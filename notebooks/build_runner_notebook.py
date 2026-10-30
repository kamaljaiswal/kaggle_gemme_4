#!/usr/bin/env python3
"""Generate notebooks/kaggle_runner.ipynb from the cell sources below.

Edit the cells here, then run:  python notebooks/build_runner_notebook.py
Keeping the source in a .py file makes diffs readable in git.
"""
import json
from pathlib import Path

MD, CODE = "markdown", "code"

CELLS = [
(MD, """# Gemma 4 agent runner: validate, smoke test, pilot, package

Runs one bundle from this repo against a chosen set of tasks, in the real competition harness,
and writes results the ledger script can read. Use it **before** submitting.

**Setup on Kaggle**
1. Upload this repository as a private Kaggle Dataset (zip the repo folder, *New Dataset*), e.g. `kaggle-gemme-4-repo`.
2. New notebook → *Add Input*: the competition data, the Gemma 4 model you want, the
   `gemma-4-developer-agent-wheelhouse` dataset (as in the official starter), and your repo dataset.
3. Accelerator: **GPU L4×4**. Internet: **off** (required for L4).
4. Edit the config cell, then *Run All*. To compare bundles, list several in `BUNDLES` and set `REPEATS`:
   they run one after another on the same tasks in a single session (one model load).

**Modes**
- `smoke`: 3 tasks. Checks the bundle loads, tools work and a patch comes out (~10 min).
- `pilot`: the fixed list in `pilot/pilot_ids.txt` (~1–1.5 h for 24 tasks).
- `ids`: the ids you list in `TASK_IDS`.
- `valid`: `N_VALID` tasks sampled (fixed seed, by repo) from the 126 public tasks whose reference patch can pass. Use this to compare bundles.
- `all`: every task (~6.5 h for 129 tasks at ~3 min each; keep an eye on your GPU quota).

**Scorer-like grading (`SCORER_LIKE = True`)**: in a plain notebook only 52 of 129 reference patches pass, so most local failures
are the environment, not the agent. Attach two more datasets: `zbigniewkirchner/gemma-4-agent-local-eval-wheels` and
`zbigniewkirchner/gemma-4-agent-local-eval-pythons`. The setup is adapted from his notebook
"Gemma 4 Agent: Do Gold Patches Pass Locally?" (Apache 2.0), where 127 of 129 reference patches pass.

Results go to `/kaggle/working/results/<RUN_ID>/`. Download `results_<SESSION>.zip` at the end, **before stopping the session**.
"""),
(CODE, """# ---------------- CONFIG: the only cell you need to edit ----------------
BUNDLES = ["v3_overflow_fix"]       # one or more folders under bundles/. Several = compared in ONE GPU session (same base model)
MODE = "smoke"                      # smoke | pilot | ids | all
TASK_IDS = []                       # used when MODE == "ids"
REPEATS = 1                         # runs of every bundle on the same tasks (2+ shows run-to-run noise)
MODEL_OVERRIDE = None               # e.g. "gemma-4-12b-it-qat-w4a16-ct" to test another size (changes the bundle id)
RUN_ID = None                       # None -> <bundle>_<mode>_<timestamp>[_rN]; only used when there is a single run
STOP_AFTER_HOURS = 11.0             # stop starting new tasks after this much wall time
REPO_DIR = None                     # None -> auto-detect the uploaded repo under /kaggle/input
SCORER_LIKE = True                  # grade in a scorer-like sandbox (needs Zbigniew Kirchner's two datasets); False = plain notebook
GOLD_CHECK = True                   # before the model runs, grade the reference patches of the selected tasks (CPU, ~15 s/task)
N_VALID = 40                        # used when MODE == "valid": tasks sampled from the 126 gradable ones, by repo
VALID_SEED = 1                      # same seed = same tasks in every session
"""),
(MD, "## 1. Environment (same as the official starter)"),
(CODE, """import glob, importlib, json, logging, os, re, shutil, subprocess, sys, time, hashlib, zipfile
from datetime import datetime, timezone
from pathlib import Path

for k, v in {
    'TRANSFORMERS_NO_TF': '1', 'TRANSFORMERS_NO_FLAX': '1', 'TRANSFORMERS_OFFLINE': '1',
    'VLLM_NO_USAGE_STATS': '1', 'VLLM_WORKER_MULTIPROC_METHOD': 'spawn', 'VLLM_ENGINE_READY_TIMEOUT_S': '1200',
    'VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS': '1', 'NCCL_DEBUG': 'WARN', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
    'LITELLM_TELEMETRY': 'False', 'LITELLM_LOG': 'WARNING', 'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True',
    'OTEL_SDK_DISABLED': 'true', 'OTEL_PYTHON_DISABLED': 'true'}.items():
    os.environ[k] = v
os.environ.setdefault('OPENAI_API_KEY', 'EMPTY'); os.environ.setdefault('LOCAL_API_KEY', 'EMPTY')

def quiet_logs():
    for name in ('LiteLLM', 'LiteLLM Router', 'LiteLLM Proxy', 'litellm', 'httpx', 'httpcore', 'openai', 'urllib3',
                 'opentelemetry', 'opentelemetry.context'):
        lg = logging.getLogger(name); lg.setLevel(logging.WARNING)
        if 'litellm' in name.lower():
            lg.propagate = False; lg.handlers.clear()
quiet_logs()

def find_wheelhouse():
    \"\"\"The harness wheelhouse is the folder holding the swegemma / adk_submission / vllm wheels.
    (Not the competition's own wheels/ folder, which only has the repos' test dependencies.)\"\"\"
    default = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
    if any(default.glob('*.whl')):
        return default
    for pat in ('swegemma*.whl', 'adk_submission*.whl', 'adk-submission*.whl', 'vllm*.whl'):
        hits = glob.glob(f'/kaggle/input/**/{pat}', recursive=True)
        if hits:
            return Path(hits[0]).parent
    return None

WHEELHOUSE_DIR = find_wheelhouse()
if WHEELHOUSE_DIR is None:
    print('Attached inputs:')
    for p in sorted(glob.glob('/kaggle/input/*/*')) + sorted(glob.glob('/kaggle/input/*/*/*')):
        print('  ', p)
    raise SystemExit('Harness wheelhouse not found. Add Input -> Datasets -> search '
                     '"gemma-4-developer-agent-wheelhouse" (owner: metric), attach it, then rerun this cell.')
for pat in ('/usr/local/lib/python*/dist-packages/*cutlass*.pth', '/usr/local/lib/python*/site-packages/*cutlass*.pth'):
    for pth in glob.glob(pat):
        try: os.unlink(pth)
        except OSError: pass
tmp_whl = Path('/tmp/wheelhouse'); tmp_whl.mkdir(parents=True, exist_ok=True)
for w in WHEELHOUSE_DIR.glob('*.whl'):
    if 'cutlass' in w.name.lower(): continue
    name = w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name
    t = tmp_whl / name
    if not t.exists():
        try: os.symlink(w, t)
        except OSError: shutil.copyfile(w, t)
wheels = sorted(str(w) for w in tmp_whl.glob('*.whl'))
print(f'Installing {len(wheels)} wheels from {WHEELHOUSE_DIR} ...')
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', *wheels], check=True)
importlib.invalidate_caches(); quiet_logs()
print('ok')
"""),
(MD, "## 2. Locate data and repo, validate the bundle"),
(CODE, """DATA_DIR = Path('/kaggle/input/competitions/gemma-4-developer-agent')
WORK = Path('/kaggle/working')

BUNDLE_LIST = list(globals().get('BUNDLES') or [])
if not BUNDLE_LIST and globals().get('BUNDLE_NAME'):          # old single-bundle config still works
    BUNDLE_LIST = [BUNDLE_NAME]
assert BUNDLE_LIST, 'Set BUNDLES in the config cell.'

if REPO_DIR is None:
    hits = [Path(p).parent for p in glob.glob('/kaggle/input/**/scripts/validate_bundle.py', recursive=True)]
    assert hits, 'Repo dataset not found under /kaggle/input. Attach it or set REPO_DIR.'
    REPO_DIR = hits[0].parent
REPO_DIR = Path(REPO_DIR)

AGENT_DIR = WORK / 'agent'          # the writable copy the harness reads; the input dataset is read-only
BUNDLE_IDS, ZIPS = {}, {}

def prepare_bundle(name, quiet=False):
    # Copy bundles/<name> to AGENT_DIR (applying MODEL_OVERRIDE) and validate it; fails before any GPU time is spent.
    src = REPO_DIR / 'bundles' / name
    assert src.is_dir(), f'bundle not found: {src}'
    shutil.rmtree(AGENT_DIR, ignore_errors=True); shutil.copytree(src, AGENT_DIR)
    if MODEL_OVERRIDE:
        for yp in sorted(AGENT_DIR.rglob('*.y*ml')):
            if yp.is_file():
                txt = re.sub(r'^(\\s*model:\\s*).*$', rf'\\g<1>{MODEL_OVERRIDE}', yp.read_text(), flags=re.M)
                if not MODEL_OVERRIDE.startswith('gemma-4-31b'):
                    txt = re.sub(r'^\\s*adapter:\\s*.*\\n?', '', txt, flags=re.M)   # sample adapters are 31B-shaped
                yp.write_text(txt)
    zdir = WORK / 'zips' / name
    shutil.rmtree(zdir, ignore_errors=True)
    v = subprocess.run([sys.executable, str(REPO_DIR / 'scripts' / 'validate_bundle.py'), str(AGENT_DIR), '--zip', str(zdir)],
                       capture_output=True, text=True)
    if not quiet:
        print(f'--- {name} ---'); print(v.stdout, v.stderr)
    assert v.returncode == 0, f'Bundle {name} failed validation; fix it before spending GPU time.'
    BUNDLE_IDS[name] = re.search(r'bundle id (\\w+)', v.stdout).group(1)
    ZIPS[name] = next(zdir.glob('*.zip'))
    # Run from the unzipped zip, not the folder copy, so a local run tests exactly the file you upload.
    shutil.rmtree(AGENT_DIR, ignore_errors=True); AGENT_DIR.mkdir(parents=True)
    with zipfile.ZipFile(ZIPS[name]) as z:
        z.extractall(AGENT_DIR)
    assert (AGENT_DIR / 'agent.yaml').is_file() or any((AGENT_DIR / n).is_file() for n in ('agent.yml', 'root_agent.yaml', 'root_agent.yml')), \
        f'{name}: root config is not at the top of the zip'

for name in BUNDLE_LIST:
    prepare_bundle(name)

# One vLLM server serves the whole session, so every bundle must declare the same base model.
def bundle_models(n):
    # every model: line in the bundle's yaml files (a workflow root such as SequentialAgent declares none itself)
    found = set()
    for yp in (REPO_DIR / 'bundles' / n).rglob('*.y*ml'):
        found |= set(re.findall(r'^\\s*model:\\s*(\\S+)', yp.read_text(), re.M))
    return {MODEL_OVERRIDE} if MODEL_OVERRIDE else found
base_models = {n: bundle_models(n) for n in BUNDLE_LIST}
all_models = set().union(*base_models.values())
assert len(all_models) == 1, f'bundles use different models, run them in separate sessions: {base_models}'
prepare_bundle(BUNDLE_LIST[0], quiet=True)    # leave the first bundle in AGENT_DIR; the server is started from it
print('BUNDLE_IDS =', BUNDLE_IDS)
"""),
(MD, "## 3. Choose tasks"),
(CODE, """from swegemma.models import load_tasks
TASKS_PATH = DATA_DIR / 'tasks.jsonl'
tasks = load_tasks(TASKS_PATH)
by_id = {t.instance_id: t for t in tasks}

if MODE == 'smoke':
    # one task from each of the first three repos, so a repo-specific setup problem shows up
    seen, sel = set(), []
    for t in tasks:
        if t.repo not in seen:
            seen.add(t.repo); sel.append(t)
        if len(sel) == 3: break
elif MODE == 'pilot':
    ids = (REPO_DIR / 'pilot' / 'pilot_ids.txt').read_text().split()
    sel = [by_id[i] for i in ids if i in by_id]
    missing = [i for i in ids if i not in by_id]
    if missing: print('not in tasks.jsonl:', missing)
elif MODE == 'ids':
    sel = [by_id[i] for i in TASK_IDS]
elif MODE == 'valid':
    import random
    # 2 tasks no environment can pass (contradictory skip conditions) + 1 that passes with no change
    EXCLUDE = {'fastapi_14186', 'rich_3486', 'fastapi_14077'}
    pool = [t for t in tasks if t.instance_id not in EXCLUDE]
    rng, groups = random.Random(VALID_SEED), {}
    for t in pool:
        groups.setdefault(t.repo, []).append(t)
    sel = []
    for repo_name in sorted(groups):
        g = groups[repo_name]
        sel += rng.sample(g, min(len(g), max(1, round(N_VALID * len(g) / len(pool)))))
    sel = sorted(sel, key=lambda t: t.instance_id)
    print('valid task ids:', [t.instance_id for t in sel])
elif MODE == 'all':
    sel = list(tasks)
else:
    raise ValueError(MODE)

task_hash = hashlib.sha256(TASKS_PATH.read_bytes()).hexdigest()[:12]
print(f'{len(sel)} tasks selected (tasks file {task_hash})')
"""),
(MD, """## 3b. Scorer-like sandbox (optional, recommended)

Adapted from Zbigniew Kirchner, "Gemma 4 Agent: Do Gold Patches Pass Locally?" (Apache 2.0). Each sandbox gets a clean venv
(no Kaggle packages) on top of a per-repo folder like the scorer image: the newest competition wheel of every package, pytest 8.4.2,
pytest-timeout 2.1.0, the imp/telnetlib shims and the missing test packages. A small calibration makes old public tasks gradable.
The same hook is used for the agent's own sandbox, so the agent also sees the scorer's packages."""),
(CODE, """CURRENT = {'id': None}     # the task being run or graded; the hook reads it
if SCORER_LIKE:
    import tarfile, tomllib
    from packaging.requirements import Requirement
    from packaging.version import Version
    import swegemma.harness.verification as verification
    import swegemma.harness.agent_runner as agent_runner
    from swegemma.sandbox.subprocess import SubprocessManager

    def _find(pattern, what):
        hits = glob.glob(f'/kaggle/input/**/{pattern}', recursive=True)
        if not hits:
            raise SystemExit(f'{what} not found. Add Input -> Datasets -> {what}, or set SCORER_LIKE = False.')
        return Path(hits[0]).parent
    EXTRA = _find('inline_snapshot-*.whl', 'zbigniewkirchner/gemma-4-agent-local-eval-wheels')
    PYDS = _find('cpython-3.12-linux.tgz.bin', 'zbigniewkirchner/gemma-4-agent-local-eval-pythons')
    NB_TAG = f'cp{sys.version_info.major}{sys.version_info.minor}'
    if NB_TAG != 'cp313':
        print(f'warning: notebook Python is {NB_TAG}; the scorer image uses 3.13')

    def fits(w, tag=NB_TAG):
        py, abi, plat = w.name[:-4].split('-')[-3:]
        if plat != 'any' and 'linux' not in plat:
            return False
        if abi == 'abi3':
            return int(py.split('.')[0][2:]) <= int(tag[2:])
        return any(t.startswith('py3') for t in py.split('.')) or tag in py.split('.')

    norm = lambda n: re.sub(r'[-_.]+', '_', n).lower()
    WHEELS = {}
    for w in [*(DATA_DIR / 'wheels').glob('*.whl'), *EXTRA.glob('*.whl'), *PYDS.glob('*.whl')]:
        n_, v_ = w.name.split('-')[:2]
        WHEELS.setdefault(norm(n_), []).append((Version(v_), w))
    OWN = {'fastapi/fastapi': 'fastapi', 'Textualize/rich': 'rich', 'psf/requests': 'requests', 'encode/httpx': 'httpx'}
    ONLY_FOR = {'pytest_httpbin': {'psf/requests'}, 'httpbin': {'psf/requests'}, 'flasgger': {'psf/requests'},
                'brotlicffi': {'psf/requests', 'encode/httpx'}, 'brotli': {'encode/httpx'}, 'zstandard': {'encode/httpx'}}
    PY = {NB_TAG: Path(sys.executable)}

    def python_for(tag):
        if tag not in PY:
            ver = f'{tag[2]}.{tag[3:]}'
            dest = WORK / f'py{tag}'
            if not (dest / 'python' / 'bin' / f'python{ver}').exists():
                with tarfile.open(PYDS / f'cpython-{ver}-linux.tgz.bin', 'r:gz') as t:
                    t.extractall(dest)
            PY[tag] = dest / 'python' / 'bin' / f'python{ver}'
        return PY[tag]

    BASE = {}
    def base_for(repo, tag):
        if (repo, tag) not in BASE:
            chosen = {}
            for name, opts in WHEELS.items():
                opts = [(v, w) for v, w in opts if fits(w, tag)]
                if not opts or name == OWN[repo] or (name in ONLY_FOR and repo not in ONLY_FOR[name]):
                    continue
                comp = [(v, w) for v, w in opts if w.parent == DATA_DIR / 'wheels']
                if name in ('pytest', 'pytest_timeout'):
                    chosen[name] = next(w for v, w in opts if str(v) in ('8.4.2', '2.1.0'))
                elif comp:
                    chosen[name] = max(comp)[1]
                elif name != 'pygments':
                    chosen[name] = max(opts)[1]
            d = WORK / f'scorer_site_{OWN[repo]}_{tag}'
            shutil.rmtree(d, ignore_errors=True)
            subprocess.run([str(python_for(tag)), '-m', 'pip', 'install', '-q', '--no-index', '--no-deps',
                            '--ignore-requires-python', '--target', str(d), *map(str, chosen.values())])
            for shim in ('imp.py', 'telnetlib.py'):
                shutil.copy(DATA_DIR / 'docker' / shim, d / shim)
            BASE[(repo, tag)] = (d, chosen)
        return BASE[(repo, tag)]

    CALIBRATION = {
        'rich_3064': {'pygments': '2.15.1'}, 'rich_3130': {'pygments': '2.15.1'}, 'rich_3296': {'pygments': '2.16.1'},
        'rich_3469': {'pygments': '2.18.0'}, 'rich_3782': {'pygments': '2.19.2'}, 'rich_4070': {'pygments': '2.19.2'},
        'rich_4079': {'pygments': '2.20.0'},
        'requests_6589': {'werkzeug': '2.3.8', 'flask': '2.3.3'}, 'requests_6592': {'werkzeug': '2.3.8', 'flask': '2.3.3'},
        'requests_6629': {'werkzeug': '2.3.8', 'flask': '2.3.3'}}
    TASK_PYTHON = {'requests_6757': 'cp312', 'rich_3472': 'cp312'}
    ASYNC_SHIM = {'fastapi_15745', 'fastapi_15763', 'fastapi_15785'}
    NO_CERT_TIME = {'requests_6757'}

    SHIM = WORK / 'shims'
    (SHIM / 'swe_async_shim-0.1.dist-info').mkdir(parents=True, exist_ok=True)
    (SHIM / 'swe_async_shim-0.1.dist-info' / 'METADATA').write_text('Metadata-Version: 2.1\\nName: swe-async-shim\\nVersion: 0.1\\n')
    (SHIM / 'swe_async_shim-0.1.dist-info' / 'entry_points.txt').write_text('[pytest11]\\nswe_async_shim = swe_async_shim\\n')
    (SHIM / 'swe_async_shim.py').write_text(
        'import asyncio, inspect\\nimport pytest\\n\\n\\n@pytest.hookimpl(tryfirst=True)\\n'
        'def pytest_pyfunc_call(pyfuncitem):\\n'
        '    if inspect.iscoroutinefunction(pyfuncitem.obj):\\n'
        '        args = {a: pyfuncitem.funcargs[a] for a in pyfuncitem._fixtureinfo.argnames}\\n'
        '        asyncio.run(pyfuncitem.obj(**args))\\n'
        '        return True\\n')
    (SHIM / 'swe_no_cert_time.py').write_text(
        'import ssl\\n\\n_new = ssl.SSLContext.__new__\\n\\n\\ndef _new_no_time(cls, *args, **kwargs):\\n'
        '    ctx = _new(cls, *args, **kwargs)\\n    ctx.verify_flags |= 0x200000\\n    return ctx\\n\\n\\n'
        'ssl.SSLContext.__new__ = staticmethod(_new_no_time)\\n')

    def poetry_to_pep440(spec):
        spec = spec if isinstance(spec, str) else spec.get('version', '')
        m = re.fullmatch(r'\\^(\\d+)(\\.\\d+)?(\\.\\d+)?', spec.strip())
        return f'>={spec.strip()[1:]},<{int(m.group(1)) + 1}' if m else ('' if spec.strip() == '*' else spec)

    PICKS = {}
    def setup_env(docker, sandbox_id, repo='', **kwargs):
        tid = CURRENT['id']
        tag = TASK_PYTHON.get(tid, NB_TAG)
        site = Path(docker.exec(sandbox_id, 'python -c "import site; print(site.getsitepackages()[0])"').stdout.strip())
        if tag != NB_TAG:
            venv_dir = site.parents[2]
            subprocess.run([str(python_for(tag)), '-m', 'venv', '--clear', '--without-pip', str(venv_dir)], check=True)
            site = next(venv_dir.glob('lib/python3*/site-packages'))
        ws = docker.exec(sandbox_id, 'pwd').stdout.strip()
        base, chosen = base_for(repo, tag)
        (site / '00_src.pth').write_text(f'{ws}/src\\n')
        (site / '01_scorer_base.pth').write_text(f'{base}\\n')
        (site / 'zz_workspace_paths.pth').write_text('\\n'.join(str(p) for p in Path(ws).iterdir()
                                                               if p.is_dir() and not p.name.startswith('.')) + '\\n')
        if tid in ASYNC_SHIM:
            (site / '02_async_shim.pth').write_text(f'{SHIM}\\n')
        if tid in NO_CERT_TIME:
            (site / '03_no_cert_time.pth').write_text(f'import sys; sys.path.insert(0, {str(SHIM)!r}); import swe_no_cert_time\\n')
        try:
            data = tomllib.loads(Path(ws, 'pyproject.toml').read_text())
        except Exception:
            data = {}
        reqs = list(data.get('project', {}).get('dependencies', []))
        reqs += [n + poetry_to_pep440(s) for n, s in data.get('tool', {}).get('poetry', {}).get('dependencies', {}).items() if n != 'python']
        picks, queue, seen = {}, list(reqs), set()
        while queue:
            try:
                req = Requirement(queue.pop(0))
            except Exception:
                continue
            key = norm(req.name)
            if key in seen or key == OWN.get(repo) or (req.marker and not req.marker.evaluate({'extra': ''})):
                continue
            seen.add(key)
            options = [(v, w) for v, w in WHEELS.get(key, []) if fits(w, tag) and req.specifier.contains(v, prereleases=True)
                       and not (key in ONLY_FOR and repo not in ONLY_FOR[key])]
            if options:
                best = max(options)[1]
                if best != chosen.get(key):
                    picks[key] = best
                with zipfile.ZipFile(best) as z:
                    meta = next(n for n in z.namelist() if n.endswith('.dist-info/METADATA'))
                    queue += [l.split(':', 1)[1].strip() for l in z.read(meta).decode().splitlines() if l.startswith('Requires-Dist:')]
        for name, ver in CALIBRATION.get(tid, {}).items():
            picks[name] = next(w for v, w in WHEELS[name] if str(v) == ver and fits(w, tag))
        if picks:
            subprocess.run([str(python_for(tag)), '-m', 'pip', 'install', '-q', '--no-index', '--no-deps', '--upgrade',
                            '--ignore-requires-python', '--target', str(site), *map(str, picks.values())])
        PICKS[tid] = [tag] + sorted(p.name.split('-')[0] + '==' + p.name.split('-')[1] for p in picks.values())

    verification.install_test_dependencies = setup_env
    agent_runner.install_test_dependencies = setup_env
    print('scorer-like sandbox hook installed')
"""),
(CODE, """# Gold check: grade the reference patch of every selected task in this sandbox (no model needed).
# Expect all of them to pass with SCORER_LIKE = True; a failure means the environment, not the agent, would fail that task.
if GOLD_CHECK:
    import asyncio as _aio, concurrent.futures as _cf
    from swegemma.config import EvalConfig as _EC
    from swegemma.evaluate import Evaluator as _Ev
    from adk_eval_core.tracing import SessionTrace
    class GoldEvaluator(_Ev):
        async def _run_agent_sandbox(self, task, snapshot_path, task_index, total_tasks, **kwargs):
            return task.patch, None, SessionTrace()
    gev = GoldEvaluator(_EC(tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / 'snapshots', results_dir=WORK / 'gold_check',
                            submission_dir=WORK, models=None, sandbox='subprocess', wheels_dir=DATA_DIR / 'wheels',
                            graph_dir=str(DATA_DIR / 'graphs'), embeddings_dir=str(DATA_DIR / 'embeddings'),
                            timeout_seconds=300, verification_timeout_seconds=300, display_mode='quiet'))
    if SCORER_LIKE:
        gev.sandbox = gev.docker = SubprocessManager(timeout_seconds=300, system_site_packages=False)
    gold, t0 = {}, time.time()
    with _cf.ThreadPoolExecutor(max_workers=1) as pool:
        for t in sel:
            CURRENT['id'] = t.instance_id
            try:
                gold[t.instance_id] = bool(pool.submit(_aio.run, gev.evaluate_task(task=t)).result().resolved)
            except Exception as e:
                gold[t.instance_id] = False; print(t.instance_id, repr(e)[:200])
    bad = [k for k, v in gold.items() if not v]
    print(f'gold patches pass: {sum(gold.values())}/{len(gold)} in {time.time() - t0:.0f}s; failing: {bad}')
    (WORK / 'results').mkdir(exist_ok=True)
    (WORK / 'results' / 'gold_check.json').write_text(json.dumps(gold, indent=1))
"""),
(MD, "## 4. Start the model server (same settings as the scorer)"),
(CODE, """import litellm, torch
from adk_submission import VllmConfig, VllmServer, discover_adapters
from adk_submission.discovery import discover_declared_models
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS
litellm.drop_params = True

MODEL_VLLM_EXTRA_ARGS = {'gemma-4-12b-it-qat-w4a16-ct': ('--hf-overrides', '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}')}
declared = discover_declared_models(AGENT_DIR)
assert len(declared) == 1, declared
declared_model = next(iter(declared))
MODEL_PATH = Path(f'/kaggle/input/models/google/gemma-4/other/{declared_model}/2')
if not MODEL_PATH.exists():
    alt = glob.glob(f'/kaggle/input/models/**/{declared_model}/*', recursive=True)
    assert alt, f'Model weights for {declared_model} not attached.'
    MODEL_PATH = Path(sorted(alt)[-1])

adapters = discover_adapters(str(AGENT_DIR), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
adapter_map = getattr(adapters, 'adapters', None) or {}
ranks = [r for i in adapter_map.values() if (r := getattr(i, 'rank', None))]
gpus = torch.cuda.device_count() if torch.cuda.is_available() else 1
tp = 4 if gpus >= 4 else (2 if gpus >= 2 else 1)

if 'server_instance' in globals() and server_instance is not None:
    server_instance.stop()
server_instance = VllmServer(VllmConfig(
    model=str(MODEL_PATH), port=8000, host='127.0.0.1', tool_call_parser='gemma4', reasoning_parser='gemma4',
    max_model_len=32768, dtype='bfloat16' if (torch.cuda.is_available() and torch.cuda.is_bf16_supported()) else 'auto',
    gpu_memory_utilization=0.90, enable_auto_tool_choice=True, enable_lora=bool(adapter_map),
    max_loras=max(1, len(adapter_map)), max_lora_rank=max(ranks) if ranks else 128, scheduler_reserve_full_isl=False,
    tensor_parallel_size=tp, startup_timeout=60 * 20, extra_args=MODEL_VLLM_EXTRA_ARGS.get(declared_model, ())),
    adapter_manifest=adapters)
server_instance.start()
models = server_instance.create_model_registry(aliases=[declared_model], model_prefix='openai/',
                                               api_key=os.environ.get('LOCAL_API_KEY', 'EMPTY'))
print(f'vLLM up: {declared_model} tp={tp}')
"""),
(MD, """## 5. Run the tasks

Each finished task is appended to `runner_results.jsonl` immediately, so a crash or a
session timeout keeps everything done so far. Rerunning the cell skips tasks already recorded."""),
(CODE, """import asyncio, concurrent.futures, yaml
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps._configs import EventsCompactionConfig
from swegemma.config import EvalConfig, build_submission_limits
from swegemma.evaluate import Evaluator

def run_sync(fn, *args, **kwargs):
    call = lambda: fn(*args, **kwargs)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(call())).result()
    return asyncio.run(call())

limits, gen_constraints = build_submission_limits()

def as_record(task, result, wall):
    rec = {'instance_id': task.instance_id, 'repo': task.repo, 'wall_seconds': round(wall, 1)}
    # keep every simple attribute the result object exposes, so nothing is lost
    for k, v in (vars(result) if hasattr(result, '__dict__') else {}).items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            rec[k] = v
    for k in ('resolved', 'test_exit_code', 'tool_calls', 'duration_seconds', 'agent_patch', 'error', 'agent_error'):
        if hasattr(result, k):
            v = getattr(result, k)
            rec[k] = v if isinstance(v, (str, int, float, bool)) or v is None else str(v)
    return rec

SESSION = globals().get('SESSION') or f"{datetime.now(timezone.utc):%Y%m%d_%H%M}"   # kept on cell rerun, so a rerun resumes
RUN_DIRS, RUN_BUNDLE_IDS = [], []
t_start = globals().get('t_start') or time.time()

def run_bundle(name, rep):
    prepare_bundle(name, quiet=True)                  # put this bundle in AGENT_DIR
    bid = BUNDLE_IDS[name]
    single = len(BUNDLE_LIST) * REPEATS == 1
    run_id = RUN_ID if (RUN_ID and single) else f"{name}_{MODE}_{SESSION}" + (f"_r{rep}" if REPEATS > 1 else "")
    run_dir = WORK / 'results' / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / 'run_meta.json').write_text(json.dumps({
        'run_id': run_id, 'bundle': name, 'bundle_id': bid, 'mode': MODE, 'repeat': rep,
        'model_override': MODEL_OVERRIDE, 'tasks_file_sha': task_hash, 'n_tasks': len(sel), 'scorer_like': SCORER_LIKE,
        'task_ids': [t.instance_id for t in sel], 'started_utc': datetime.now(timezone.utc).isoformat()}, indent=2))

    cfg_file = next((c for n in ('eval_config.yaml', 'eval_config.yml') if (c := AGENT_DIR / n).is_file()), None)
    raw = (yaml.safe_load(cfg_file.read_text()) or {}) if cfg_file else {}
    ev = raw.get('evaluation', raw)
    eval_config = EvalConfig(
        tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / 'snapshots', results_dir=run_dir / 'harness',
        submission_dir=AGENT_DIR, models=models, sandbox='subprocess',
        timeout_seconds=int(ev.get('timeout_seconds', 300)), verification_timeout_seconds=300,
        max_time_minutes=float(ev.get('max_time_minutes', 60.0)), max_tool_calls=int(ev.get('max_tool_calls', 100)),
        max_turns=int(ev['max_turns']) if ev.get('max_turns') is not None else None,
        limits=limits, generation_constraints=gen_constraints, adapter_manifest=adapters,
        # these two mirror the scorer (HARNESS_README section 7.2)
        context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
        events_compaction_config=EventsCompactionConfig(compaction_interval=15, overlap_size=2,
                                                        token_threshold=14336, event_retention_size=5),
        graph_dir=str(DATA_DIR / 'graphs'), embeddings_dir=str(DATA_DIR / 'embeddings'),
        wheels_dir=DATA_DIR / 'wheels', verbose=False)
    evaluator = Evaluator(eval_config)
    if SCORER_LIKE:     # clean venv per sandbox, like the scorer image (the hook in 3b adds its packages)
        evaluator.sandbox = evaluator.docker = SubprocessManager(timeout_seconds=int(ev.get('timeout_seconds', 300)),
                                                                 system_site_packages=False)

    out = run_dir / 'runner_results.jsonl'
    done = {json.loads(l)['instance_id'] for l in out.read_text().splitlines() if l.strip()} if out.exists() else set()
    (run_dir / 'patches').mkdir(exist_ok=True)
    print(f'===== {run_id}  bundle {bid}  {len(sel)} tasks ({len(done)} already done) =====')
    for i, task in enumerate(sel, 1):
        if task.instance_id in done:
            continue
        if (time.time() - t_start) / 3600 > STOP_AFTER_HOURS:
            print('time limit reached, stopping'); break
        t0 = time.time()
        CURRENT['id'] = task.instance_id
        try:
            result = run_sync(evaluator.evaluate_task, task=task, task_index=i, total_tasks=len(sel))
            rec = as_record(task, result, time.time() - t0)
        except Exception as e:
            rec = {'instance_id': task.instance_id, 'repo': task.repo, 'resolved': False,
                   'error': f'{type(e).__name__}: {e}'[:2000], 'wall_seconds': round(time.time() - t0, 1)}
        patch = (rec.get('agent_patch') or '').strip()
        (run_dir / 'patches' / f'{task.instance_id}.patch').write_text(patch)
        with out.open('a') as f:
            f.write(json.dumps(rec, default=str) + '\\n')
        print(f"[{i}/{len(sel)}] {task.instance_id}: resolved={rec.get('resolved')} "
              f"calls={rec.get('tool_calls')} {rec.get('wall_seconds')}s patch={len(patch)} "
              f"{(rec.get('error') or rec.get('agent_error') or '')[:80]}")
    # per-run ledger and trace statistics (why tasks failed)
    r = subprocess.run([sys.executable, str(REPO_DIR / 'scripts' / 'build_ledger.py'), str(run_dir), '--bundle-id', bid,
                        '--tasks', str(TASKS_PATH), '--results-file', 'runner_results.jsonl',
                        '--tool-cap', str(ev.get('max_tool_calls', 100)), '--out', str(run_dir / 'ledger.csv')],
                       capture_output=True, text=True)
    print(r.stdout, r.stderr)
    ts = subprocess.run([sys.executable, str(REPO_DIR / 'scripts' / 'trace_stats.py'), str(run_dir / 'harness' / 'traces'),
                         '--out', str(run_dir / 'trace_stats.csv')], capture_output=True, text=True)
    print(ts.stdout[-3000:], ts.stderr[-500:])
    RUN_DIRS.append(run_dir); RUN_BUNDLE_IDS.append(bid)

for rep in range(1, REPEATS + 1):                     # repeat-major order, so slow drift hits every bundle equally
    for name in BUNDLE_LIST:
        if (time.time() - t_start) / 3600 > STOP_AFTER_HOURS:
            print('time limit reached, no further runs'); break
        run_bundle(name, rep)
print(f'all runs done in {(time.time() - t_start) / 60:.1f} min')
"""),
(MD, "## 6. Ledger and summary"),
(CODE, """import pandas as pd
ALL = WORK / 'results' / f'ledger_all_{SESSION}.csv'
r = subprocess.run([sys.executable, str(REPO_DIR / 'scripts' / 'build_ledger.py'), *map(str, RUN_DIRS),
                    '--bundle-id', *RUN_BUNDLE_IDS, '--tasks', str(TASKS_PATH), '--results-file', 'runner_results.jsonl',
                    '--tool-cap', str(max(int((yaml.safe_load((REPO_DIR / 'bundles' / n / 'eval_config.yaml').read_text()) or {}).get('max_tool_calls', 28)) for n in BUNDLE_LIST)), '--out', str(ALL)], capture_output=True, text=True)
print(r.stdout[-6000:], r.stderr[-1500:])

L = pd.read_csv(ALL, dtype={'bundle_id': str, 'run_id': str, 'instance_id': str})
L['secs'] = pd.to_numeric(L['duration_s'], errors='coerce')
L['bundle'] = L['bundle_id'].map({v: k for k, v in BUNDLE_IDS.items()})
tab = L.groupby(['bundle', 'run_id']).agg(
    tasks=('instance_id', 'count'), resolved=('resolved', 'sum'),
    overflow=('failure_type', lambda s: (s == 'context_overflow').sum()),
    timeout=('failure_type', lambda s: (s == 'timeout').sum()),
    tests_failed=('failure_type', lambda s: (s == 'tests_failed').sum()),
    median_s=('secs', 'median'), p90_s=('secs', lambda s: s.quantile(0.9)))
print('\\nCOMPARISON (same tasks, one row per run)'); print(tab.round(0).to_string())
print('\\nPER TASK (1 = resolved)')
print(L.pivot_table(index='instance_id', columns='run_id', values='resolved', aggfunc='max').astype(float).fillna(-1).astype(int).to_string())   # -1 = not run
"""),
(MD, """## 7. Package

`submission.zip` is the first bundle's validated zip (`submission_<bundle>.zip` for each one). Submit only after the pilot looks right.
`results_<SESSION>.zip` holds every run's outputs and traces: download it and send it back for analysis."""),
(CODE, """for name in BUNDLE_LIST:
    shutil.copyfile(ZIPS[name], WORK / f'submission_{name}.zip')
    c = subprocess.run([sys.executable, str(REPO_DIR / 'scripts' / 'check_submission_zip.py'), str(WORK / f'submission_{name}.zip'),
                        '--bundle', str(REPO_DIR / 'bundles' / name)] if not MODEL_OVERRIDE else
                       [sys.executable, str(REPO_DIR / 'scripts' / 'check_submission_zip.py'), str(WORK / f'submission_{name}.zip')],
                       capture_output=True, text=True)
    print(f'--- zip check: {name} ---'); print(c.stdout, c.stderr)
    assert c.returncode == 0, f'submission_{name}.zip failed the zip check; do not upload it'
shutil.copyfile(ZIPS[BUNDLE_LIST[0]], WORK / 'submission.zip')     # with several bundles, submit the one you choose
arc = shutil.make_archive(str(WORK / f'results_{SESSION}'), 'zip', root_dir=WORK / 'results')
print('submission (first bundle):', WORK / 'submission.zip', '| per bundle:', [f'submission_{n}.zip' for n in BUNDLE_LIST])
print('results   :', arc)
try:
    server_instance.stop()
except Exception:
    pass
"""),
]


def build() -> dict:
    cells = []
    for n, (kind, src) in enumerate(CELLS):
        cell = {"cell_type": kind, "id": f"cell{n:02d}", "metadata": {}, "source": src.strip("\n").splitlines(keepends=True)}
        if kind == CODE:
            cell.update({"execution_count": None, "outputs": []})
        cells.append(cell)
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                                        "name": "python3"},
                                         "language_info": {"name": "python"}},
            "nbformat": 4, "nbformat_minor": 5}


if __name__ == "__main__":
    out = Path(__file__).with_name("kaggle_runner.ipynb")
    out.write_text(json.dumps(build(), indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}")
