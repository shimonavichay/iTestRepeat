import psutil
import subprocess
import time

PROGRAM_PATH = r"C:\Program Files (x86)\CET\iTest\iTestLauncher.exe"
PROCESS_NAME = "iTestLauncher.exe"

def is_running():
    return any(p.name() == PROCESS_NAME for p in psutil.process_iter())

def launch():
    subprocess.Popen([PROGRAM_PATH])

def main():

    while True:
        if not is_running():
            launch()
        time.sleep(3)  # Check every 3 seconds

if __name__ == "__main__":
    main()
