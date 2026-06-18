# setup_env.py — one-shot environment setup for a new machine.
# Installs every third-party package iTestRepeat (and its dev/test tooling) needs.
# Run once on a fresh station:  py -3.12 setup_env.py
# Personal preference: run from inside the IDE instead of by command,
# so it's clear it gets installed on the right environment,
import subprocess
import sys

PACKAGES = [
    "psutil",       # process / service inspection (main program)
    "pyinstaller",  # compiling to exe (build.py)
]

def main():
    for pkg in PACKAGES:
        print(f"Installing {pkg}...")
        # Same interpreter we're running under, so packages land in the right place
        subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True)
    print("\nSetup complete.")

if __name__ == "__main__":
    main()