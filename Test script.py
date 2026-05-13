import subprocess
import sys

commands = [
    #[],
    #["--version"],
    #["--stop"],
    #["--init-csv", "--csv", r"\\dca\Files-Open\Admin\iTestRepeat\tests_init.csv"],
    ["--csv", "fake.csv"],
    #["-?"],
]

for args in commands:
    print(f"\n--- Testing: {args} ---")
    input("Press Enter to confirm")
    subprocess.run([sys.executable, "iTestRepeat development.py"] + args)
    input("Press Enter to confirm")