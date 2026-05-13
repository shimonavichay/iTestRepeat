import psutil
import subprocess
import time
import csv
import tkinter as tk
from tkinter import ttk
from datetime import date
import multiprocessing
import argparse
import sys
import os

VERSION = "0.2" #CSV path argument

PROGRAM_PATH = r"C:\Program Files (x86)\CET\iTest\iTestLauncher.exe"
PROCESS_NAME = "iTestLauncher.exe"


def get_exe_folder():
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        return os.path.dirname(sys.executable)
    else:
        # Running as plain python script
        return os.path.dirname(os.path.abspath(__file__))


def get_todays_tests(csv_path, csv_specified):
    today = date.today().strftime("%d/%m/%Y")
    tests = []
    try:
        with open(csv_path, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["Date"] == today:
                    tests.append({"name": row["TestName"], "password": row["Password"]})
    except FileNotFoundError:
        if csv_specified:
            p = multiprocessing.Process(target=show_error, args=(f"CSV not found:\n{csv_path}",), daemon=True)
            p.start()
    return tests


def show_popup(tests):
    root = tk.Tk()
    root.title("Exam Password")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    root.geometry(f"+{screen_width // 2 - 160}+0")

    if len(tests) == 1:
        test = tests[0]

        tk.Label(root, text=f"Password: {test['password']}",
                 font=("Arial", 14, "bold")).grid(row=0, column=0, columnspan=2, padx=20, pady=20)

        def copy():
            root.clipboard_clear()
            root.clipboard_append(test["password"])

        ttk.Button(root, text="Copy", command=copy).grid(row=1, column=0, padx=10, pady=10)
        ttk.Button(root, text="Close", command=root.destroy).grid(row=1, column=1, padx=10, pady=10)

    else:
        for i, test in enumerate(tests):
            tk.Label(root, text=f"{test['name']}: {test['password']}",
                     font=("Arial", 12)).grid(row=i, column=0, padx=20, pady=5, sticky="w")

            def copy(p=test["password"]):
                root.clipboard_clear()
                root.clipboard_append(p)

            ttk.Button(root, text="Copy", command=copy).grid(row=i, column=1, padx=10, pady=5)

        ttk.Button(root, text="Close", command=root.destroy).grid(
            row=len(tests), column=0, columnspan=2, pady=10)

    root.mainloop()

def show_error(message):
    root = tk.Tk()
    root.title("Error")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    root.geometry(f"+{screen_width // 2 - 160}+0")

    tk.Label(root, text=message, font=("Arial", 12), padx=20, pady=20).grid(row=0, column=0, columnspan=2)
    ttk.Button(root, text="Close", command=root.destroy).grid(row=1, column=0, padx=10, pady=10)

    root.after(10000, root.destroy)  # Auto-close after 10 seconds
    root.mainloop()

popup_process = None

def is_running():
    return any(p.name() == PROCESS_NAME for p in psutil.process_iter())


def launch(csv_path, csv_specified):
    global popup_process

    if popup_process is not None and popup_process.is_alive():
        popup_process.terminate()

    tests = get_todays_tests(csv_path, csv_specified)
    if tests:
        popup_process = multiprocessing.Process(target=show_popup, args=(tests,), daemon=True)
        popup_process.start()

    subprocess.Popen([PROGRAM_PATH])


def main():
    parser = argparse.ArgumentParser(description=f"iTest Repeat Launcher v{VERSION}")
    parser.add_argument("--csv", help="Path to the tests CSV file (default: tests.csv next to the exe)", default=None)
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = parser.parse_args()

    csv_specified = args.csv is not None
    csv_path = args.csv if csv_specified else os.path.join(get_exe_folder(), "tests.csv")

    i = 0
    while True:
        i += 1
        print(f"loop {i}")
        if not is_running():
            launch(csv_path, csv_specified)
        time.sleep(3)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()