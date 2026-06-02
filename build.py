import subprocess
import sys
import re
import os
import shutil

SCRIPT = "iTestRepeat development.py"
NAME = "iTestRepeat"

# Dedicated folders so the build doesn't dump artifacts in the project root
BUILD_DIR = "build"        # PyInstaller's intermediate work folder
DIST_DIR = "dist"          # Where the final exe lands
SPEC_DIR = "spec"          # Where the generated .spec file goes
VERSIONS_DIR = "versions"  # Archive of each version's source code

# Read VERSION and its inline comment without executing the script
with open(SCRIPT, encoding="utf-8") as f:
    content = f.read()

def read_value(var_name):
    """Reads a top-level string assignment like  VAR = "value"  from the script."""
    m = re.search(rf'^{var_name}\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    return m.group(1) if m else None

version = read_value("VERSION")
description = read_value("DESC") or ""

if not version:
    sys.exit("Could not find VERSION in the script.")

print(f"Building version {version}...")
if description:
    print(f"  {description}")

# --- Build the exe ---
subprocess.run([
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--noconsole",
    f"--name={NAME}_v{version}",
    f"--distpath={DIST_DIR}",
    f"--workpath={BUILD_DIR}",
    f"--specpath={SPEC_DIR}",
    SCRIPT
])

# --- Archive the source into versions/ ---
os.makedirs(VERSIONS_DIR, exist_ok=True)
safe_desc = re.sub(r'[\\/:*?"<>|]', "", description)  # strip characters illegal in filenames
archive_name = f"{NAME} v{version} {safe_desc}".strip() + ".py"
archive_path = os.path.join(VERSIONS_DIR, archive_name)

if os.path.exists(archive_path):
    print(f"\nNote: {archive_name} already exists — not overwriting.")
else:
    shutil.copy2(SCRIPT, archive_path)
    print(f"\nArchived source to: {archive_path}")

print(f"Done. Exe is in: {os.path.abspath(DIST_DIR)}")