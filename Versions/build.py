import subprocess
import importlib.util
import sys

# Load the version from the script without fully importing it
script = "iTestRepeat v0.3 Stop arg.py"
name = "iTestRepeat"
spec = importlib.util.spec_from_file_location(name, script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

version = module.VERSION

print(f"Building version {version}...")

subprocess.run([
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--noconsole",
    f"--name={name}_v{version}",
    script
])