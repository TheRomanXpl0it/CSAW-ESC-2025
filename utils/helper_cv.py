import time
import matplotlib.pyplot as plt
import os

SCOPETYPE = 'CWNANO'
PLATFORM = 'CWNANO'


def setup_cw(cw,scope):
    
    try:
        if not scope.connectStatus:
            scope.con()
    except NameError:
        scope = cw.scope()

    try:
        if SS_VER == "SS_VER_2_1":
            target_type = cw.targets.SimpleSerial2
        elif SS_VER == "SS_VER_2_0":
            raise OSError("SS_VER_2_0 is deprecated. Use SS_VER_2_1")
        else:

            target_type = cw.targets.SimpleSerial
    except:
        SS_VER="SS_VER_1_1"
        target_type = cw.targets.SimpleSerial

    try:
        target = cw.target(scope, target_type)
    except:
        print("INFO: Caught exception on reconnecting to target - attempting to reconnect to scope first.")
        print("INFO: This is a work-around when USB has died without Python knowing. Ignore errors above this line.")
        scope = cw.scope()
        target = cw.target(scope, target_type)


    print("INFO: Found ChipWhisperer😍")

    if "STM" in PLATFORM or PLATFORM == "CWLITEARM" or PLATFORM == "CWNANO":
        prog = cw.programmers.STM32FProgrammer
    elif PLATFORM == "CW303" or PLATFORM == "CWLITEXMEGA":
        prog = cw.programmers.XMEGAProgrammer
    elif "neorv32" in PLATFORM.lower():
        prog = cw.programmers.NEORV32Programmer
    elif "SAM4S" in PLATFORM or PLATFORM == "CWHUSKY":
        prog = cw.programmers.SAM4SProgrammer
    else:
        prog = None

    time.sleep(0.05)
    scope.default_setup()
    
    #scope.clock.adc_freq = 16000000

    return scope, target, prog

def reset_target(scope):
    if PLATFORM == "CW303" or PLATFORM == "CWLITEXMEGA":
        scope.io.pdic = 'low'
        time.sleep(0.1)
        scope.io.pdic = 'high_z' #XMEGA doesn't like pdic driven high
        time.sleep(0.1) #xmega needs more startup time
    elif "neorv32" in PLATFORM.lower():
        raise IOError("Default iCE40 neorv32 build does not have external reset - reprogram device to reset")
    elif PLATFORM == "CW308_SAM4S" or PLATFORM == "CWHUSKY":
        scope.io.nrst = 'low'
        time.sleep(0.25)
        scope.io.nrst = 'high_z'
        time.sleep(0.25)
    else:  
        scope.io.nrst = 'low'
        time.sleep(0.05)
        scope.io.nrst = 'high_z'
        time.sleep(0.05)

def cap_pass_trace(scope, target, pass_guess: bytes, command: str = "a", verbose: bool = False, read_bytes: int = 18, reset: bool = True):
    if reset:
        reset_target(scope)
    num_char = target.in_waiting()
    while num_char > 0:
        target.read(num_char, 10)
        time.sleep(0.01)
        num_char = target.in_waiting()

    scope.arm()
    target.simpleserial_write(command, pass_guess) 
    response = target.simpleserial_read('r', read_bytes, timeout=50)
    if verbose:
        print(f"[+] Response: {response}")
    ret = scope.capture()
    if ret:
        print('Timeout happened during acquisition')
        return None

    trace = scope.get_last_trace()
    return trace

def interact(scope, target, command: str, pass_guess: bytes, bytes_to_read: int = 1):
    num_char = target.in_waiting()
    while num_char > 0:
        target.read(num_char, 10)
        time.sleep(0.01)
        num_char = target.in_waiting()
    target.simpleserial_write(command, pass_guess) 
    response = target.simpleserial_read('r', bytes_to_read)
    return response

        
def plot_traces(traces, filename="palle.png"):
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

    fig = plt.figure(figsize=(50, 4))
    ax = fig.add_subplot(111)

    ax.plot(traces[0], label="Trace 1", linewidth=1.5)
    ax.plot(traces[1], label="Trace 2", linewidth=1.5, alpha=0.6)

    ax.set_title("Confronto tra due tracce di acquisizione", pad=12)
    ax.legend(loc="upper right", fontsize=10)
    ax.set_xlabel("Campioni")
    ax.set_ylabel("Ampiezza del segnale")
    ax.grid(True, linestyle="--", alpha=0.4)

    fig.tight_layout()
    fig.savefig(filename, dpi=300)
    plt.close(fig) # oom fix

def reboot_flush(scope, target):
    reset_target(scope)
    target.flush()


def upload_firmware(cw, scope, prog, challenge_name):

    cw.put_file("{}-{}.hex".format(challenge_name, PLATFORM), "{}-{}.hex".format(challenge_name, PLATFORM))
    cw.program_target(scope, prog, "/home/pi/remote_files/{}-{}.hex".format(challenge_name, PLATFORM))
    print("[+] Programmed target with {}-{}.hex".format(challenge_name, PLATFORM))