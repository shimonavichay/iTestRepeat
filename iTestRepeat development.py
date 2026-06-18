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
import ctypes           # For ShellExecuteW (UAC-elevated service start)

VERSION = "0.6.0"  # Startup sequence: single-instance kill, wait-for-service popup, show passwords first
DESC = "Service wait and single-instance startup"

PROGRAM_PATH = r"C:\Program Files (x86)\CET\iTest\iTestLauncher.exe"
PROCESS_NAME = "iTestLauncher.exe"  # Must match the exact process name shown in Task Manager
SERVICE_NAME = "registry test windows service"  # Real service iTest needs (overridden in script mode)
SERVICE_TIMEOUT = 300  # First wait before showing options, in seconds (5 min — iTest support's guidance)
RETRY_TIMEOUT = 60     # Each "keep waiting" retry, in seconds (1 min)
#OPEN = True       # Whether to actually launch iTest; get_exe_folder() sets it False in script mode (for testing)
#! v0.6.0 - Added a dummy program to launch in script mode instead of telling in not to launch. OPEN is no longer needed.

# POTENTIAL OPTIMISATIONS (not urgent):
# - Unify all window types (message/error, password, wait/options, modal confirm) into one class.
# - Revisit rebuilding option buttons each time show_options() runs (currently destroys+recreates).

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
    # Popup window titles
    "title_info": "הודעה",
    "title_error": "שגיאה",
    # Buttons
    "close": "סגור",
    "close_countdown": "סגור ({})",   # {} is filled with the seconds remaining
    # CSV read errors
    "err_not_found": "קובץ הסיסמאות לא נמצא:",
    "err_encoding": "קובץ הסיסמאות אינו בקידוד הנכון (נדרש UTF-8):",
    "err_permission": "אין הרשאה לקרוא את קובץ הסיסמאות (אולי הוא פתוח בתוכנה אחרת?):",
    "err_generic": "לא ניתן לקרוא את קובץ הסיסמאות:",
    # init / create-CSV messages
    "csv_exists": "הקובץ כבר קיים:\n{}\n\nמחק או שנה את שמו תחילה.",
    "csv_created": "קובץ דוגמה נוצר ב:\n{}",
    "csv_create_failed": "יצירת הקובץ נכשלה:\n{}",
    # --loop validation.
    # The \u202A...\u202C (LTR embedding) markers force "-l" and the echoed value to render
    # left-to-right inside this RTL Hebrew sentence, so the hyphen and digits don't get reordered.
    # Note: tk.Text doesn't fully honor the *newer* isolate chars (\u2066/\u2069 — they show as
    # visible boxes), but it DOES act on these older embedding chars. So this is a "shouldn't really
    # work but does" case — keep the \u202A\u202C pair, not the isolates.
    "loop_not_number": "ערך לא חוקי: הארגומנט \u202A-l\u202C מקבל מספרים חיוביים בלבד. התקבל: \u202A{}\u202C",
    # Service wait / options  (svc = service)
    "svc_waiting": "ממתין לשירות של iTest...\nזמן המתנה: {}",   # {} = elapsed MM:SS
    "svc_skip": "דלג על ההמתנה (לטכנאי בלבד)",
    "svc_options": "השירות של iTest עדיין לא פעיל.\nמה ברצונך לעשות?",
    "svc_start": "הפעל שירות",
    "svc_launch_anyway": "הפעל את iTest בכל זאת",
    "svc_keep_waiting": "המשך להמתין",
    "svc_cancel": "ביטול (סגירת התוכנה)",
    "svc_start_failed": "הפעלת השירות נכשלה או בוטלה.",
    "svc_not_installed": "נראה ש-iTest אינו מותקן.\nיש להיכנס לאתר ולהוריד את התוכנה (נדרשת התחברות):\n{}",
    "svc_no_service": "השירות של iTest לא נמצא, אך נראה ש-iTest מותקן.\nניתן לנסות להפעיל בכל זאת, או לבטל ולעבור לעמדה אחרת.",
    "svc_status_starting": "[{}] מנסה להפעיל את השירות...",
    "svc_status_failed": "[{}] הפעלת השירות נכשלה.",
    # Technician-action warning
    "tech_warn": "פעולה זו מיועדת לטכנאי בלבד.\nאין ללחוץ עליה ללא הנחיה.\n\nלהמשיך?",
    "tech_yes": "כן, אני הטכנאי",
    "tech_no": "ביטול",
    # homepage only — no direct download link available
    "itest_download_url": "https://itest.cet.ac.il/",
}


def get_exe_folder():
    """Returns the folder where the exe (or script) is located.
    Needed because the 'current folder' depends on how the program was launched,
    which may differ from the exe's actual location.
    In script mode also points global vars at a dummy test program,
    so development doesn't wait on the real one."""
    #global OPEN #! See comment where OPEN is first set
    global PROGRAM_PATH
    global PROCESS_NAME
    # TESTING NOTE: making a local dummy Windows service to test the wait-for-service flow proved
    # fiddly. We ended up testing against a real iTest install instead. If you know a
    # clean way to spin up a throwaway service, it'd make testing this flow easier.
    if getattr(sys, 'frozen', False):
        # Running as a compiled exe (PyInstaller sets sys.frozen = True)
        return os.path.dirname(sys.executable)
    else:
        # Running as a plain Python script — testing mode
        #OPEN = False #! See comment where OPEN is first set
        PROCESS_NAME = "iTestDummy.exe"
        wd = os.path.dirname(os.path.abspath(__file__))
        PROGRAM_PATH = os.path.join(wd, PROCESS_NAME)
        return wd


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


def _build_message_content(root, message, font=None, time_to_close=0):
    """Builds the layout for an info/error popup inside the given root window.
    font: optional dict of _selectable_label kwargs (family/size/weight).
    time_to_close: if > 0, the Close button shows a live countdown and closes at 0.
    Returns (label, copy_button, close_button)."""
    font = font or {}
    lines = message.split("\n")
    label = _selectable_label(root, message, **font, height=len(lines))
    label.grid(row=0, column=0, columnspan=2, padx=20, pady=20)

    def copy_all():
        root.clipboard_clear()
        root.clipboard_append(message)
    copy_button = ttk.Button(root, text=HE["copy"], command=copy_all)
    copy_button.grid(row=1, column=0, padx=10, pady=10)

    close_button = ttk.Button(root, text=HE["close"], command=root.destroy)
    close_button.grid(row=1, column=1, padx=10, pady=10)

    # Live countdown on the Close button so the admin sees it's about to auto-close.
    # This also owns the auto-close itself (replaces the old root.after in _popup_window).
    if time_to_close:
        def tick(remaining):
            if remaining <= 0:
                root.destroy()
                return
            close_button.config(text=HE["close_countdown"].format(remaining))
            root.after(1000, tick, remaining - 1)  # self-reschedules each second
            # If the user clicks Close early, root is destroyed and the next tick
            # fires on a dead widget — tkinter swallows the resulting error harmlessly.
        tick(time_to_close)

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
    - error: if True, title is the Hebrew "error", otherwise the Hebrew "information"
    - time_to_close: seconds before auto-close. If 0, stays open until closed manually.
    - font: optional dict of _selectable_label kwargs (family/size/weight) passed through to the message label."""
    root = tk.Tk()
    root.title(HE["password_title"] if tests else (HE["title_error"] if error else HE["title_info"]))
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
        _build_message_content(root, message, font=font, time_to_close=time_to_close)

    # Position the window at the top-center of the screen
    root.update_idletasks()  # Required before winfo_screenwidth() returns correct values
    root.geometry(f"+{(root.winfo_screenwidth() - root.winfo_width()) // 2}+0")
    # Push it all the way to the other side of the screen, go back the length of the window,
    # then cut it in half to get to the center

    # NOTE: auto-close is now handled by the countdown inside _build_message_content
    # (was: if time_to_close: root.after(time_to_close * 1000, root.destroy))
    root.mainloop()


def popup(message=None, tests=None, error=False, time_to_close=0, daemon=True, font=None):
    """Spawns a separate process showing a popup window.
    - message: text for info/error popups
    - tests: list of test dicts for password popups (mutually exclusive with message)
    - error: if True, title is the Hebrew "error", otherwise the Hebrew "information"
      (password popups use the Hebrew password title regardless of this flag).
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


def technician_warning(parent):
    """Modal 'this is a technician-only action' confirmation, styled like a Windows warning dialog.
    Returns True if confirmed, False otherwise. Reusable — attach to any technician-only button.
    'parent' is the window it should be modal over."""
    confirmed = {"value": False}  # dict so the button closures can mutate it (can't rebind a plain var)

    win = tk.Toplevel(parent)
    win.title(HE["title_error"])
    win.resizable(False, False)
    win.attributes("-topmost", True)
    win.grab_set()  # Modal: blocks the parent window until this is answered

    msg = HE["tech_warn"]
    _selectable_label(win, msg, height=len(msg.split("\n"))).grid(row=0, column=0, columnspan=2, padx=20, pady=20)

    def choose(value):
        confirmed["value"] = value
        win.destroy()

    ttk.Button(win, text=HE["tech_yes"], command=lambda: choose(True)).grid(row=1, column=0, padx=10, pady=10)
    ttk.Button(win, text=HE["tech_no"], command=lambda: choose(False)).grid(row=1, column=1, padx=10, pady=10)

    win.update_idletasks()
    win.geometry(f"+{(win.winfo_screenwidth() - win.winfo_width()) // 2}+{win.winfo_screenheight() // 3}")
    win.wait_window()  # Block until answered (Toplevel can't run its own mainloop)
    return confirmed["value"]


def _shell_execute(verb, file, params="", show=1, working_directory=None, parent=None):
    """Readable wrapper around the positional Win32 ShellExecuteW
    (hwnd, verb, file, parameters, directory, show).
    verb: 'open', 'runas' (UAC elevation), etc. show: 1 = visible window, 0 = hidden."""
    return ctypes.windll.shell32.ShellExecuteW(parent, verb, file, params, working_directory, show)


def _service_wait_process(result_queue, start_epoch):
    """Runs in its own process. Owns the entire wait-for-service experience:
    - Polls the service every second, showing elapsed time since start_epoch.
    - If the service comes up on its own (even while options are showing), closes and reports 'running'.
    - 'Skip wait' (technician) or the SERVICE_TIMEOUT jumps to the options screen.
    - Options: Start service (elevated), Launch anyway, Keep waiting, Cancel.
    - Reports the verdict ('running' / 'launch' / 'cancel') back via result_queue.
    Closing the window (X) counts as Cancel.

    Verdict goes through a Queue rather than a shared Value purely for readability —
    it lets us pass back strings that match the rest of the code's match/case style.

    (FUTURE): when the service is missing but iTest IS installed, we currently offer the same
    simple options. A richer flow (reinstall via UninstallString, support phone numbers, GitHub link)
    is planned but deferred so a misconfiguration can't render iTestRepeat useless in the meantime.
    Authentication for that flow: registry DisplayName == 'iTest' AND Publisher == 'CET', reading
    InstallLocation (e.g. C:\\Program Files (x86)\\CET\\iTest) instead of the hardcoded PROGRAM_PATH.
    Found under HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{GUID}."""
    root = tk.Tk()
    root.title(HE["title_info"])
    root.resizable(False, False)
    root.attributes("-topmost", True)

    state = {"phase": "waiting", "deadline": start_epoch + SERVICE_TIMEOUT}

    def on_close():
        result_queue.put("cancel")
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)

    label = _selectable_label(root, HE["svc_waiting"].format("00:00"), height=2)
    label.grid(row=0, column=0, padx=20, pady=20)

    def _svc_status_line(msg_key):
        """Returns a timestamped status string for the options window, e.g. '[14:03:21] מנסה להפעיל שירות...'.
        msg_key: the suffix of the HE['svc_status_*'] key to show."""
        stamp = time.strftime("%H:%M:%S")
        text = HE["svc_options"] + "\n" + HE[f"svc_status_{msg_key}"].format(stamp)
        return text

    def set_label(text):
        label.configure(state="normal")
        label.delete("1.0", "end")
        label.insert("1.0", text)
        label.configure(state="disabled")

    def finish(verdict):
        result_queue.put(verdict)
        root.destroy()

    opt_frame = ttk.Frame(root)  # holds option buttons; shown only in the options phase

    def back_to_waiting(retry_seconds):
        state["phase"] = "waiting"
        state["deadline"] = time.time() + retry_seconds
        set_label(HE["svc_waiting"].format("00:00"))
        opt_frame.grid_remove()  # hide options (remembers grid position for later)
        skip_btn.grid()          # re-show the skip button (was hidden in options phase)

    def show_options(missing=False):
        state["phase"] = "options"
        set_label(HE["svc_no_service"] if missing else HE["svc_options"])
        skip_btn.grid_remove()  # hide skip while options are up

        def do_start():
            if technician_warning(root):
                set_label(_svc_status_line("starting"))  # show "[HH:MM:SS] starting service…" on the options window
                ps = (f"Start-Service -Name '{SERVICE_NAME}'; "
                      f"Get-Service -Name '{SERVICE_NAME}'; Start-Sleep -Seconds 10")
                try:
                    _shell_execute(verb="runas", file="powershell", params=f'-Command "{ps}"', show=1)
                except Exception as e:
                    # Acknowledge the failure in its own dialog, then STAY on the options screen
                    popup(f'{HE["svc_start_failed"]}\n({e})', error=True, time_to_close=10, daemon=False)
                    set_label(_svc_status_line("failed"))  # update the options-window status line
                else:
                    back_to_waiting(RETRY_TIMEOUT)  # only on success-path: poll will confirm it came up

        def do_launch():
            if technician_warning(root):
                finish("launch")

        # Rebuild option buttons fresh each time (so repeated cycles don't stack duplicates)
        for child in opt_frame.winfo_children():
            child.destroy()
        ttk.Button(opt_frame, text=HE["svc_start"], command=do_start).grid(row=0, column=0, padx=6, pady=8)
        ttk.Button(opt_frame, text=HE["svc_launch_anyway"], command=do_launch).grid(row=0, column=1, padx=6, pady=8)
        ttk.Button(opt_frame, text=HE["svc_keep_waiting"], command=lambda: back_to_waiting(RETRY_TIMEOUT)).grid(row=0, column=2, padx=6, pady=8)
        ttk.Button(opt_frame, text=HE["svc_cancel"], command=on_close).grid(row=0, column=3, padx=6, pady=8)
        opt_frame.grid(row=2, column=0, padx=10, pady=5)

    def do_skip():
        if technician_warning(root):
            show_options()
    skip_btn = ttk.Button(root, text=HE["svc_skip"], command=do_skip)
    skip_btn.grid(row=1, column=0, padx=10, pady=10)

    def tick():
        # Poll the service first — if it's up, finish regardless of phase (covers "came up
        # while options were showing", like the Windows 'app responded again' behaviour).
        try:
            status = psutil.win_service_get(SERVICE_NAME).status()
            exists = True
        except Exception:
            status = None
            exists = False  # service not found

        if status == "running":
            finish("running")
            return

        if state["phase"] == "waiting":
            elapsed = int(time.time() - start_epoch)
            mm, ss = divmod(elapsed, 60)
            set_label(HE["svc_waiting"].format(f"{mm:02d}:{ss:02d}"))

            if not exists:
                # Service missing — is iTest even installed? (placeholder: check PROGRAM_PATH exists)
                # FUTURE (#9): authenticate + locate via registry (see this function's docstring).
                if not os.path.exists(PROGRAM_PATH):
                    popup(HE["svc_not_installed"].format(HE["itest_download_url"]),
                          error=True, time_to_close=60, daemon=False)
                    finish("cancel")
                    return
                else:
                    show_options(missing=True)  # installed but no service → options
            elif time.time() >= state["deadline"]:
                show_options()

        root.after(1000, tick)  # next poll in 1 second

    tick()
    root.update_idletasks()
    root.geometry(f"+{(root.winfo_screenwidth() - root.winfo_width()) // 2}+0")
    root.mainloop()


def wait_for_service():
    """Starts the wait-for-service popup process and blocks until it reports a verdict.
    Returns 'running', 'launch', or 'cancel'. On 'cancel', the caller should exit."""
    result_queue = multiprocessing.Queue()
    start_epoch = time.time()  # this instance's first check — the popup's timer counts from here
    proc = multiprocessing.Process(target=_service_wait_process, args=(result_queue, start_epoch), daemon=True)
    proc.start()
    verdict = result_queue.get()  # blocks until the popup puts its decision on the queue
    proc.join()                   # reap the finished process so it doesn't linger
    return verdict


def create_example_csv(csv_path):
    """Creates an example CSV at csv_path with 2 example tests for today.
    Refuses to overwrite an existing file."""
    if os.path.exists(csv_path):
        # daemon=False so the popup survives after this process exits
        popup(HE["csv_exists"].format(csv_path), error=True, time_to_close=10, daemon=False)
        return

    today = date.today().strftime("%d/%m/%Y")
    try:
        with open(csv_path, "w", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "TestName", "Password"])
            writer.writerow([today, "Math Exam", "12345abc"])
            writer.writerow([today, "Physics Exam", "67890xyz"])
        popup(HE["csv_created"].format(csv_path), time_to_close=10, daemon=False)
    except Exception as e:
        popup(HE["csv_create_failed"].format(e), error=True, time_to_close=10, daemon=False)


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
    """Returns True if iTest(/the dummy) is currently in the process list."""
    return any(p.name() == PROCESS_NAME for p in psutil.process_iter())


def show_passwords(csv_path, csv_specified):
    """Closes any existing password popup and shows a new one with today's passwords.
    v0.6.0: split out from launch() so passwords can be shown without launching iTest
    (used to show passwords up front even if iTest is already open). Remove this note at v0.7.0."""
    global popup_process
    if popup_process is not None and popup_process.is_alive():
        popup_process.terminate()
    tests = get_today_tests(csv_path, csv_specified)
    if tests:
        popup_process = popup(tests=tests)


def launch_itest():
    """Launches iTest (in script mode PROGRAM_PATH points at the dummy exe, so this is safe to call during development).
    v0.6.0: split out from launch(). Remove this note at v0.7.0."""
    # if OPEN: #! See comment where OPEN is first set
    subprocess.Popen([PROGRAM_PATH])  # Launching the program


def kill_other_instances():
    """Kills any other running instances of this exe, sparing only the current process.
    SAFE ONLY AT STARTUP: runs before any popup subprocess exists, so the only process with
    our name is ourselves. If moved later, it would also kill our own popup children."""
    my_pid = os.getpid()
    my_name = os.path.basename(sys.executable)
    # Fetch name in the iterator so we can skip non-matching processes cheaply
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] == my_name and proc.info["pid"] != my_pid:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass  # vanished or not ours to kill — skip


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
            # The value is wrapped in directional markers to match the embedding in
            # HE["loop_not_number"] (see the comment there). The pop-then-embed order
            # (\u202C before, \u202A after) nests correctly inside that outer LTR run.
            popup(HE["loop_not_number"].format(f"\u202C{args.loop}\u202A"),
                  error=True, time_to_close=60, daemon=False)
            sys.exit(2)

    # --- Startup sequence (runs once, before the relaunch loop) ---
    kill_other_instances()            # Ensure only this instance remains
    verdict = wait_for_service()      # Block on the wait/options popup
    if verdict == "cancel":
        sys.exit()
    # 'running' or 'launch' → proceed

    # Show passwords up front so they're visible even if iTest is already open
    show_passwords(csv_path, csv_specified)

    # --- Relaunch loop ---
    i = 0
    launches = 0
    while True:
        i += 1
        print(f"loop {i}")  # Debug — harmless in --noconsole; slated for removal in v1.0
        if not is_running():
            if MAX_LOOPS and launches >= MAX_LOOPS:  # MAX_LOOPS=0 (infinite) is falsy → never breaks
                break
            show_passwords(csv_path, csv_specified)
            launch_itest()
            launches += 1
        if i == 1: launches = 1  # Counts an iTest session that was already open in iTestRepeat launch to the "-l N" count
        time.sleep(3)


if __name__ == "__main__":
    multiprocessing.freeze_support()  # Required for multiprocessing to work inside a PyInstaller exe
    main()