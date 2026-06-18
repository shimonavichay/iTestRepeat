# dummy_itest_build.py — compiles the dummy iTest stand-in (iTestDummy.exe) into the project root,
# where iTestRepeat's script-mode PROGRAM_PATH looks for it.
# Separate from build.py (which builds the real exe) so the two never interfere.
# NOTE: dummy tooling — copied from Claude, not independently reviewed.
import subprocess
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DUMMY_SOURCE = os.path.join(HERE, "dummy_itest.py")
NAME = "iTestDummy"

subprocess.run([
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--console",
    f"--name={NAME}",
    f"--distpath={HERE}",            # project root — where script-mode PROGRAM_PATH expects it
    f"--workpath={os.path.join(HERE, 'build')}",
    f"--specpath={os.path.join(HERE, 'spec')}",
    DUMMY_SOURCE
])
print(f"Done. {NAME}.exe is in the project root for script-mode testing.")