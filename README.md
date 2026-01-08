# LabJack-Dyno-Code

## Environment Setup

Make a virtual environment and run `pip isntall -r requirements.txt`

## Building

Run `pyinstaller --onefile --noconsole --name CobraLJTool -i icon.ico main.py`

## To-Dos and Notes

Currently using Command-Response, which is useful up to 1000 Hz (which is exactly what I'm running at). If additional speed is needed, I'll need to move to Streaming.