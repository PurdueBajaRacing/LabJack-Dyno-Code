from labjack import ljm
import ttkbootstrap as ttk
import os, time, csv, sys
import logging
from threading import Thread

"""
Relevant Documentation:
 
LJM Library:
    LJM Library Installer:
        https://labjack.com/support/software/installers/ljm
    LJM Users Guide:
        https://labjack.com/support/software/api/ljm
    Opening and Closing:
        https://labjack.com/support/software/api/ljm/function-reference/opening-and-closing
    Constants:
        https://labjack.com/support/software/api/ljm/constants
    Stream Functions:
        https://labjack.com/support/software/api/ljm/function-reference/stream-functions
 
T-Series and I/O:
    Modbus Map:
        https://labjack.com/support/software/api/modbus/modbus-map
    Stream Mode: 
        https://labjack.com/support/datasheets/t-series/communication/stream-mode
    Analog Inputs:
        https://labjack.com/support/datasheets/t-series/ain

"""

VERSION = "0.0.6"
IS_EXE_MODE = getattr(sys, "frozen", False)
if IS_EXE_MODE:
    DATA_DIR = os.path.dirname(sys.executable) + "/data"
else:
    DATA_DIR = os.path.dirname(os.path.realpath(__file__)) + "/data"

# start logger with info
logging.basicConfig(
    filename=f"app.log",
    encoding="utf-8",
    filemode="a",
    format="{asctime}:{levelname}:{name}:{message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG,
)


def openLabJack():
    # Open first found LabJack
    try:
        # Find the LJ: T7, Any connection, Any identifier
        handle_local = ljm.openS("T7", "ANY", "ANY")
        info = ljm.getHandleInfo(handle_local)
        logging.debug(
            "Opened a LabJack with Device type: %i, Connection type: %i,\n"
            "Serial number: %i, IP address: %s, Port: %i,\nMax bytes per MB: %i"
            % (info[0], info[1], info[2], ljm.numberToIP(info[3]), info[4], info[5])
        )
    except:
        logging.exception("")
        return None

    # Labjack setup

    # Ensure triggered stream is disabled.
    ljm.eWriteName(handle_local, "STREAM_TRIGGER_INDEX", 0)

    # Enabling internally-clocked stream.
    ljm.eWriteName(handle_local, "STREAM_CLOCK_SOURCE", 0)

    # AIN0:
    #   Range = +/-10.0 V (10)
    #   Resolution index = Default (0)
    #   Negative Channel = Differential with AIN1 as negative (1)
    #   Settling, in microseconds = Auto (0)
    #   See https://github.com/labjack/labjack-ljm-python/blob/master/Examples/More/Utilities/thermocouple_example_ain_ef.py#L103
    #      for Diffy reference

    # AIN2:
    #   Range = +/-10.0 V (10)
    #   Resolution index = Default (0)
    #   Negative Channel = single-ended (199)
    #   Settling, in microseconds = Auto (0)
    aNames = [
        "AIN0_RANGE",
        "AIN0_RESOLUTION_INDEX",
        "AIN0_NEGATIVE_CH",
        "AIN0_SETTLING_US",
        "AIN2_RANGE",
        "AIN2_RESOLUTION_INDEX",
        "AIN2_NEGATIVE_CH",
        "AIN2_SETTLING_US",
        "STREAM_SETTLING_US",
    ]
    aValues = [10, 0, 1, 0, 10, 0, ljm.constants.GND, 0, 450]
    numFrames = len(aNames)
    ljm.eWriteNames(handle_local, numFrames, aNames, aValues)

    return handle_local


def makeNewFile():
    """Checks existing and creates new file name"""

    filename_blank = "LJdata"
    i = 0
    filename = DATA_DIR + "/" + filename_blank + str(i) + ".csv"
    while os.path.exists(filename):
        i += 1
        filename = DATA_DIR + "/" + filename_blank + str(i) + ".csv"

    file_header = "Time, Torque (Nm), Speed (RPM)\n"
    with open(filename, "w") as f:
        f.write(file_header)

    return filename


def start_log():
    global loggingState, easterEggCounter

    if loggingState:
        return

    logging.debug("Starting data logging...")

    info_label.config(text="Setting Up...", fg=None)
    loggingState = 1
    easterEggCounter = -1
    current_filename = makeNewFile()

    handle = openLabJack()
    if handle is None:
        info_label.config(text="Failed to open LabJack, try again")
        return

    data = [0, 0, 0]
    # f = open(current_filename, "a", newline="")
    # writer = csv.writer(f)

    # Stream Configuration
    # Scan list names to stream - Must be updated depending on sensors
    aScanListNames = ["AIN0", "AIN2"]
    numAddresses = len(aScanListNames)
    aScanList = ljm.namesToAddresses(numAddresses, aScanListNames)[0]
    scanRate = 1000  # Sampling frequency in Hz
    scansPerRead = 1  # How many samples are pulled off the buffer at once

    # Configure and start stream
    ljm.eStreamStart(handle, scansPerRead, numAddresses, aScanList, scanRate)

    last_visual_update = 0
    start_time = time.time()

    logging.debug(f"Writing data to {current_filename}")

    while loggingState == 1:
        try:
            aData = ljm.eStreamRead(handle)[0]
            data[0] = time.time() - start_time

            data[1] = aData[0] * -20  # 100 Nm over 5 volts
            data[2] = aData[1] * 1200  # 6000 RPM over 5 volts

            if time.time() - last_visual_update > (1 / 60):
                info_label.config(
                    text=f"Torque {data[1]:.3f} N-m\nSpeed {data[2]:.3f} RPM"
                )
                last_visual_update = time.time()

            # writer.writerow(data)

            with open(current_filename, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(data)
        except:
            logging.exception("")

    logging.debug("Stopping data record...")
    try:
        info_label.config(text="Stopping recording...")
        f.close()
        ljm.eStreamStop(handle)  # Close Data stream from LJ
        ljm.close(handle)
        logging.debug("Stopped & saved data")
        info_label.config(text=f"Saved data to {current_filename[len(DATA_DIR) + 1:]}")
    except:
        logging.exception("")
        info_label.config(text=f"Failed to save data")
    loggingState = 0


def stop_log():
    global loggingState, easterEggCounter

    colorsList = [None, None, None, "red", "orange", "yellow", "green", "blue", "indigo", "purple"] # fmt: skip

    easterEggCounter += 1
    if easterEggCounter >= len(colorsList):
        easterEggCounter = 2
        logging.debug("Oh wow, they found the easter egg!")

    if loggingState == 0:
        info_label.config(text="You aren't running!", fg=colorsList[easterEggCounter])
    elif loggingState == 1:
        loggingState = 2
        info_label.config(text="Stopping logging...")


logging.debug(f"Running {VERSION}, using data folder {DATA_DIR}, EXE: {IS_EXE_MODE}")
loggingState = 0  # 0 - not running, 1 - running, 2 - stopping logging
easterEggCounter = -1

window = ttk.Window()
window.title(f"Labjack-Dyno Interface - Version {VERSION}")

try:
    os.mkdir(DATA_DIR)
    logging.debug(f"Data folder created successfully.")
except FileExistsError:
    pass
except:
    logging.exception("")

    ID_label = ttk.Label(
        window,
        text="File Error?\nSomething something you have a weird filesystem.\nMove this .exe to a REASONABLE folder, and try again\nIf it's in a reasonable folder, let Taiga know",
    )
    ID_label.pack()
    window.mainloop()
    sys.exit()  # prevent an exception

handle = openLabJack()
if handle is None:
    print("No LJ Found!")
    ID_label = ttk.Label(
        window, text="No LabJack!\nPlug in the LabJack, and reopen this program"
    )
    ID_label.pack()
    window.mainloop()
    sys.exit()
ljm.close(handle)

s = ttk.Style("darkly")
s.configure(".", font=("", 24))

title_label = ttk.Label(window, text="Cobra Dyno!")
title_label.pack()

button_start = ttk.Button(window,text="Start",width=25,command=lambda: Thread(target=start_log).start(),bootstyle="outline") # fmt: skip
button_start.pack()
button_stop = ttk.Button(window,text="Stop",width=25,command=lambda: Thread(target=stop_log).start(),bootstyle="outline") # fmt: skip
button_stop.pack()

info_label = ttk.Label(window, text="Press Start to Begin!")
info_label.pack()

window.mainloop()
sys.exit()
