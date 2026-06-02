import subprocess
import sys

commands = [
    # ["--init-csv"],
    # [],
    # ["-l"],
    # ["--loop"],
    # ["--loop", "2"],
    ["--loop", "3"],
    # ["--version"],
    #["--stop"],
    #["--init-csv", "--csv", r"\\dca\Files-Open\Admin\iTestRepeat\tests_init.csv"],
    #["--init-csv", "--csv", r"\\dca\Files-Open\Admin\iTestRepeat\tests_init.csv"],
    #["--csv", r"\\dca\Files-Open\Admin\iTestRepeat\tests_init.csv"],
    ["-?"],
    #["-h"],
    #["--help"],
]

for args in commands:
    print(f"\n--- Testing: {args} ---")
    input("Press Enter to confirm")
    subprocess.run([sys.executable, "iTestRepeat development.py"] + args)
    input("Press Enter to confirm")