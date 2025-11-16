from pathlib import Path
import itertools
import sys

# Adding parent directory to the path to access utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.remote_cw import remote_cw, RemoteConfig
from utils.helper_cv import setup_cw, cap_pass_trace, plot_traces, PLATFORM, interact
import numpy as np
import matplotlib.pyplot as plt
from rpyc.utils.classic import obtain
from tqdm import trange

cfg = RemoteConfig(
    host="remotechipwhisperer.example", # replace with hostname of the remote pi or its IP address
    user="pi",
    key_filename="/home/nect/.ssh/id_ed25519", # replace with your private key path
    port=18812,                  # must match the rpyc_classic on the Pi
    connect_host="127.0.0.1",    # local end (your machine)
    remote_host="127.0.0.1",     # remote rpyc_classic bind address
)


def get_shift_trace(scope, target, tresh, shifts):
    payload = bytes([tresh & 0xff, (tresh >> 8)&0xff] + shifts)
    return obtain(cap_pass_trace(scope, target, payload, command="s", reset=True))


def trace_corr(a, b):
    a = np.asarray(a)
    b = np.asarray(b)
    a = a - np.mean(a)
    b = b - np.mean(b)
    corr = np.corrcoef(a, b)[0, 1]
    return corr


def find_min_shift_for_branch(scope, target, tresh, shifts, ref_trace):
    idx = (tresh - 1) % 4

    for i in range(1, 17):
        shifts[idx] = i
        trace = get_shift_trace(scope, target, tresh, shifts)
        corr = trace_corr(trace, ref_trace)
        if abs(corr) < 0.92:
            return i
    return 0


def get_samples(scope, target, qr, rot):
    tresh = qr * 4 + rot + 1
    ref_trace = get_shift_trace(scope, target, tresh, [0]*4)

    STEP_TABLE = {0:1, 1:1, 2:4, 3:4}
    step = STEP_TABLE.get(rot, 2)
    values = list(range(1, 17, step))
    combos = itertools.product(values, repeat=rot)

    ls = []
    for combo in combos:
        shifts = list(combo) + [0] * (4 - rot)
        smin = find_min_shift_for_branch(scope, target, tresh, shifts, ref_trace)

        x = {
                "tresh": tresh,
                "shifts": shifts,
                "smin": smin,
        }
        print(x)
        ls.append(x)

    return ls

def main():
    with remote_cw(cfg) as cw:
        # This runs on the REMOTE machine inside the venv!
        scope, target, prog = setup_cw(cw,cw.scope())

        # Setting up the scope for capturing
        scope.adc.samples = 100

        if "UPLOAD" in sys.argv:
            cw.put_file("ghostBlood-{}.hex".format(PLATFORM), "ghostBlood-{}.hex".format(PLATFORM))
            cw.program_target(scope, prog, "/home/pi/remote_files/ghostBlood-{}.hex".format(PLATFORM))
            print("[+] Programmed target with ghostBlood-{}.hex".format(PLATFORM))

        samples = {}
        for qr in range(4):
            for rot in range(4):
                tresh = qr * 4 + rot + 1
                samples[tresh] = get_samples(scope, target, qr, rot)

            with open("sample.json", "wb") as f:
                import json
                f.write(json.dumps(samples).encode())


if __name__ == "__main__":
    main()

