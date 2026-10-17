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
- `all`: every task (~6.5 h for 129 tasks at ~3 min each; keep an eye on your GPU quota).

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
"""),
(MD, "## 1. Environment (same as the official starter)"),
(CODE, """import glob, importlib, json, logging, os, re, shutil, subprocess, sys, time, hashlib
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
        for yp in [AGENT_DIR / 'agent.yaml', *sorted((AGENT_DIR / 'sub_agents').glob('*.yaml'))]:
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

for name in BUNDLE_LIST:
    prepare_bundle(name)

# One vLLM server serves the whole session, so every bundle must declare the same base model.
base_models = {n: (MODEL_OVERRIDE or re.search(r'^\\s*model:\\s*(\\S+)', (REPO_DIR / 'bundles' / n / 'agent.yaml').read_text(), re.M).group(1))
               for n in BUNDLE_LIST}
assert len(set(base_models.values())) == 1, f'bundles use different models, run them in separate sessions: {base_models}'
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
elif MODE == 'all':
    sel = list(tasks)
else:
    raise ValueError(MODE)

task_hash = hashlib.sha256(TASKS_PATH.read_bytes()).hexdigest()[:12]
print(f'{len(sel)} tasks selected (tasks file {task_hash})')
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
        'model_override': MODEL_OVERRIDE, 'tasks_file_sha': task_hash, 'n_tasks': len(sel),
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
