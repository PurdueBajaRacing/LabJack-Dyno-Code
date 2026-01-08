from labjack import ljm
import tkinter as tk
from tkinter import ttk
import os, time, csv, sys
import logging
from threading import Thread

import random

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

VERSION = "0.0.1"
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

logging.debug(f"Running {VERSION}, using data folder {DATA_DIR}, EXE: {IS_EXE_MODE}")
loggingState = 0  # 0 - not running, 1 - running, 2 - stopping logging
easterEggCounter = -1

window = tk.Tk()
window.title("Dyno Labjack Interface")
s = ttk.Style()
s.configure(".", font=("Helvetica", 32))

try:
    os.mkdir(DATA_DIR)
    logging.debug(f"Data folder created successfully.")
except FileExistsError:
    pass
except:
    logging.exception("")

    ID_label = tk.Label(
        window,
        text="File Error?\nSomething something you have a weird filesystem.\nMove this .exe to a REASONABLE folder, and try again",
    )
    ID_label.pack()
    window.mainloop()
    sys.exit()  # prevent an exception

# Open first found LabJack
LJ_good = False
try:
    # Find the LJ: T7, Any connection, Any identifier
    handle = ljm.openS("T7", "ANY", "ANY")
    info = ljm.getHandleInfo(handle)
    logging.debug(
        "Opened a LabJack with Device type: %i, Connection type: %i,\n"
        "Serial number: %i, IP address: %s, Port: %i,\nMax bytes per MB: %i"
        % (info[0], info[1], info[2], ljm.numberToIP(info[3]), info[4], info[5])
    )
    LJ_good = True
except:
    logging.exception("")
    if IS_EXE_MODE:
        ID_label = tk.Label(
            window, text="No LabJack!\nPlug in the LabJack, and reopen this program"
        )
        ID_label.pack()
        window.mainloop()
    else:
        print("No LJ Found!")
    sys.exit()

# Labjack setup
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
]
aValues = [10, 0, 1, 0, 10, 0, 199, 0]
numFrames = len(aNames)

ljm.eWriteNames(handle, numFrames, aNames, aValues)


def makeNewFile():
    """Checks existing and creates new file name"""
    global filename

    filename_blank = "LJdata"
    i = 0
    filename = DATA_DIR + "/" + filename_blank + str(i) + ".csv"
    while os.path.exists(filename):
        i += 1
        filename = DATA_DIR + "/" + filename_blank + str(i) + ".csv"

    file_header = "Time, Torque (Nm), Speed (RPM)\n"
    with open(filename, "w") as f:
        f.write(file_header)


def start_log():
    global loggingState, easterEggCounter, filename, handle

    if loggingState:
        return

    loggingState = 1
    easterEggCounter = -1
    info_label.config(text="Setting Up...", fg="black")
    makeNewFile()

    data = [0, 0, 0]
    start_time = time.time()
    f = open(filename, "a", newline="")
    writer = csv.writer(f)

    # Read AIN0 and AIN2 from the LabJack with eReadNames in a loop.
    numFrames = 2
    aNames = ["AIN0", "AIN2"]

    intervalHandle = 1
    ljm.startInterval(intervalHandle, 1000)  # Delay between readings (in microseconds)

    info_label.config(text="Running...")
    while loggingState == 1:
        try:
            results = ljm.eReadNames(handle, numFrames, aNames)
            data[0] = time.time() - start_time

            data[1] = results[0] * 20  # 100 Nm over 5 volts
            data[2] = results[1] * 1200  # 6000 RPM over 5 volts

            writer.writerow(data)

            ljm.waitForNextInterval(intervalHandle)
        except:
            logging.exception("")

    f.close()
    ljm.cleanInterval(intervalHandle)
    ljm.close(handle)
    info_label.config(text=f"Saved data to {filename[len(DATA_DIR) + 1:]}", fg="black")
    loggingState = 0


def stop_log():
    global loggingState, easterEggCounter

    colorsList = ["black", "black", "black", "red", "orange", "yellow", "green", "blue", "indigo", "purple"] # fmt: skip

    easterEggCounter += 1
    if easterEggCounter >= len(colorsList):
        easterEggCounter = 2
        logging.debug("Oh wow, they found the easter egg!")

    if loggingState == 0:
        info_label.config(text="You aren't running!", fg=colorsList[easterEggCounter])
    elif loggingState == 1:
        loggingState = 2
        info_label.config(text="Stopping logging...")


title_label = tk.Label(window, font=("Helvetica", 32), text="Cobra Dyno!")
title_label.pack()

button_start = ttk.Button(window,text="Start",width=25,command=lambda: Thread(target=start_log).start()) # fmt: skip
button_start.pack()
button_stop = ttk.Button(window,text="Stop",width=25,command=lambda: Thread(target=stop_log).start()) # fmt: skip
button_stop.pack()

info_label = tk.Label(window, font=("Helvetica", 24), text="Press Start to Begin!")
info_label.pack()

window.mainloop()
