from pathlib import Path
import sys

# Adding parent directory to the path to access utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.remote_cw import remote_cw, RemoteConfig
from utils.helper_cv import setup_cw, cap_pass_trace, plot_traces, PLATFORM, interact
import numpy as np
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.size": 14,        # base font size
    "axes.titlesize": 18,   # ax.set_title
    "axes.labelsize": 16,   # ax.set_xlabel / set_ylabel
    "xtick.labelsize": 14,
    "ytick.labelsize": 14,
    "legend.fontsize": 14,
})
from rpyc.utils.classic import obtain
from tqdm import trange

cfg = RemoteConfig(
    host="remotechipwhisperer.example", # replace with hostname of the remote pi or its IP address
    user="pi",
    key_filename="/home/lorenzinco/.ssh/id_ecdsa", # replace with your private key path
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
        # This runs on the REMOTE machine inside the venv!
        scope, target, prog = setup_cw(cw,cw.scope())

        # Setting up the scope for capturing
        scope.adc.samples = 2100

        # Setup the target for simpleserial
        cw.put_file("hyperspaceJumpDrive-{}.hex".format(PLATFORM), "hyperspaceJumpDrive-{}.hex".format(PLATFORM))
        cw.program_target(scope, prog, "/home/pi/remote_files/hyperspaceJumpDrive-{}.hex".format(PLATFORM))
        print("[+] Programmed target with hyperspaceJumpDrive-{}.hex".format(PLATFORM))

        # Create Hamming Weight dictionary
        hw = [bin(x).count("1") for x in range(256)]
        print("[+] Created Hamming Weight dictionary")

        # Capturing traces
        traces = []
        textin = list(range(256))
        print("[+] Starting trace capture")
        for i in trange(256):
            traces.append(obtain(cap_pass_trace(scope, target, bytes([i]), command="p")))
        traces = np.array(traces)
        print("[+] Finished trace capture")

        # split traces into per-key-byte windows (12 windows of 160 samples each)
        splitted_traces = [np.array([trace[160*i:160*(i+1)] for trace in traces]) for i in range(12)]
        # splitted_traces[k] shape -> (256, 160)

        # Calculation of mean, stddev per window
        t_bar = [mean(t) for t in splitted_traces]                       # list of (160,) arrays
        t_std = [std_dev(t, t_bar[kbyte]) for kbyte, t in enumerate(splitted_traces)]  # list of (160,) arrays
        print("[+] Calculated mean and stddev of traces")

        # prepare output dir
        out_dir = Path("figures")
        out_dir.mkdir(parents=True, exist_ok=True)

        key = [0]*12
        for kbyte in range(12):
            print(f"[+] Processing key byte {kbyte}", flush=True)
            traces_k = splitted_traces[kbyte]   # shape (256, 160)
            samples = traces_k.shape[1]

            # We'll build a matrix of correlations: guesses x samples
            corr_matrix = np.zeros((256, samples), dtype=float)
            maxcpa = np.zeros(256, dtype=float)

            for kguess in range(256):
                # predicted HW for each trace given this guess (shape (256,1))
                HWS = np.array([[hw[t ^ kguess] for t in textin]]).transpose()  # (256,1)
                HWS_bar = mean(HWS)   # scalar-ish shape (1,)
                HWS_std = std_dev(HWS, HWS_bar)  # shape (1,)

                covariances = cov(traces_k, t_bar[kbyte], HWS, HWS_bar)   # shape (samples,)
                # correlations per sample (shape samples,)
                correlations = covariances / (t_std[kbyte] * (HWS_std + 1e-12))

                corr_matrix[kguess, :] = np.abs(correlations)
                maxcpa[kguess] = np.max(np.abs(correlations))

            # select best guess
            best_guess = int(np.argmax(maxcpa))
            key[kbyte] = best_guess
            print(f"[+] Found key byte {kbyte}: {best_guess:02x}, {maxcpa[best_guess]:.6f}")

            # --- Plot heatmap (guesses vs sample index) ---
            plt.figure(figsize=(10, 5))
            plt.imshow(corr_matrix, aspect='auto', origin='lower', interpolation='nearest')
            plt.colorbar(label='|correlation|')
            plt.xlabel('Sample index (windowed)')
            plt.ylabel('Key guess (0..255)')
            plt.title(f'Hyperspace CPA - byte {kbyte}: |corr| (guess vs sample)')
            # mark best guess row
            plt.axhline(best_guess, color='white', linewidth=1.0, linestyle='--', alpha=0.8)
            plt.tight_layout()
            heatmap_path = out_dir / f"hyperspace_cpa_kbyte_{kbyte}.png"
            plt.savefig(heatmap_path, dpi=200)
            plt.close()

            # --- Plot max-correlation per guess bar chart ---
            plt.figure(figsize=(10, 2.5))
            plt.bar(np.arange(256), maxcpa)
            plt.xlabel('Key guess')
            plt.ylabel('max |corr|')
            plt.title(f'Hyperspace CPA - byte {kbyte}: max absolute correlation per guess (best={best_guess})')
            plt.tight_layout()
            barpath = out_dir / f"hyperspace_cpa_maxcorr_kbyte_{kbyte}.png"
            plt.savefig(barpath, dpi=200)
            plt.close()

        print(f"[+] Found key: {''.join([f'{k:02x}' for k in key])}")
        resp = interact(scope, target, 'a', bytes(key), bytes_to_read=17)
        print(f"[+] Response: {resp}")

# [+] Found key byte 0: 37, 0.584252
# [+] Found key byte 1: 45, 0.573846
# [+] Found key byte 2: 4c, 0.525603
# [+] Found key byte 3: 16, 0.605838
# [+] Found key byte 4: 6e, 0.418389
# [+] Found key byte 5: 1c, 0.434965
# [+] Found key byte 6: 77, 0.518524
# [+] Found key byte 7: 2d, 0.558147
# [+] Found key byte 8: 5b, 0.495616
# [+] Found key byte 9: 5a, 0.521182
# [+] Found key byte 10: 22, 0.628889
# [+] Found key byte 11: 7b, 0.456448
# [+] Found key: 37454c166e1c772d5b5a227b
# [+] Response: bytearray(b'ESC{21hYP35TrEEt}')



        
if __name__ == "__main__":
    main()
