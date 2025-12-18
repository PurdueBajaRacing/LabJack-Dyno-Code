from labjack import ljm
import tkinter as tk
from tkinter import ttk
import os, time, csv
from datetime import datetime
import logging
from threading import Thread

VERSION = "0.0.1"

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

try:
    os.mkdir("data")
    logging.INFO(f"Data folder created successfully.")
except FileExistsError:
    pass
except:
    logging.exception("")

window = tk.Tk()
window.title("Dyno Labjack Interface")

# Open first found LabJack
try:
    handle = ljm.openS(
        "ANY", "ANY", "ANY"
    )  # Find the LJ: Any device, Any connection, Any identifier
    logging.INFO("Successfully connected to LabJack: ", handle)
except:
    logging.exception("")
    ID_label = tk.Label(window, text="No Labjack!")
    ID_label.pack()

    window.mainloop()

# TODO: Setup the Labjack

# Checks existing and creates new file name
filename_blank = "data/LJdata"
i = 0
filename = filename_blank + str(i) + ".csv"
while os.path.exists(filename):
    i += 1
    filename = filename_blank + str(i) + ".csv"

file_header = "Time, Shock Pot[V], Load Cell[V], Tie Rod[V]\n"  # Must be updated to match sensors eg. "Time, Sensor1, Sensor2"
f = open(filename, "w")
f.write(file_header)

ID_label = tk.Label(window, font=("Helvetica", 32))
