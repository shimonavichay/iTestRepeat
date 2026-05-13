# Version: 0.1
import psutil
import subprocess
import time
import csv
import tkinter as tk
from tkinter import ttk
from datetime import date
import multiprocessing

PROGRAM_PATH = r"C:\Program Files (x86)\CET\iTest\iTestLauncher.exe"
PROCESS_NAME = "iTestLauncher.exe"
CSV_PATH = r"H:\Python compiling tests\tests.csv"


def get_todays_tests():
    today = date.today().strftime("%d/%m/%Y")
    tests = []
    with open(CSV_PATH, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["Date"] == today:
                tests.append({"name": row["TestName"], "password": row["Password"]})
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


popup_process = None

def is_running():
    return any(p.name() == PROCESS_NAME for p in psutil.process_iter())


def launch():
    global popup_process

    if popup_process is not None and popup_process.is_alive():
        popup_process.terminate()

    tests = get_todays_tests()
    if tests:
        popup_process = multiprocessing.Process(target=show_popup, args=(tests,), daemon=True)
        popup_process.start()

    subprocess.Popen([PROGRAM_PATH])


def main():
    i = 0
    while True:
        i += 1
        print(f"loop {i}")
        if not is_running():
            launch()
        time.sleep(3)


if __name__ == "__main__":
    multiprocessing.freeze_support()  # Required for PyInstaller
    main()