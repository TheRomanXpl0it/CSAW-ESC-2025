from pathlib import Path
import sys

# Adding parent directory to the path to access utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.remote_cw import remote_cw, RemoteConfig
from utils.helper_cv import setup_cw, cap_pass_trace, plot_traces, PLATFORM, interact, upload_firmware
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
        scope.adc.samples = 2200
        # BAUD = target.baud
        # CLOCK = scope.io.clkout
        # NEWCLOCK = 7.5e6
        # scope.io.clkout = NEWCLOCK
        # NEWCLOCK = scope.io.clkout
        # target.baud = BAUD * NEWCLOCK / CLOCK
        scope.adc.clk_freq = 7500000.0
        # print(f"[+] Changed baud rate from {BAUD} to {target.baud}")
        # print(f"[+] Changed clkout from {CLOCK} to {NEWCLOCK}")

        # Setup the target for simpleserial
        upload_firmware(cw, scope, prog, "chaos")

        # Attack loop for SorterSong1
        secret_array = []
        
        for byte_pos in range(14, -1, -1):
            interact(scope, target, command="x", pass_guess=b'')        
            reference_trace = obtain(cap_pass_trace(scope, target, pass_guess=bytes([2, 0, 0, byte_pos]), command="p", reset=False))
            interact(scope, target, command="x", pass_guess=b'')        
            reference_trace_2 = obtain(cap_pass_trace(scope, target, pass_guess=bytes([2, 1, 0, byte_pos]), command="p", reset=False))
            diff_ref = np.sum(np.abs(reference_trace - reference_trace_2))
            #print(f"Diff for {0} and {1}: {diff_ref}")
            #plot_traces([reference_trace, reference_trace_2], filename=f"traces/traces_bytepos_{byte_pos}.png")

            min_i = 2
            max_i = 0xffff
            secret_byte = 2
            while min_i <= max_i:
                i = (min_i + max_i) // 2
                interact(scope, target, command="x", pass_guess=b'')        
                trace = obtain(cap_pass_trace(scope, target, pass_guess=bytes([2, i&0xff, i>>8, byte_pos]), command="p", reset=False))
                diff = np.abs(trace - reference_trace)
                #print(f"Diff for {i} at position {byte_pos+1}: {np.sum(diff)}")
                if np.sum(diff) > diff_ref+80:
                    max_i = i-1
                else:
                    min_i = i+1
                    secret_byte = i
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

# [+] Programmed target with chaos-CWNANO.hex
# [+] Found value 19617 for position 15
# [+] Found value 49204 for position 14
# [+] Found value 29600 for position 13
# [+] Found value 64986 for position 12
# [+] Found value 64748 for position 11
# [+] Found value 25986 for position 10
# [+] Found value 13983 for position 9
# [+] Found value 6536 for position 8
# [+] Found value 42349 for position 7
# [+] Found value 9092 for position 6
# [+] Found value 58772 for position 5
# [+] Found value 36080 for position 4
# [+] Found value 45996 for position 3
# [+] Found value 697 for position 2
# [+] Found value 27964 for position 1
# [+] Secret array found:  [697, 6536, 9092, 13983, 19617, 25986, 27964, 29600, 36080, 42349, 45996, 49204, 58772, 64748, 64986]
# [+] Flag:  bytearray(b'eoc{th3yreC00ked}   ')