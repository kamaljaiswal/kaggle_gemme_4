"""install.py: copy locate.py to /tmp/h (where run_command can always reach it), then run it.

Usage (skill script tool): skill swe-helpers, file scripts/install.py, positional args = words from the issue.
After this, `python3 /tmp/h/locate.py '...'` works with run_command.
"""
import os, shutil, subprocess, sys

here = os.path.dirname(os.path.abspath(__file__))
dest = "/tmp/h"
os.makedirs(dest, exist_ok=True)
for name in ("locate.py",):
    shutil.copy(os.path.join(here, name), os.path.join(dest, name))
print("locate installed in /tmp/h")
words = [a for a in sys.argv[1:] if a != "--"]
if words:
    r = subprocess.run([sys.executable, os.path.join(dest, "locate.py"), " ".join(words)], capture_output=True, text=True)
    print(r.stdout[-4500:] or r.stderr[-1500:])
