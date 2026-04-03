from labjack import ljm
import ttkbootstrap as ttk
import os, time, csv, sys
import logging
from threading import Thread
from statistics import mean

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

VERSION = "0.0.8"
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
    level=logging.INFO,
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
    #   Negative Channel = single-ended (199)
    #   Settling, in microseconds = Auto (0)

    # AIN1 is the negative port for both AIN0 and AIN2

    # AIN2:
    #   Range = +/-10.0 V (10)
    #   Resolution index = Default (0)
    #   Negative Channel = single-ended (199)
    #   Settling, in microseconds = Auto (0)

    # DIO0:
    #   Built-in non-removable 100k pullup to 3.3V
    #   System tolerant to 5.8V
    #   See https://support.labjack.com/docs/13-2-8-high-speed-counter-t-series-datasheet#Stream-Read

    aNames = [
        "AIN0_RANGE",
        "AIN0_RESOLUTION_INDEX",
        "AIN0_NEGATIVE_CH",
        "AIN0_SETTLING_US",
        "AIN1_RANGE",
        "AIN1_RESOLUTION_INDEX",
        "AIN1_NEGATIVE_CH",
        "AIN1_SETTLING_US",
        "AIN2_RANGE",
        "AIN2_RESOLUTION_INDEX",
        "AIN2_NEGATIVE_CH",
        "AIN2_SETTLING_US",
        "STREAM_SETTLING_US",
        "DIO0_EF_ENABLE",
        "DIO0_EF_INDEX",
    ]
    aValues = [10, 0, ljm.constants.GND, 0, 10, 0, ljm.constants.GND, 0, 10, 0, ljm.constants.GND, 0, 450, 0, 8]  # fmt: skip
    numFrames = len(aNames)
    ljm.eWriteNames(handle_local, numFrames, aNames, aValues)

    # LabJack can't reconfigure EFs if the enable is 1
    aNames = ["DIO0_EF_ENABLE"]
    aValues = [1]
    numFrames = len(aNames)
    ljm.eWriteNames(handle_local, numFrames, aNames, aValues)

    return handle_local


def makeNewFile():
    # Checks existing and creates new file name

    filename_blank = "LJdata"
    i = 0
    filename = DATA_DIR + "/" + filename_blank + str(i) + ".csv"
    while os.path.exists(filename):
        i += 1
        filename = DATA_DIR + "/" + filename_blank + str(i) + ".csv"

    file_header = "Time, Torque (Nm), Shaft Speed (RPM), Engine Speed (RPM)\n"
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

    # Stream Configuration
    # Scan list names to stream - Must be updated depending on sensors
    aScanListNames = [
        "AIN0",
        "AIN1",
        "AIN2",
        "DIO0_EF_READ_A",
        "STREAM_DATA_CAPTURE_16",
    ]
    numAddresses = len(aScanListNames)
    aScanList = ljm.namesToAddresses(numAddresses, aScanListNames)[0]
    scanRate = 1000  # Sampling frequency in Hz
    scansPerRead = 1  # How many samples are pulled off the buffer at once

    lastEngineRPMCount = 0
    engineScanRate = 10  # engine RPM reads in Hz
    engineRPMFactor = 60 / 20  # TODO: replace the 20 with the number of fins

    data = []
    newData = [0, 0, 0, 0]
    last_visual_update = 0
    logging.debug(f"Writing data to {current_filename}")

    # reset the high speed counter
    ljm.eReadName(handle, "DIO0_EF_READ_A_AND_RESET")

    # Configure and start stream
    ljm.eStreamStart(handle, scansPerRead, numAddresses, aScanList, scanRate)

    start_time = time.time()

    while loggingState == 1:
        try:
            aData = ljm.eStreamRead(handle)[0]
            now = time.time()
            newData[0] = now - start_time

            newData[1] = (aData[0] - aData[1]) * -20  # 100 Nm over 5 volts
            newData[2] = (aData[2] - aData[1]) * 1200  # 6000 RPM over 5 volts

            rawEngineRPMCount = aData[3] + aData[4] * 65536  # engine RPM data
            newData[3] = rawEngineRPMCount - lastEngineRPMCount
            lastEngineRPMCount = rawEngineRPMCount

            data.append(newData)

            if now - last_visual_update > (1 / 60):
                info_label.config(
                    text=f"Torque {newData[1]:.3f} N-m\nSpeed {newData[2]:.3f} RPM"
                )
                last_visual_update = now
        except:
            logging.exception("")

    logging.debug("Stopping data record (saving to file)...")
    try:
        info_label.config(text="Cleaning up data...")
        ljm.eStreamStop(handle)  # Close Data stream from LJ
        ljm.close(handle)

        raw_rpm_data = [row[3] for row in data]
        timestamps = [row[0] for row in data]
        rpm_data = []
        num_zero_rows = (scanRate // engineScanRate - 1) // 2
        for i in range(0, num_zero_rows):
            rpm_data.append(0)
        for i in range(num_zero_rows, len(data) - num_zero_rows):
            ticks = raw_rpm_data[i - num_zero_rows : i + num_zero_rows]
            times = timestamps[i - num_zero_rows : i + num_zero_rows]

            result = [x / y for x, y in zip(ticks, times)]
            pps = mean(result)
            rpm_data.append(pps * engineRPMFactor)
        while len(rpm_data) < len(data):
            rpm_data.append(0)

        raw_rpm_data.clear()
        for i in range(len(data)):
            data[i][3] = rpm_data[i]
        rpm_data.clear()

        with open(current_filename, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(data)
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
