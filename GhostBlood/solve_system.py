from pathlib import Path
import itertools
import sys

# Adding parent directory to the path to access utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.remote_cw import remote_cw, RemoteConfig
from utils.helper_cv import setup_cw, cap_pass_trace, plot_traces, PLATFORM, interact, reset_target
import numpy as np
import matplotlib.pyplot as plt
from rpyc.utils.classic import obtain
from tqdm import trange

cfg = RemoteConfig(
    host="remotechipwhisperer.example", # replace with hostname of the remote pi or its IP address
    user="pi",
    key_filename="path/to/your/priv_key", # replace with your private key path
    port=18812,                  # must match the rpyc_classic on the Pi
    connect_host="127.0.0.1",    # local end (your machine)
    remote_host="127.0.0.1",     # remote rpyc_classic bind address
)

def try_solve(k):
    with remote_cw(cfg) as cw:
        # This runs on the REMOTE machine inside the venv!
        scope, target, prog = setup_cw(cw,cw.scope())

        KEY = bytearray(16)
        for i, n in enumerate(k):
            KEY[i*2] = n&0xFF
            KEY[i*2+1] = n >> 8

        target.simpleserial_write('d', bytes(KEY))
        flag = target.simpleserial_read('r', 21, timeout=50)
        print("RESPONSE:", flag)

from z3 import *
import json,sys

key = [BitVec(f'k{i}', 16) for i in range(8)]

NONCE = [0xeaee,  0x83a0, 0xd9a6, 0xb8f7]

CONSTS = [0x4554, 0x4332, 0x3032, 0x3520]

SOLVER = Solver()

MASK = BitVecVal(0xffff, 16)

SAMPLES = {}

TRESH = 0

def ROTL(x, n, shifts):
    global TRESH

    x = x & MASK
    TRESH += 1

    if n > 16:
        return x

    if TRESH in SAMPLES:
        if tuple(shifts) in SAMPLES[TRESH]:
            # add constraint on x >= 1 <<(16-n)

            lo = BitVecVal(2**(16 - n), 16)      # inclusive
            SOLVER.add(UGE(x, lo))
            if 2**(16 - n + 1) < (1 << 16):
                hi = BitVecVal(2**(16 - n + 1), 16)
                SOLVER.add(ULT(x, hi))

    return ((x << n) | LShR(x, 16 - n)) & MASK

def quarter_round(a, b, c, d, shifts):
    b = (b ^ ROTL(a+d, shifts[0], shifts)) & MASK
    c = (c ^ ROTL(b+a, shifts[1], shifts)) & MASK
    d = (d ^ ROTL(c+b, shifts[2], shifts)) & MASK
    a = (a ^ ROTL(d+c, shifts[3], shifts)) & MASK
    return a, b, c, d

def block_cipher(key, shifts):
    x = [CONSTS[0], key[0], key[1], key[2], key[3],
             CONSTS[1], NONCE[0], NONCE[1], NONCE[2], NONCE[3],
             CONSTS[2], key[4], key[5], key[6], key[7], CONSTS[3]]

    global TRESH
    TRESH = 0

    # only first round
    x[0], x[4], x[8], x[12] = quarter_round(x[0], x[4], x[8], x[12], shifts)
    x[5], x[9], x[13], x[1] = quarter_round(x[5], x[9], x[13], x[1], shifts)
    x[10], x[14], x[2], x[6] = quarter_round(x[10], x[14], x[2], x[6], shifts)
    x[15], x[3], x[7], x[11] = quarter_round(x[15], x[3], x[7], x[11], shifts)

    #x[0], x[1], x[2], x[3] = quarter_round(x[0], x[1], x[2], x[3], shifts)
    #x[5], x[6], x[7], x[4] = quarter_round(x[5], x[6], x[7], x[4], shifts)
    #x[10], x[11], x[8], x[9] = quarter_round(x[10], x[11], x[8], x[9], shifts)
    #x[15], x[12], x[13], x[14] = quarter_round(x[15], x[12], x[13], x[14], shifts)

def main():
    global SAMPLES

    file = 'sample.json'
    if len(sys.argv) > 1:
        file = sys.argv[1]

    all_sets = set()

    with open(file,'r') as f:
        t = json.load(f)

        for tresh, samples in t.items():
            sets = set()

            for sample in samples:
                # smin should be in the shifts
                x = sample['shifts']
                idx = (int(tresh)-1)%4
                x[idx] = sample['smin']
                sets.add(tuple(x))

            SAMPLES[int(tresh)] = sets
            all_sets.update(sets)


    for shift in all_sets:
        block_cipher(key, shift)
        if SOLVER.check() != sat:
            print("ERROR")
            break

    if SOLVER.check() == sat:
        # print all solutions
        while SOLVER.check() == sat:
            model = SOLVER.model()
            key_guess = [model[k].as_long() if model[k] is not None else None for k in key]
            print(f"[+] Key guess: {[hex(k) if k is not None else None for k in key_guess]}")

            try_solve(key_guess)

            # add constraint to avoid this solution
            SOLVER.add(Or([k != model[k] for k in key if model[k] is not None]))
    else:
        print("[-] No solution found")

if __name__ == "__main__":
    main()



# [0xea96, 0xf735, 0x95b5, 0xba52, 0xd896, 0x1a96, 0xb689, 0x5f9],
# bytearray(bESC{Th*t\'sT*eSp1*1t!})
