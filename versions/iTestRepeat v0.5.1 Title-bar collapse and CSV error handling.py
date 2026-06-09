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
import sys              # For sys.argv, sys.exit, sys.executable, sys.frozen
import os               # For path handling and reading the exe's own location

VERSION = "0.5.1"  # Title-bar X collapses instead of closing; broader CSV read-error handling
DESC = "Title-bar collapse and CSV error handling"

PROGRAM_PATH = r"C:\Program Files (x86)\CET\iTest\iTestLauncher.exe"
PROCESS_NAME = "iTestLauncher.exe"  # Must match the exact process name shown in Task Manager
OPEN = True       # Whether to actually launch iTest; get_exe_folder() sets it False in script mode (for testing)

# Hebrew UI strings — centralized so they're easy to find and edit (and to localize later)
HE = {
    "password_title": "סיסמאות למבחן",
    "password_label": "סיסמה",
    "col_name": "שם המבחן",
    "col_password": "סיסמה",
    "col_copy": "העתקה",
    "copy": "העתק",
    "collapse": "מזער",
    "expand": "הצג סיסמאות",
    # CSV read errors
    "err_not_found": "קובץ הסיסמאות לא נמצא:",
    "err_encoding": "קובץ הסיסמאות אינו בקידוד הנכון (נדרש UTF-8):",
    "err_permission": "אין הרשאה לקרוא את קובץ הסיסמאות (אולי הוא פתוח בתוכנה אחרת?):",
    "err_generic": "לא ניתן לקרוא את קובץ הסיסמאות:",
}


def get_exe_folder():
    """Returns the folder where the exe (or script) is located.
    Needed because the 'current folder' depends on how the program was launched,
    which may differ from the exe's actual location.
    Also sets OPEN = False when running as a script (so testing doesn't launch iTest)."""
    global OPEN
    if getattr(sys, 'frozen', False):
        # Running as a compiled exe (PyInstaller sets sys.frozen = True)
        return os.path.dirname(sys.executable)
    else:
        # Running as a plain Python script — don't actually launch iTest
        OPEN = False
        return os.path.dirname(os.path.abspath(__file__))

def _detect_justify(text):
    """Returns 'right' if the first letter in the text is Hebrew, else 'left'.
    Skips digits, spaces, and punctuation — only the first real letter decides."""
    for ch in text:
        if ch.isalpha():  # first letter — decide based on it
            # Hebrew block is U+0590–U+05FF
            return "right" if "\u0590" <= ch <= "\u05FF" else "left"
    return "left"  # no letters at all (e.g. a pure-number password) → default left

def _selectable_label(parent, text, family="Segoe UI", size=12, weight="normal", height=1,
                      justify=None, width=0, select_all_on_click=False):
    """Text widget styled like a Label but with selectable text.
    family/size/weight default to the standard popup font; pass overrides to change them.
    justify: internal text alignment. If None, auto-detected from the first letter
             ('right' for Hebrew, 'left' otherwise).
    width: fixed character width. If 0, sizes to the widget's own text (per-widget).
    select_all_on_click: if True, clicking the widget selects its entire content
                         (used in the password popup so one click grabs the value)."""
    if justify is None:
        justify = _detect_justify(text)

    # RTL text needs the embedding marker so mixed content (e.g. "3 יחידות") renders in visual order.
    # Done here (not by the caller) so direction detection and the marker stay in one place.
    if justify == "right" and not text.startswith("\u202B"):
        text = "\u202B" + text

    if width == 0:
        width = max(len(line) for line in text.split("\n")) + 2  # default: size to own content
    widget = tk.Text(
        parent, font=(family, size, weight), height=height, width=width,
        borderwidth=0, highlightthickness=0,
        background=parent.cget("bg"), wrap="none"
    )
    widget.insert("1.0", text)
    widget.tag_configure("align", justify=justify)
    widget.tag_add("align", "1.0", "end")
    widget.configure(state="disabled")  # Read-only, but selection still works

    if select_all_on_click:
        def _select_all(event):
            event.widget.tag_add("sel", "1.0", "end-1c")  # -1c skips the trailing newline Text auto-appends
            event.widget.focus_set()
            return "break"  # stop the default click handler from clearing the selection we just set
        widget.bind("<Button-1>", _select_all)

    return widget

def _build_message_content(root, message, font=None):
    """Builds the layout for an info/error popup inside the given root window.
    font: optional dict of _selectable_label kwargs (family/size/weight).
    Returns (label, copy_button, close_button)."""
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


def _collapse(main_window):
    """Hides the main popup and shows a small borderless always-on-top bar to bring it back.
    The bar has no native title bar (no close/minimize) — a grip handle lets the user drag it."""
    main_window.withdraw()  # Hide without destroying — all data/widgets stay in memory

    bar = tk.Toplevel()
    bar.attributes("-topmost", True)
    bar.resizable(False, False)
    bar.overrideredirect(True)  # Remove the native title bar entirely (no close/minimize, frees the space)

    def expand():
        bar.destroy()
        main_window.deiconify()  # Bring the main window back

    # Manual dragging, since overrideredirect removes the normal drag-by-titlebar.
    # On press we record where the cursor sits *within* the window; on motion we keep
    # that same offset, so the window follows the cursor without jumping.
    drag = {"x": 0, "y": 0}

    def start_drag(event):
        drag["x"] = event.x_root - bar.winfo_x()  # x_root = absolute screen X of the cursor
        drag["y"] = event.y_root - bar.winfo_y()

    def do_drag(event):
        bar.geometry(f"+{event.x_root - drag['x']}+{event.y_root - drag['y']}")

    grip = tk.Label(bar, text="\u2807", cursor="fleur", padx=8)  # ⠇ braille dots as a grab handle
    grip.pack(side="left")
    grip.bind("<Button-1>", start_drag)
    grip.bind("<B1-Motion>", do_drag)

    ttk.Button(bar, text=HE["expand"], command=expand).pack(side="left", padx=2, pady=2)

    bar.update_idletasks()
    bar.geometry(f"+{(bar.winfo_screenwidth() - bar.winfo_width()) // 2}+0")  # Top-center, like the main popup

def _build_password_content(root, tests):
    """Builds the password popup layout inside root.
    - Single test: label cell ('סיסמה') + password cell + copy button, no header
    - Multiple tests: header row + one row per test (name + password + copy button)
    Returns (labels_dict, collapse_button)."""
    labels = {}

    def make_copy(password):
        """Returns a copy-to-clipboard function bound to this specific password.
        (A factory avoids the late-binding trap where every button copies the last password.)"""
        def copy():
            root.clipboard_clear()
            root.clipboard_append(password)
        return copy

    # The collapse button is identical in both branches — only its grid position differs
    collapse_button = ttk.Button(root, text=HE["collapse"], command=lambda: _collapse(root))

    if len(tests) == 1:
        test = tests[0]
        # Layout mirrors the multi-test table (no header): copy | password | label
        # No \u202B / justify passed — _selectable_label auto-detects direction per cell
        labels[0] = {
            "Button": ttk.Button(root, text=HE["copy"], command=make_copy(test["password"])),
            "password": _selectable_label(root, test["password"], size=14, weight="bold", select_all_on_click=True),
            "label": _selectable_label(root, f"{HE['password_label']}:", size=14, weight="bold", select_all_on_click=True),
        }
        labels[0]["Button"].grid(row=0, column=0, padx=10, pady=20)
        labels[0]["password"].grid(row=0, column=1, padx=10, pady=20)
        labels[0]["label"].grid(row=0, column=2, padx=10, pady=20)

        collapse_button.grid(row=1, column=0, columnspan=3, pady=10)

    else:
        # One shared width per column so every cell aligns (sized to the widest entry in that column)
        name_width = max(len(t["name"]) for t in tests) + 2
        pass_width = max(len(t["password"]) for t in tests) + 2

        # Header row (only shown for 2+ tests). RTL order: copy | password | name
        ttk.Label(root, text=HE["col_copy"], font=("Segoe UI", 11, "bold")).grid(row=0, column=0, padx=10, pady=5)
        ttk.Label(root, text=HE["col_password"], font=("Segoe UI", 11, "bold")).grid(row=0, column=1, padx=10, pady=5)
        ttk.Label(root, text=HE["col_name"], font=("Segoe UI", 11, "bold")).grid(row=0, column=2, padx=10, pady=5)

        for idx, test in enumerate(tests):
            r = idx + 1  # +1 because row 0 is the header
            labels[idx] = {
                "Button": ttk.Button(root, text=HE["copy"], command=make_copy(test["password"])),
                "password": _selectable_label(root, test["password"], width=pass_width, select_all_on_click=True),
                "label": _selectable_label(root, test["name"], width=name_width, select_all_on_click=True),
            }
            labels[idx]["Button"].grid(row=r, column=0, padx=10, pady=5)
            labels[idx]["password"].grid(row=r, column=1, padx=10, pady=5)
            labels[idx]["label"].grid(row=r, column=2, padx=10, pady=5)

        collapse_button.grid(row=len(tests) + 1, column=0, columnspan=3, pady=10)

    return labels, collapse_button


def _popup_window(message=None, tests=None, error=False, time_to_close=0, font=None):
    """The actual tkinter window. Runs inside the spawned process (or directly for blocking calls).
    - message: text for info/error popups
    - tests: list of test dicts for password popups (mutually exclusive with message)
    - error: if True, title is "Error", otherwise "Information"
    - time_to_close: seconds before auto-close. If False/0, stays open until closed manually.
    - font: optional dict of _selectable_label kwargs (family/size/weight) passed through to the message label."""
    root = tk.Tk()
    root.title(HE["password_title"] if tests else ("Error" if error else "Information"))
    root.resizable(False, False)
    root.attributes("-topmost", True)  # Always on top, so it's visible over iTest

    if tests:
        _build_password_content(root, tests)
        # Students shouldn't be able to lose the password window: the X collapses
        # instead of closing, and minimize/maximize are removed (-toolwindow).
        # All title-bar paths now lead to the same safe action as the collapse button.
        root.protocol("WM_DELETE_WINDOW", lambda: _collapse(root))  # X → collapse, not close
        root.attributes("-toolwindow", True)  # Windows: no minimize/maximize buttons (keeps X + draggable title bar)
    else:
        _build_message_content(root, message, font=font)

    # Position the window at the top-center of the screen
    root.update_idletasks()  # Required before winfo_screenwidth() returns correct values
    root.geometry(f"+{(root.winfo_screenwidth() - root.winfo_width()) // 2}+0")
    # Push it all the way to the other side of the screen, go back the length of the window,
    # then cut it in half to get to the center

    if time_to_close:
        root.after(time_to_close * 1000, root.destroy)  # time_to_close is in seconds (messagebox doesn't support this)
    root.mainloop()


def popup(message=None, tests=None, error=False, time_to_close=0, daemon=True, font=None):
    """Spawns a separate process showing a popup window.
    - message: text for info/error popups
    - tests: list of test dicts for password popups (mutually exclusive with message)
    - error: if True, title is "Error", otherwise "Information" / Hebrew password title
    - time_to_close: seconds before auto-close. If False/0, stays open until closed manually.
    - daemon: if False, popup survives after main process exits.
    - font: optional dict of _selectable_label kwargs (family/size/weight) passed through to the popup window.
    Returns the spawned process so the caller can track/terminate it."""
    # Run popup in a separate process — tkinter windows are destroyed along
    # with the thread they were created in, so threading doesn't work here
    try:
        if message:
            print(message)
    except Exception:  # Non-critical debug aid — don't block under any circumstance
        pass  # No console available (windowed mode with no parent console)
    p = multiprocessing.Process(
        target=_popup_window,
        kwargs={
            "message": message,
            "tests": tests,
            "error": error,
            "time_to_close": time_to_close,
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
        popup(msg, error=True, time_to_close=10, daemon=False)
        return

    today = date.today().strftime("%d/%m/%Y")
    try:
        with open(csv_path, "w", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "TestName", "Password"])
            writer.writerow([today, "Math Exam", "12345abc"])
            writer.writerow([today, "Physics Exam", "67890xyz"])
        popup(f"Example CSV created at:\n{csv_path}", time_to_close=10, daemon=False)
    except Exception as e:
        popup(f"Failed to create CSV:\n{e}", error=True, time_to_close=10, daemon=False)


def get_today_tests(csv_path, csv_specified):
    """Reads the CSV and returns a list of today's tests as dicts: {name, password}.
    On any read error: if the user specified the path explicitly, shows an error popup;
    if no path was specified, stays silent (the default file may simply not be there).
    Either way, returns whatever was read so far (possibly empty) and never crashes —
    iTest still launches even if the CSV can't be read."""
    today = date.today().strftime("%d/%m/%Y")
    tests = []

    def report(prefix):
        """Show an error popup only when the user explicitly asked for this CSV."""
        if csv_specified:
            popup(f"{prefix}\n{csv_path}", error=True, time_to_close=10, daemon=False)

    try:
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["Date"] == today:
                    tests.append({"name": row["TestName"], "password": row["Password"]})
    except FileNotFoundError:
        report(HE["err_not_found"])
    except UnicodeDecodeError:
        report(HE["err_encoding"])
    except PermissionError:
        report(HE["err_permission"])
    except OSError as e:
        # Any other OS-level read problem (bad path, disk error, network share down, etc.)
        report(f'{HE["err_generic"]}\n({e})')

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

    tests = get_today_tests(csv_path, csv_specified)
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
            r"  iTestRepeat.exe --loop" "\n"
            r"  iTestRepeat.exe --loop 3" "\n"
            r"  iTestRepeat.exe --stop" "\n"
            r"  iTestRepeat.exe --version" "\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,  # Preserves newlines in epilog and arg help
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
        "-l", "--loop",
        nargs="?",      # Accept -l alone, or -l with a value
        default=1,      # -l not given at all → run once
        const=0,        # -l given alone → 0, which we treat as infinite
        metavar="N",
        help="Repeat: relaunch iTest each time it closes.\n"
             "Without a number, loops indefinitely.\n"
             "With a number (e.g. -l 3), loops that many times.\n"
             "Default (no -l): run once, then exit when iTest closes."
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

    # Resolve --loop into MAX_LOOPS (1 = run once, 0 = infinite, N = loop N times)
    # 0 doubles as "infinite" because the loop's `if MAX_LOOPS and ...` treats 0 as falsy → never breaks
    if isinstance(args.loop, int):
        MAX_LOOPS = args.loop  # default=1 (run once) or const=0 (infinite) — already an int, no parsing needed
    else:
        try:
            MAX_LOOPS = int(args.loop)  # a string typed on the command line, e.g. "3"
            if MAX_LOOPS < 1:
                raise ValueError
        except ValueError:
            popup(f"-l accepts positive numbers only, got: {args.loop}",
                  error=True, time_to_close=60, daemon=False)
            sys.exit(2)
    i = 0
    launches = 0
    while True:
        i += 1
        print(f"loop {i}")  # Debug — harmless in --noconsole; slated for removal in v1.0
        if not is_running():
            if MAX_LOOPS and launches >= MAX_LOOPS:  # MAX_LOOPS=0 (infinite) is falsy → never breaks
                break
            launch(csv_path, csv_specified)
            launches += 1
        time.sleep(3)


if __name__ == "__main__":
    multiprocessing.freeze_support()  # Required for multiprocessing to work inside a PyInstaller exe
    main()