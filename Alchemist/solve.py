from pathlib import Path
import sys

# Adding parent directory to the path to access utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.remote_cw import remote_cw, RemoteConfig
from utils.helper_cv import setup_cw, cap_pass_trace, plot_traces, PLATFORM, interact, upload_firmware
import numpy as np
import matplotlib.pyplot as plt
from rpyc.utils.classic import obtain
from tqdm import trange, tqdm
import os
from itertools import product

cfg = RemoteConfig(
    host="remotechipwhisperer.example", # replace with hostname of the remote pi or its IP address
    user="pi",
    key_filename="path/to/your/priv_key", # replace with your private key path
    port=18812,                  # must match the rpyc_classic on the Pi
    connect_host="127.0.0.1",    # local end (your machine)
    remote_host="127.0.0.1",     # remote rpyc_classic bind address
)

def mean(X):
    return np.sum(X, axis=0)/len(X)

def std_dev(X, X_bar):
    return np.sqrt(np.sum((X-X_bar)**2, axis=0))

def cov(X, X_bar, Y, Y_bar):
    return np.sum((X-X_bar)*(Y-Y_bar), axis=0)

def main():
    with remote_cw(cfg) as cw:

        CHALLENGE_NAME = "alchemistInfuser"
        # This runs on the REMOTE machine inside the venv!
        scope, target, prog = setup_cw(cw,cw.scope())

        # Setting up the scope for capturing
        scope.adc.samples = 3500
        # BAUD = target.baud
        # CLOCK = scope.io.clkout
        # NEWCLOCK = 3.75e6
        # scope.io.clkout = NEWCLOCK
        # NEWCLOCK = scope.io.clkout
        # target.baud = BAUD * NEWCLOCK / CLOCK
        # scope.adc.clk_freq = 15000000.0
        # print(f"[+] Changed baud rate from {BAUD} to {target.baud}")
        # print(f"[+] Changed clkout from {CLOCK} to {NEWCLOCK}")

        # Setup the target for simpleserial
        upload_firmware(cw, scope, prog, CHALLENGE_NAME)

        # Create Hamming Weight dictionary
        hw = [bin(x).count("1") for x in range(256)]
        print("[+] Created Hamming Weight dictionary")

        # Capturing traces
        NSAMPLES = 400
        traces = []
        textin = [os.urandom(8) for _ in range(NSAMPLES)]
        print("[+] Starting trace capture")
        for i in trange(NSAMPLES):
            traces.append(obtain(cap_pass_trace(scope, target, bytes(textin[i]), command="e")))
        traces = np.array(traces)
        print("[+] Finished trace capture")
        np.save("traces/traces.npy", traces)

        assignment_index = 191
        splitted_traces = [np.array([[trace[20+203*i:20+203*(i+1)][assignment_index]] for trace in traces]) for i in range(8)]
        # for i in range(8):
        #     plot_traces(splitted_traces[i], 'traces/splitted_trace_byte_'+str(i)+'.png')
        # Calculation of mean, stddev
        t_bar = [mean(t) for t in splitted_traces]
        t_std = [std_dev(t, t_bar[kbyte]) for kbyte, t in enumerate(splitted_traces)]
        print("[+] Calculated mean and stddev of traces")
        
        possible_keys = []
        key = [0]*8
        for kbyte in range(8):
            maxcpa = [0]*256
            maxcpa_index = [0]*256
            for kguess in range(256):
                HWS = np.array([[hw[t[kbyte]^kguess] for t in textin]]).transpose()
                HWS_bar = mean(HWS)
                HWS_std = std_dev(HWS, HWS_bar)
                covariances = cov(splitted_traces[kbyte], t_bar[kbyte], HWS, HWS_bar)
                correlations = covariances / (t_std[kbyte] * HWS_std)
                maxcpa[kguess] = np.max(np.abs(correlations))
            key[kbyte] = np.argmax(maxcpa)
            mean_cpa = np.mean(maxcpa)
            std_cpa = np.std(maxcpa)
            possible_indices = np.where(maxcpa > 0.95*maxcpa[key[kbyte]])[0]
            possible_keys.append(possible_indices)
            print(f"[+] Found key byte {kbyte}: {key[kbyte]:02x}, {maxcpa[key[kbyte]]:.6f}, maxcpa mean: {mean_cpa:.6f}+/-{std_cpa:.6f}, possible indices: {possible_indices}") 


        splitted_traces = [np.array([trace[20+203*8+204*i:20+203*8+204*(i+1)] for trace in traces]) for i in range(8)]
        # for i in range(8):
        #     plot_traces(splitted_traces[i], 'traces/splitted_trace_byte_'+str(i)+'.png')

        # Calculation of mean, stddev
        t_bar = [mean(t) for t in splitted_traces]
        t_std = [std_dev(t, t_bar[kbyte]) for kbyte, t in enumerate(splitted_traces)]
        print("[+] Calculated mean and stddev of traces")
        
        key2 = [0]*8
        for kbyte in range(8):
            maxcpa = [0]*256
            for kguess in range(256):
                HWS = np.array([[hw[t[kbyte]^key[kbyte]^kguess] for t in textin]]).transpose()
                HWS_bar = mean(HWS)
                HWS_std = std_dev(HWS, HWS_bar)
                covariances = cov(splitted_traces[kbyte], t_bar[kbyte], HWS, HWS_bar)
                correlations = covariances / (t_std[kbyte] * HWS_std)
                maxcpa[kguess] = np.max(np.abs(correlations))
            key2[kbyte] = np.argmax(maxcpa)
            mean_cpa = np.mean(maxcpa)
            std_cpa = np.std(maxcpa)
            possible_indices = np.where(maxcpa > 0.95*maxcpa[key2[kbyte]])[0]
            new_possible_indices = np.append(possible_indices, [k^0xff for k in possible_indices])
            possible_keys.append(new_possible_indices)
            print(f"[+] Found key byte {kbyte}: {key2[kbyte]:02x}, {maxcpa[key2[kbyte]]:.6f}, maxcpa mean: {mean_cpa:.6f}+/-{std_cpa:.6f}, possible indices: {new_possible_indices}")

        print(f"[+] Found key: {''.join([f'{k:02x}' for k in key+key2])}")
        resp = interact(scope, target, 'c', bytes(key+key2), bytes_to_read=17)
        print(resp)

        for key in tqdm(list(product(*possible_keys))):
            print(f"[+] Trying key: {''.join([f'{k:02x}' for k in key])}")
            resp = obtain(interact(scope, target, 'c', bytes(key), bytes_to_read=17))
            if resp!=bytearray(b'deadlyWhiteJade!!'):
                print(f"[+] Found key: {''.join([f'{k:02x}' for k in key])}")
                print(f"[+] Response: {resp}")
                break
            print(f"[+] Response: {resp}")

# [+] Trying key: 4e614a2d556752643270586b38763573
# [+] Found key: 4e614a2d556752643270586b38763573
# [+] Response: bytearray(b'a1c{Wh1teDragonT}')



        
if __name__ == "__main__":
    main()
