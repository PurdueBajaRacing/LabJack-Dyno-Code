from labjack import ljm
import ttkbootstrap as ttk
import os, time, csv, sys, logging, queue
from threading import Thread

# --- Configuration & Setup ---
VERSION = "1.0.4"
IS_EXE_MODE = getattr(sys, "frozen", False)
if IS_EXE_MODE:
    DATA_DIR = os.path.dirname(sys.executable) + "/data"
else:
    DATA_DIR = os.path.dirname(os.path.realpath(__file__)) + "/data"

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

NM_TO_FTLBS = 0.7376

logging.basicConfig(
    filename="app.log",
    encoding="utf-8",
    filemode="a",
    format="{asctime}:{levelname}:{name}:{message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)

# --- Functions ---


def openLabJack():
    """Opens and configures the T7 for streaming."""
    try:
        handle = ljm.openS("T7", "ANY", "ANY")

        # Initial configurations
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
        aValues = [
            10,
            0,
            ljm.constants.GND,
            500,
            10,
            0,
            ljm.constants.GND,
            500,
            10,
            0,
            ljm.constants.GND,
            500,
            450,
            0,
            8,
        ]
        ljm.eWriteNames(handle, len(aNames), aNames, aValues)

        # Enable High Speed Counter
        ljm.eWriteName(handle, "DIO0_EF_ENABLE", 1)
        return handle
    except Exception:
        logging.exception("LabJack Connection Error")
        return None


def makeNewFile():
    """Finds the next available filename."""
    i = 0
    while os.path.exists(os.path.join(DATA_DIR, f"LJdata{i}.csv")):
        i += 1
    full_path = os.path.join(DATA_DIR, f"LJdata{i}.csv")

    with open(full_path, "w") as f:
        f.write("Time (s),Torque (Ft-Lbs),Shaft Speed (RPM),Engine Speed (RPM)\n")
    return full_path


def start_log():
    global loggingState
    if loggingState:
        return

    loggingState = 1
    info_label.config(text="Initializing...", bootstyle="info")

    current_filename = makeNewFile()
    handle = openLabJack()
    if handle is None:
        info_label.config(text="No LabJack Found", bootstyle="danger")
        loggingState = 0
        return

    # Stream Constants
    aScanListNames = [
        "AIN0",
        "AIN1",
        "AIN2",
        "DIO0_EF_READ_A",
        "STREAM_DATA_CAPTURE_16",
    ]
    numChannels = len(aScanListNames)
    aScanList = ljm.namesToAddresses(numChannels, aScanListNames)[0]
    scanRate = 1000  # Hz
    scansPerRead = 20  # Batch size (Read 50 times per second)

    data_queue = queue.Queue()

    def consumer_worker():
        """Processes the queue, performs math, and writes to disk."""
        sample_count = 0
        last_engine_count = 0
        engine_factor = 60 / 20  # 20 pulses per rev
        last_ui_update = 0
        visual_tick_sum = 0

        with open(current_filename, "a", newline="") as f:
            writer = csv.writer(f)

            while loggingState == 1 or not data_queue.empty():
                try:
                    # Get batch from producer
                    batch_data = data_queue.get(timeout=0.2)
                    num_scans_in_batch = len(batch_data) // numChannels

                    for i in range(num_scans_in_batch):
                        # 1. HARDWARE-ALIGNED TIMING
                        # Use the sample index to guarantee perfect 1000Hz increments
                        precise_time = sample_count * (1.0 / scanRate)

                        # 2. DATA EXTRACTION
                        start_idx = i * numChannels
                        row = batch_data[start_idx : start_idx + numChannels]

                        # 3. CALCULATIONS
                        torque = (row[0] - row[1]) * -20 * NM_TO_FTLBS
                        shaft_rpm = max(0, (row[2] - row[1]) * 1200)

                        # Engine RPM (Counter logic)
                        raw_engine_count = row[3] + (row[4] * 65536)
                        delta_ticks = raw_engine_count - last_engine_count
                        last_engine_count = raw_engine_count

                        # RPM = (pulses / time_between_scans) * factor
                        engine_rpm = (delta_ticks * scanRate) * engine_factor
                        visual_tick_sum += delta_ticks

                        # 4. DISK I/O
                        writer.writerow(
                            [
                                f"{precise_time:.4f}",
                                f"{torque}",
                                f"{shaft_rpm}",
                                f"{engine_rpm}",
                            ]
                        )

                        # 5. UI THROTTLED UPDATE (10Hz)
                        if time.time() - last_ui_update > 0.1:
                            engine_rpm_average = (
                                visual_tick_sum
                                / (time.time() - last_ui_update)
                                * engine_factor
                            )
                            visual_tick_sum = 0

                            info_label.config(
                                text=f"Torque: {torque:.2f} Ft-Lbs\nShaft: {shaft_rpm:.2f} RPM\nEngine: {engine_rpm_average:.2f} RPM\nCVT Ratio: {engine_rpm_average/shaft_rpm:.2f}"
                            )
                            last_ui_update = time.time()

                        sample_count += 1

                    data_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    logging.error(f"Consumer Error: {e}")

    # Start the Consumer Thread
    consumer_thread = Thread(target=consumer_worker, daemon=True)
    consumer_thread.start()

    # --- PRODUCER (High-Priority Stream) ---
    try:
        # Reset counter before start
        ljm.eReadName(handle, "DIO0_EF_READ_A_AND_RESET")

        # Start Stream
        actualScanRate = ljm.eStreamStart(
            handle, scansPerRead, numChannels, aScanList, scanRate
        )
        logging.info(f"Stream started at actual rate: {actualScanRate} Hz")

        while loggingState == 1:
            # Blocking call: waits for 'scansPerRead' to be ready in hardware buffer
            ret = ljm.eStreamRead(handle)
            data_queue.put(ret[0])

    except Exception:
        logging.exception("Stream Loop Interrupted")
    finally:
        # Graceful Shutdown
        time.sleep(0.2)  # Allow consumer to catch up
        ljm.eStreamStop(handle)
        ljm.close(handle)
        loggingState = 0
        info_label.config(text="Logging Stopped. File Saved.", bootstyle="success")


def stop_log():
    global loggingState
    if loggingState == 1:
        loggingState = 2  # Signal to stop
        info_label.config(text="Finalizing data...", bootstyle="warning")


# --- UI Setup ---
loggingState = 0

window = ttk.Window(themename="darkly")
window.title(f"Labjack-Dyno Interface v{VERSION}")
window.geometry("500x470")

s = ttk.Style()
s.configure(".", font=("Helvetica", 18))

title_label = ttk.Label(
    window, text="Cobra Dyno Logger", font=("Helvetica", 24, "bold")
)
title_label.pack(pady=20)

button_start = ttk.Button(
    window,
    text="START LOGGING",
    width=25,
    command=lambda: Thread(target=start_log).start(),
    bootstyle="success-outline",
)
button_start.pack(pady=10)

button_stop = ttk.Button(
    window, text="STOP", width=25, command=stop_log, bootstyle="danger-outline"
)
button_stop.pack(pady=10)

info_label = ttk.Label(window, text="Ready to Record", justify="center")
info_label.pack(pady=40)

window.mainloop()
