"""Harness probe: print where this skill script runs and what it can see. Changes nothing."""
import getpass, os, platform, subprocess, sys, time

t0 = time.time()
print("PROBE where.py")
print("argv:", sys.argv)
print("file:", os.path.abspath(__file__))
print("cwd:", os.getcwd())
print("python:", sys.executable, platform.python_version())
try:
    print("user:", getpass.getuser())
except Exception as e:
    print("user: ?", e)
print("hostname:", platform.node())
for d in ("/workspace", os.getcwd()):
    try:
        names = sorted(os.listdir(d))
        print(f"listdir {d}: {len(names)} entries:", names[:25])
    except Exception as e:
        print(f"listdir {d}: error {e!r}")
try:
    r = subprocess.run(["git", "-C", "/workspace", "status", "--short", "--branch"], capture_output=True, text=True, timeout=20)
    print("git status /workspace (rc %d):" % r.returncode, (r.stdout or r.stderr)[:800])
except Exception as e:
    print("git status error:", repr(e))
for k in ("PATH", "VIRTUAL_ENV", "HOME", "PYTHONPATH"):
    print(f"env {k}:", os.environ.get(k))
print("seconds: %.2f" % (time.time() - t0))
