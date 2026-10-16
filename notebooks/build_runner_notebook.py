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
4. Edit the config cell, then *Run All*.

**Modes**
- `smoke`: 3 tasks. Checks the bundle loads, tools work and a patch comes out (~10 min).
- `pilot`: the fixed list in `pilot/pilot_ids.txt` (~1–1.5 h for 24 tasks).
- `ids`: the ids you list in `TASK_IDS`.
- `all`: every task (~6.5 h for 129 tasks at ~3 min each; keep an eye on your GPU quota).

Results go to `/kaggle/working/results/<RUN_ID>/`. Download `results_<RUN_ID>.zip` at the end.
"""),
(CODE, """# ---------------- CONFIG: the only cell you need to edit ----------------
BUNDLE_NAME = "v3_overflow_fix"     # folder under bundles/
MODE = "smoke"                      # smoke | pilot | ids | all
TASK_IDS = []                       # used when MODE == "ids"
MODEL_OVERRIDE = None               # e.g. "gemma-4-12b-it-qat-w4a16-ct" to test another size (changes the bundle id)
RUN_ID = None                       # None -> <bundle>_<mode>_<timestamp>
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

if REPO_DIR is None:
    hits = [Path(p).parent for p in glob.glob('/kaggle/input/**/scripts/validate_bundle.py', recursive=True)]
    assert hits, 'Repo dataset not found under /kaggle/input. Attach it or set REPO_DIR.'
    REPO_DIR = hits[0].parent
REPO_DIR = Path(REPO_DIR)
SRC_BUNDLE = REPO_DIR / 'bundles' / BUNDLE_NAME
assert SRC_BUNDLE.is_dir(), f'bundle not found: {SRC_BUNDLE}'

# Work on a writable copy; the input dataset is read-only.
AGENT_DIR = WORK / 'agent'
shutil.rmtree(AGENT_DIR, ignore_errors=True); shutil.copytree(SRC_BUNDLE, AGENT_DIR)
if MODEL_OVERRIDE:
    for yp in [AGENT_DIR / 'agent.yaml', *sorted((AGENT_DIR / 'sub_agents').glob('*.yaml'))]:
        if yp.is_file():
            txt = re.sub(r'^(\\s*model:\\s*).*$', rf'\\g<1>{MODEL_OVERRIDE}', yp.read_text(), flags=re.M)
            if not MODEL_OVERRIDE.startswith('gemma-4-31b'):
                txt = re.sub(r'^\\s*adapter:\\s*.*\\n?', '', txt, flags=re.M)   # sample adapters are 31B-shaped
            yp.write_text(txt)

ZIP_DIR = WORK / 'zips'
v = subprocess.run([sys.executable, str(REPO_DIR / 'scripts' / 'validate_bundle.py'), str(AGENT_DIR), '--zip', str(ZIP_DIR)],
                   capture_output=True, text=True)
print(v.stdout, v.stderr)
assert v.returncode == 0, 'Bundle failed validation; fix it before spending GPU time.'
BUNDLE_ID = re.search(r'bundle id (\\w+)', v.stdout).group(1)
print('BUNDLE_ID =', BUNDLE_ID)
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

RUN_ID = RUN_ID or f"{BUNDLE_NAME}_{MODE}_{datetime.now(timezone.utc):%Y%m%d_%H%M}"
RUN_DIR = WORK / 'results' / RUN_ID
RUN_DIR.mkdir(parents=True, exist_ok=True)
task_hash = hashlib.sha256(TASKS_PATH.read_bytes()).hexdigest()[:12]
meta = {'run_id': RUN_ID, 'bundle': BUNDLE_NAME, 'bundle_id': BUNDLE_ID, 'mode': MODE,
        'model_override': MODEL_OVERRIDE, 'tasks_file_sha': task_hash, 'n_tasks': len(sel),
        'task_ids': [t.instance_id for t in sel], 'started_utc': datetime.now(timezone.utc).isoformat()}
(RUN_DIR / 'run_meta.json').write_text(json.dumps(meta, indent=2))
print(f'{len(sel)} tasks -> {RUN_DIR}')
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

cfg_file = next((c for n in ('eval_config.yaml', 'eval_config.yml') if (c := AGENT_DIR / n).is_file()), None)
raw = (yaml.safe_load(cfg_file.read_text()) or {}) if cfg_file else {}
ev = raw.get('evaluation', raw)
limits, gen_constraints = build_submission_limits()
eval_config = EvalConfig(
    tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / 'snapshots', results_dir=RUN_DIR / 'harness',
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

OUT = RUN_DIR / 'runner_results.jsonl'
done = {json.loads(l)['instance_id'] for l in OUT.read_text().splitlines() if l.strip()} if OUT.exists() else set()
(RUN_DIR / 'patches').mkdir(exist_ok=True)

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

t_start = time.time()
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
    (RUN_DIR / 'patches' / f'{task.instance_id}.patch').write_text(patch)
    with OUT.open('a') as f:
        f.write(json.dumps(rec, default=str) + '\\n')
    print(f"[{i}/{len(sel)}] {task.instance_id}: resolved={rec.get('resolved')} "
          f"calls={rec.get('tool_calls')} {rec.get('wall_seconds')}s patch={len(patch)} "
          f"{(rec.get('error') or rec.get('agent_error') or '')[:80]}")
print(f'done in {(time.time() - t_start) / 60:.1f} min')
"""),
(MD, "## 6. Ledger and summary"),
(CODE, """r = subprocess.run([sys.executable, str(REPO_DIR / 'scripts' / 'build_ledger.py'), str(RUN_DIR),
                    '--bundle-id', BUNDLE_ID, '--tasks', str(TASKS_PATH), '--results-file', 'runner_results.jsonl',
                    '--tool-cap', str(ev.get('max_tool_calls', 100)), '--out', str(RUN_DIR / 'ledger.csv')],
                   capture_output=True, text=True)
print(r.stdout, r.stderr)
"""),
(MD, """## 7. Package

`submission.zip` is the validated bundle (deterministic zip). Submit it only after the pilot looks right.
`results_<RUN_ID>.zip` holds the run outputs: download it and send it back for analysis."""),
(CODE, """shutil.copyfile(next(ZIP_DIR.glob('*.zip')), WORK / 'submission.zip')
arc = shutil.make_archive(str(WORK / f'results_{RUN_ID}'), 'zip', root_dir=RUN_DIR)
print('submission:', WORK / 'submission.zip')
print('results   :', arc)
try:
    server_instance.stop()
except Exception:
    pass
"""),
]


def build() -> dict:
    cells = []
    for kind, src in CELLS:
        cell = {"cell_type": kind, "metadata": {}, "source": src.strip("\n").splitlines(keepends=True)}
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
