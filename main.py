from labjack import ljm
import ttkbootstrap as ttk
import os, time, csv, sys, logging, queue
from threading import Thread
import numpy as np

# --- Configuration & Setup ---
VERSION = "1.1.0"
IS_EXE_MODE = getattr(sys, "frozen", False)
if IS_EXE_MODE:
    DATA_DIR = os.path.dirname(sys.executable) + "/data"
else:
    DATA_DIR = os.path.dirname(os.path.realpath(__file__)) + "/data"

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

NM_TO_FTLBS = 0.7375621493
TORQUE_CONVERSION = -20 * NM_TO_FTLBS
ENGINE_FACTOR = 60 / 20  # 20 pulses per rev
SCAN_RATE = 25_000
SCANS_PER_READ = 100  # Batch size

logging.basicConfig(
    filename="app.log",
    encoding="utf-8",
    filemode="a",
    format="{asctime}:{levelname}:{name}:{message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)


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
            "AIN2_RANGE",
            "AIN2_RESOLUTION_INDEX",
            "AIN2_NEGATIVE_CH",
            "AIN2_SETTLING_US",
            "STREAM_SETTLING_US",
            "DIO0_EF_ENABLE",
            "DIO0_EF_INDEX",
        ]
        aValues = [10, 0, 1, 0, 10, 0, 3, 0, 0, 0, 8]
        ljm.eWriteNames(handle, len(aNames), aNames, aValues)

        # Enable Interrupt Counter
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
    aScanListNames = ["AIN0", "AIN2", "DIO0_EF_READ_A", "STREAM_DATA_CAPTURE_16"]
    numChannels = len(aScanListNames)
    aScanList = ljm.namesToAddresses(numChannels, aScanListNames)[0]

    data_queue = queue.Queue()

    def consumer_worker():
        """Processes the queue, performs math, and writes to disk."""
        sample_count = 0
        last_engine_count = 0
        visual_tick_sum = 0
        inverse_scan_rate = 1.0 / actualScanRate
        last_visual_update = 0

        with open(current_filename, "a", newline="") as f:
            writer = csv.writer(f)

            while loggingState == 1 or not data_queue.empty():
                try:
                    # Get batch from producer
                    batch_data = data_queue.get(timeout=0.2)

                    # --- Setup for the calculation ---
                    # Convert batch_data to a numpy array immediately.
                    # Using float64 ensures precision for the time and converted values.
                    batch_arr = np.array(batch_data)
                    num_scans = len(batch_arr) // numChannels

                    # 1. Reshape into (Scans, Channels)
                    # This allows us to slice by column: data[:, 0], data[:, 1], etc.
                    data = batch_arr.reshape(num_scans, numChannels)

                    # 2. Timing (Vectorized)
                    # np.arange creates [0, 1, 2, ... num_scans-1]
                    # Adding sample_count shifts it to the current hardware tick
                    precise_times = (
                        np.arange(num_scans) + sample_count
                    ) * inverse_scan_rate

                    # 3. Conversions
                    torques = data[:, 0] * TORQUE_CONVERSION
                    shaft_rpms = np.maximum(0, data[:, 1] * 1200)

                    # 4. Engine RPM
                    col2 = data[:, 2]
                    col3 = data[:, 3]
                    raw_engine_counts = col2.astype(np.int64) + (
                        col3.astype(np.int64) << 16
                    )

                    # To get deltas, we need the last value from the PREVIOUS batch
                    # We stack the last_engine_count at the front of our current array
                    counts_with_bridge = np.concatenate(
                        ([last_engine_count], raw_engine_counts)
                    )
                    delta_ticks = np.diff(counts_with_bridge)

                    engine_rpms = delta_ticks * (actualScanRate * ENGINE_FACTOR)

                    # 5. Final Assembly
                    # This creates a 2D array where each row is [time, torque, rpm, engine_rpm]
                    processed_batch = np.column_stack(
                        (precise_times, torques, shaft_rpms, engine_rpms)
                    )

                    # 6. Update State for the next iteration
                    sample_count += num_scans
                    last_engine_count = raw_engine_counts[-1]
                    visual_tick_sum += np.sum(delta_ticks)
                    latest_torque = processed_batch[-1, 1]
                    latest_shaft_rpm = processed_batch[-1, 2]

                    # --- AFTER THE LOOP (Efficient Disk I/O) ---
                    writer.writerows(processed_batch)

                    now = time.time()
                    if now - last_visual_update > 0.1:
                        engine_rpm_average = (
                            visual_tick_sum / (now - last_visual_update)
                        ) * ENGINE_FACTOR

                        # Define a small helper function for the update
                        def update_ui():
                            info_label.config(
                                text=f"Torque: {latest_torque:.2f} Ft-Lbs\n"
                                f"Shaft: {latest_shaft_rpm:.2f} RPM\n"
                                f"Engine: {engine_rpm_average:.2f} RPM"
                            )

                        # Schedule the helper to run on the MAIN thread
                        window.after(0, update_ui)

                        last_visual_update = now
                        visual_tick_sum = 0

                    data_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    logging.error(f"Consumer Error: {e}")

    # --- PRODUCER (High-Priority Stream) ---
    try:
        # Reset counter before start
        ljm.eReadName(handle, "DIO0_EF_READ_A_AND_RESET")

        # Start Stream
        actualScanRate = ljm.eStreamStart(
            handle, SCANS_PER_READ, numChannels, aScanList, SCAN_RATE
        )
        logging.info(f"Stream started at actual rate: {actualScanRate} Hz")

        # Start the Consumer Thread
        consumer_thread = Thread(target=consumer_worker, daemon=True)
        consumer_thread.start()

        while loggingState == 1:
            # Blocking call: waits for 'SCANS_PER_READ' to be ready in hardware buffer
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
