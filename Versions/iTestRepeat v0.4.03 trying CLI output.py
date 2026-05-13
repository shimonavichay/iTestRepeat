# iTestRepeat - Automatic iTest Launcher with Exam Password Display
# Monitors whether iTest is running and relaunches it if it closes.
# Optionally reads today's exam passwords from a CSV and displays them in a popup.

import psutil           # For checking running processes
import subprocess       # For launching iTest
import time             # For the sleep between checks
import csv              # For reading the tests CSV
import tkinter as tk    # For the password and error popups
from tkinter import ttk
from datetime import date
import multiprocessing  # For running popups in a separate process (tkinter in a thread gets closed when the exe gets closed)
import argparse         # For command line arguments
import sys
import os
import ctypes

VERSION = "0.4.03"  # Added: information args
#test: Added a delay to init_csv for debugging
#testing a solution of Claude Code

if __name__ == "__main__":
    if ctypes.windll.kernel32.AttachConsole(-1):  # -1 means "attach to parent process console"
        try:
            import io
            _conout = open('CONOUT$', 'wb', buffering=0)
            sys.stdout = io.TextIOWrapper(_conout, encoding='utf-8', errors='replace', line_buffering=True)
            sys.stderr = sys.stdout
        except Exception:
            pass  # Can't display this error, but at least we don't crash silently on a bad open()
#PARENT = psutil.Process(os.getppid()).name()
#HAS_TERMINAL = PARENT not in ("explorer.exe",)
# The last 2 lines are in case I'd want to destinguish, so I'll have the lines Claude suggested to test and use.

PROGRAM_PATH = r"C:\Program Files (x86)\CET\iTest\iTestLauncher.exe"
PROCESS_NAME = "iTestLauncher.exe"  # Must match the exact process name shown in Task Manager
MAX_LOOPS = None                                         # but if it's a double-click on the file - stop after 5 loops
OPEN = True # For testing. In develepment we won't neccecery want the proggram to open every time

def get_exe_folder():
    """Returns the folder where the exe (or script) is located.
    Needed because the 'current folder' depends on how the program was launched,
    which may differ from the exe's actual location."""
    global MAX_LOOPS
    global OPEN
    if getattr(sys, 'frozen', False):
        # Running as a compiled exe (PyInstaller sets sys.frozen = True)
        return os.path.dirname(sys.executable)
    else:
        # Running as a plain Python script
        MAX_LOOPS = 5
        OPEN = False
        return os.path.dirname(os.path.abspath(__file__))


def create_example_csv(csv_path):
    """Creates an example CSV at csv_path with 2 example tests for today.
    Refuses to overwrite an existing file."""
    if os.path.exists(csv_path):
        msg = f"File already exists:\n{csv_path}\n\nDelete or rename it first."
        print(msg)
        # daemon=False so the popup survives after this process exits
        p = multiprocessing.Process(target=information_popup, args=(msg,) kwargs={"error": True}, daemon=False)
        p.start()
        return

    today = date.today().strftime("%d/%m/%Y")
    try:
        with open(csv_path, "w", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "TestName", "Password"])
            writer.writerow([today, "Math Exam", "12345abc"])
            writer.writerow([today, "Physics Exam", "67890xyz"])
        msg = f"Example CSV created at: {csv_path}"
        print(msg)
        p = multiprocessing.Process(target=information_popup, args=(msg,) kwargs={"error": True}, daemon=False)
        p.start()
    except Exception as e:
        msg = f"Failed to create CSV:\n{e}"
        print(msg)
        p = multiprocessing.Process(target=information_popup, args=(msg,) kwargs={"error": True}, daemon=False)
        p.start()


def get_todays_tests(csv_path, csv_specified):
    """Reads the CSV and returns a list of today's tests as dicts: {name, password}.
    If the file isn't found and the user specified the path explicitly, shows an error popup.
    If no path was specified, silently ignores the missing file (it may just not needed)."""
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
            # Run error popup in a separate process so it doesn't block iTest from launching
            p = multiprocessing.Process(target=information_popup, args=(f"CSV not found:\n{csv_path}",),
            kwargs={"error": True, "TimeToClose": 10000}, daemon=True)
            p.start()
    return tests


def passwords_popup(tests):
    """Displays a topmost window with today's exam passwords.
    - Single test: shows 'Password: XXXX' with Copy and Close buttons
    - Multiple tests: shows one row per test, each with its own Copy button"""
    root = tk.Tk()
    root.title("Exam Password")
    root.resizable(False, False)
    root.attributes("-topmost", True)  # Always on top, so it's visible over iTest

    # Position the window at the top-center of the screen
    root.update_idletasks()  # Required before winfo_screenwidth() returns correct values
    root.geometry(f"+{(root.winfo_screenwidth() - root.winfo_width()) // 2}+0")
    # Push it all the way to the other side of the screen, go back the length of the window,
    # then cut it in half to get to the center

    if len(tests) == 1:
        test = tests[0]

        tk.Label(root, text=f"Password: {test['password']}",
                 font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, padx=20, pady=20)

        def copy():
            root.clipboard_clear()
            root.clipboard_append(test["password"])

        ttk.Button(root, text="Copy", command=copy).grid(row=1, column=0, padx=10, pady=10)
        ttk.Button(root, text="Close", command=root.destroy).grid(row=1, column=1, padx=10, pady=10)

    else:
        for i, test in enumerate(tests):
            tk.Label(root, text=f"\u202B{test['name']}: {test['password']}", # \u202B = RTL marker, fixes Hebrew rendering
                     font=("Segoe UI", 12)).grid(row=i, column=0, padx=20, pady=5, sticky="w")

            # p=test["password"] captures the value at loop time, not at click time.
            # Without this, all buttons would copy the last test's password.
            def copy(p=test["password"]):
                root.clipboard_clear()
                root.clipboard_append(p)

            ttk.Button(root, text="Copy", command=copy).grid(row=i, column=1, padx=10, pady=5)

        ttk.Button(root, text="Close", command=root.destroy).grid(
            row=len(tests), column=0, columnspan=2, pady=10)

    root.mainloop()


def information_popup(message, error=False, TimeToClose=False):
    """Displays a topmost information or error popup.
    - error=True: title is "Error", otherwise "Information"
    - TimeToClose: seconds before auto-close. If False/0, stays open until closed manually.
    Runs in its own process so it doesn't block the main loop."""
    root = tk.Tk()
    root.title("Error" if error else "Information")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    # Text widget instead of Label so the user can select and copy parts of the message manually
    lines = message.split("\n")
    text_widget = tk.Text(
        root,
        font=("Segoe UI", 12),
        height=len(lines),
        width=max(len(line) for line in lines) + 2,
        borderwidth=0,
        highlightthickness=0,
        background=root.cget("bg"),
        wrap="none",
        padx=20,
        pady=20
    )
    text_widget.insert("1.0", message)
    text_widget.configure(state="disabled")  # Read-only, but selection still works
    text_widget.grid(row=0, column=0, columnspan=2)

    root.update_idletasks()
    root.geometry(f"+{(root.winfo_screenwidth() - root.winfo_width()) // 2}+0")

    ttk.Button(root, text="Close", command=root.destroy).grid(row=1, column=0, padx=10, pady=10)

    def copy_all():
        root.clipboard_clear()
        root.clipboard_append(message)
    ttk.Button(root, text="Copy", command=copy_all).grid(row=1, column=1, padx=10, pady=10)

    if TimeToClose:
        root.after(TimeToClose * 1000, root.destroy) # Converting seconds to miliseconds for self terminate pop-up if needed
    root.mainloop()


popup_process = None  # Tracks the current password popup process so we can close it before reopening


def is_running():
    """Returns True if iTest is currently in the process list."""
    return any(p.name() == PROCESS_NAME for p in psutil.process_iter())


def launch(csv_path, csv_specified):
    """Closes any existing password popup, shows a new one with today's passwords, then launches iTest."""
    global popup_process

    # Close previous popup if still open
    if popup_process is not None and popup_process.is_alive():
        popup_process.terminate()

    tests = get_todays_tests(csv_path, csv_specified)
    if tests:
        # Run popup in a separate process — tkinter windows are destroyed along
        # with the thread they were created in, so threading doesn't work here
        popup_process = multiprocessing.Process(target=passwords_popup, args=(tests,), daemon=True)
        popup_process.start()

    if OPEN: subprocess.Popen([PROGRAM_PATH])  # Launching the program


def main():
    exe_folder = get_exe_folder()

    parser = argparse.ArgumentParser(
        prog="iTestRepeat",
        description=f"iTestRepeat v{VERSION} - Automatic iTest Launcher with Exam Password Display",
        epilog=(
            r"Examples:" "\n"
            r"  iTestRepeat.exe" "\n"
            r'  iTestRepeat.exe --csv "tests.csv"' "\n"
            r'  iTestRepeat.exe --csv "Z:\Admin\tests.csv"' "\n"
            r'  iTestRepeat.exe --csv "\\fileserver\Exams\tests.csv"' "\n"
            r"  iTestRepeat.exe --stop" "\n"
            r"  iTestRepeat.exe --version" "\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,  # Preserves newlines in epilog
        add_help=False  # We add it manually below so we can include -? as an alias
    )
    parser.add_argument(
        "--csv",
        metavar="PATH",
        help="Path to the tests CSV file. Can be relative or absolute.\n"
             "Default: tests.csv in the same folder as the exe.",
        default=None
    )
    parser.add_argument(
        "--init-csv",
        action="store_true",
        help="Create an example CSV with 2 sample tests for today's date.\n"
             "Uses the --csv path if provided, otherwise creates tests.csv next to the exe."
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop the running instance of iTestRepeat."
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"%(prog)s {VERSION}",
        help="Show the version number and exit."
    )
    parser.add_argument(
        "-h", "--help", "-?",
        action="help",
        help="Show this help message and exit."
    )
    args = parser.parse_args()

    # Stop mode — kill this exe by name and exit
    if args.stop:
        exe_name = os.path.basename(sys.executable)
        subprocess.run(["taskkill", "/IM", exe_name, "/F"])
        sys.exit()

    csv_specified = args.csv is not None
    csv_path = args.csv if csv_specified else os.path.join(exe_folder, "tests.csv")

    # Init mode — create example CSV and exit
    if args.init_csv:
        time.sleep(10)
        create_example_csv(csv_path)
        sys.exit()

    i = 0
    while True:
        i += 1
        print(f"loop {i}")
        if not is_running():
            launch(csv_path, csv_specified)
        time.sleep(3)
        if MAX_LOOPS and i >= MAX_LOOPS:
            break


if __name__ == "__main__":
    multiprocessing.freeze_support()  # Required for multiprocessing to work inside a PyInstaller exe
    main()