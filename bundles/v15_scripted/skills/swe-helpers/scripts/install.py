"""install.py: copy the helper scripts to /tmp/h (where run_command can always reach them), then run locate.

Usage (skill script tool): skill swe-helpers, file scripts/install.py, positional args = words from the issue.
After this, use `python3 /tmp/h/locate.py`, `python3 /tmp/h/patch.py`, `python3 /tmp/h/check.py` with run_command.
"""
import os, shutil, subprocess, sys

here = os.path.dirname(os.path.abspath(__file__))
dest = "/tmp/h"
os.makedirs(dest, exist_ok=True)
for name in ("locate.py", "patch.py", "check.py"):
    shutil.copy(os.path.join(here, name), os.path.join(dest, name))
print("helpers installed in /tmp/h: locate.py patch.py check.py")
words = [a for a in sys.argv[1:] if a != "--"]
if words:
    r = subprocess.run([sys.executable, os.path.join(dest, "locate.py"), " ".join(words)], capture_output=True, text=True)
    print(r.stdout[-4500:] or r.stderr[-1500:])
