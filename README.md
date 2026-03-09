# LabJack-Dyno-Code

## Usage

1. You'll want to download and install the [Normal LJM Installer](https://support.labjack.com/docs/ljm-software-installer-windows)
2. You can find packaged `.exe`s under "Releases" (right-hand side, I hope you're running Windows!). Download and run it (if a SmartScreen warning comes up, hit "Run Anyway").
3. Assuming the Labjack is found (you'll see warnings if you don't), you should see a "Start" and "Stop" button. I _really_ hope you can guess which button to press to start recording data.
4. The data files will be saved AFTER recording is stopped (it may take a moment to finish saving, there's quite a bit of cleanup in the background). It'll be in a `data` folder in the same place as the `.exe` file.

## To-Dos and Notes

- [X] Test it with a potentiometer (actually screwed in)
- [ ] Test with the load cell
- [X] Upload `.exe` files to releases
- [X] Test `.exe`s with other computers

Should be ready for v0.1 soon!

Because all of the data is stored in memory, you shouldn't run tests *too* long.

---

## Environment Setup and Packaging (if you're making changes)

Make a virtual environment and run `pip install -r requirements.txt`

To package, run `pyinstaller --onefile --noconsole --name CobraLJTool -i icon.ico main.py`

Using [UPX compression](https://coderslegacy.com/python/pyinstaller-upx/) can be useful to reduce file size