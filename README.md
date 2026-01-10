# LabJack-Dyno-Code

## Usage

1. You'll want to download and install the [Normal LJM Installer](https://support.labjack.com/docs/ljm-software-installer-windows)
2. You can find packaged `.exe`s under "Releases" (right-hand side, I hope you're running Windows!). Download and run it (if a SmartScreen warning comes up, hit "Run Anyway").
3. Assuming the Labjack is found (you'll see warnings if you don't), you should see a "Start" and "Stop" button. I _really_ hope you can guess which button to press to start recording data.
4. The data files will be saved AFTER recording is stopped. It'll be in a `data` folder in the same place as the `.exe` file.

## To-Dos and Notes

Still need to test the thing and upload the `.exe` file.

Currently using Command-Response, which is useful up to 1000 Hz (which is exactly what I'm running at). If additional speed is needed, I'll need to move to Streaming.

---

## Environment Setup and Packaging (if you're making changes)

Make a virtual environment and run `pip install -r requirements.txt`

To package, run `pyinstaller --onefile --noconsole --name CobraLJTool -i icon.ico main.py`
