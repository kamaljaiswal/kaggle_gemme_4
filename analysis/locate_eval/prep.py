"""Build an offline locate benchmark from the 41 traces: issue text, gold files, base commit (parent of the PR commit)."""
import csv, json, re, subprocess, sys
RES = '/tmp/claude-0/res'; REPOS = '/tmp/claude-0/repos'
led = {r['instance_id']: r for r in csv.DictReader(open(f'{RES}/ledger_all_20261031_1753.csv')) if r['run_id'].startswith('v12a')}
out = []
for tid, r in sorted(led.items()):
    repo, num = tid.rsplit('_', 1)
    t = json.load(open(f'{RES}/v12a_think2048_valid_20261031_1753/harness/traces/trace_{tid}.json'))
    user = next(s['message'] for s in t['steps'] if s.get('source') == 'user')
    issue = user.split('Problem Statement:', 1)[1].split('## Task Budget', 1)[0].strip()
    git = lambda *a: subprocess.run(['git', '-C', f'{REPOS}/{repo}', *a], capture_output=True, text=True).stdout.strip()
    c = git('log', '--format=%H %s', '--all', f'--grep=#{num}\\b', '-E')
    lines = [l for l in c.splitlines() if l]
    # prefer squash commit "(#N)" else "Merge pull request #N"
    pick = next((l for l in lines if f'(#{num})' in l), None) or next((l for l in lines if f'pull request #{num} ' in l), None)
    if not pick:
        print('no commit for', tid); continue
    sha = pick.split()[0]
    base = git('rev-parse', f'{sha}^1')
    out.append(dict(id=tid, repo=repo, base=base, issue=issue, gold=[g for g in r['gold_files'].split(';') if g],
                    agent_loc=r['loc_hit'], resolved=r['resolved'] == 'True'))
json.dump(out, open('/tmp/claude-0/loc/tasks.json', 'w'), indent=1)
print(len(out), 'tasks prepared')
