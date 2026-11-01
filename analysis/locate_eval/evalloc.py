"""Run locate.py on each task at its base commit (git worktree) and score gold-file hits in the top 1/3/5."""
import json, os, subprocess, sys, shutil
SCRIPT = sys.argv[1]
tasks = json.load(open('/tmp/claude-0/loc/tasks.json'))
REPOS = '/tmp/claude-0/repos'; WT = '/tmp/claude-0/loc/wt'
res = []
for t in tasks:
    wt = f"{WT}/{t['id']}"
    if not os.path.isdir(wt):
        subprocess.run(['git', '-C', f"{REPOS}/{t['repo']}", 'worktree', 'add', '-f', '--detach', wt, t['base']], capture_output=True)
    env = dict(os.environ, WORKSPACE=wt)
    words = t['issue'][:3000]
    out = subprocess.run([sys.executable, SCRIPT, words], capture_output=True, text=True, env=env, cwd=wt).stdout
    ranked = [l[3:].split('  (')[0].strip() for l in out.splitlines() if l.startswith('== ')]
    gold = set(t['gold'])
    rank = next((i + 1 for i, f in enumerate(ranked) if f in gold), None)
    res.append((t['id'], rank, ranked[:3], sorted(gold)[:2], t['agent_loc'], t['resolved']))
n = len(res)
for k in (1, 3, 5):
    print(f'top-{k}: {sum(1 for r in res if r[1] and r[1] <= k)}/{n}')
for r in res:
    print(f"{r[0]:15s} rank={str(r[1]):4s} agent_loc={r[4]:5s} solved={str(r[5]):5s} top3={r[2]} gold={r[3]}")
