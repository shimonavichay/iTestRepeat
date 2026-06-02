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

VERSION = "0.4.04"  # Unified popup function

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


def _selectable_label(parent, text, family="Segoe UI", size=12, weight="normal", height=1):
    """Text widget styled like a Label but with selectable text."""
    widget = tk.Text(
        parent, font=(family, size, weight), height=height,
        width=max(len(line) for line in text.split("\n")) + 2,
        borderwidth=0, highlightthickness=0,
        background=parent.cget("bg"), wrap="none"
    )
    widget.insert("1.0", text)
    widget.configure(state="disabled")  # Read-only, but selection still works
    return widget


def _build_message_content(root, message, font=None):
    """Builds the layout for an info/error popup inside the given root window."""
    font = font or {}
    lines = message.split("\n")
    label = _selectable_label(root, message, **font, height=len(lines))
    label.grid(row=0, column=0, columnspan=2, padx=20, pady=20)

    def copy_all():
        root.clipboard_clear()
        root.clipboard_append(message)
    copy_button = ttk.Button(root, text="Copy", command=copy_all)
    copy_button.grid(row=1, column=0, padx=10, pady=10)

    close_button = ttk.Button(root, text="Close", command=root.destroy)
    close_button.grid(row=1, column=1, padx=10, pady=10)

    return label, copy_button, close_button


def _build_password_content(root, tests):
    """Builds the layout for a password popup inside the given root window.
    - Single test: shows 'Password: XXXX' with Copy and Close buttons
    - Multiple tests: shows one row per test, each with its own Copy button"""
    labels = {}
    if len(tests) == 1:
        test = tests[0]
        labels[0] = {"label":_selectable_label(root, f"Password: {test['password']}", size=14, weight="bold")}
        labels[0]["label"].grid(row=0, column=0, columnspan=2, padx=20, pady=20)

        def copy():
            root.clipboard_clear()
            root.clipboard_append(test["password"])
        labels[0]["Button"] = ttk.Button(root, text="Copy", command=copy)
        labels[0]["Button"].grid(row=1, column=0, padx=10, pady=10)

        close_button = ttk.Button(root, text="Close", command=root.destroy)
        close_button.grid(row=1, column=1, padx=10, pady=10)

    else:
        for i, test in enumerate(tests):
            # \u202B = RTL marker, fixes Hebrew rendering
            labels[i] = {"label":_selectable_label(root, f"\u202B{test['name']}: {test['password']}")}
            labels[i]["label"].grid(row=i, column=1, padx=20, pady=5, sticky="w")

            # p=test["password"] captures the value at loop time, not at click time.
            # Without this, all buttons would copy the last test's password.
            def copy(p=test["password"]):
                root.clipboard_clear()
                root.clipboard_append(p)

            labels[i]["Button"] = ttk.Button(root, text="Copy", command=copy)
            labels[i]["Button"].grid(row=i, column=0, padx=10, pady=5)

        close_button = ttk.Button(root, text="Close", command=root.destroy)
        close_button.grid(row=len(tests), column=0, columnspan=2, pady=10)

    return labels, close_button


def _popup_window(message=None, tests=None, error=False, TimeToClose=False, font=None):
    """The actual tkinter window. Runs inside the spawned process (or directly for blocking calls)."""
    root = tk.Tk()
    root.title("Exam Password" if tests else ("Error" if error else "Information"))
    root.resizable(False, False)
    root.attributes("-topmost", True)  # Always on top, so it's visible over iTest

    if tests:
        _build_password_content(root, tests)
    else:
        _build_message_content(root, message, font=font)

    # Position the window at the top-center of the screen
    root.update_idletasks()  # Required before winfo_screenwidth() returns correct values
    root.geometry(f"+{(root.winfo_screenwidth() - root.winfo_width()) // 2}+0")
    # Push it all the way to the other side of the screen, go back the length of the window,
    # then cut it in half to get to the center

    if TimeToClose:
        root.after(TimeToClose * 1000, root.destroy)  # TimeToClose is in seconds (messagebox doesn't support this)
    root.mainloop()


def popup(message=None, tests=None, error=False, TimeToClose=False, daemon=True, font=None):
    print("POPUP CALLED, message =", repr(message))
    """Spawns a separate process showing a popup window.
    - message: text for info/error popups
    - tests: list of test dicts for password popups (mutually exclusive with message)
    - error: if True, title is "Error", otherwise "Information" / "Exam Password"
    - TimeToClose: seconds before auto-close. If False/0, stays open until closed manually.
    - daemon: if False, popup survives after main process exits.
    Returns the spawned process so the caller can track/terminate it."""
    # Run popup in a separate process — tkinter windows are destroyed along
    # with the thread they were created in, so threading doesn't work here
    try:
        if message:
            print(f"messega: {message}")
    except Exception: # It's a non-critical debug aid. Don't block under any circumstance.
        pass  # No console available (windowed mode with no parent console).
    p = multiprocessing.Process(
        target=_popup_window,
        kwargs={
            "message": message,
            "tests": tests,
            "error": error,
            "TimeToClose": TimeToClose,
            "font": font,
        },
        daemon=daemon
    )
    p.start()
    return p


def create_example_csv(csv_path):
    """Creates an example CSV at csv_path with 2 example tests for today.
    Refuses to overwrite an existing file."""
    if os.path.exists(csv_path):
        msg = f"File already exists:\n{csv_path}\n\nDelete or rename it first."
        # daemon=False so the popup survives after this process exits
        popup(msg, error=True, TimeToClose=10, daemon=False)
        return

    today = date.today().strftime("%d/%m/%Y")
    try:
        with open(csv_path, "w", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "TestName", "Password"])
            writer.writerow([today, "Math Exam", "12345abc"])
            writer.writerow([today, "Physics Exam", "67890xyz"])
        popup(f"Example CSV created at:\n{csv_path}", TimeToClose=10, daemon=False)
    except Exception as e:
        popup(f"Failed to create CSV:\n{e}", error=True, TimeToClose=10, daemon=False)


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
            popup(f"CSV not found:\n{csv_path}", error=True, TimeToClose=10)
    return tests


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
        popup_process = popup(tests=tests)

    if OPEN: subprocess.Popen([PROGRAM_PATH])  # Launching the program


def main():
    exe_folder = get_exe_folder()

    HELP_ALIASES = ("-h", "--help", "-?")
    VERSION_ALIASES = ("-v", "--version")
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
        *VERSION_ALIASES,
        action="store_true",
        help="Show the version number and exit."
    )
    parser.add_argument(
        *HELP_ALIASES,
        action="store_true",
        dest="help",
        help="Show this help message and exit."
    )

    # Handle --help / --version manually so we can show them in a popup instead of stdout
    # (since the console may not be available in --noconsole compiled mode)
    if any(arg in sys.argv for arg in HELP_ALIASES):
        popup(message=parser.format_help(), font={"family": "Consolas"}, daemon=False)
        sys.exit()
    if any(arg in sys.argv for arg in VERSION_ALIASES):
        popup(message=f"iTestRepeat v{VERSION}", daemon=False)
        sys.exit()

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