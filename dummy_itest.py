# dummy_itest.py — stand-in for iTest during development.
# Prints a message and stays open until you close it (Enter or window close).
print("iTest dummy is active")
print("Close this window (or press Enter) to simulate iTest closing.")
try:
    input()
except (EOFError, KeyboardInterrupt):
    pass