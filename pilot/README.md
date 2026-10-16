# Pilot task list

`pilot_ids.txt` is the fixed task list used for every A/B comparison. Create it once from the
run_02 ledger and commit it; do not change it afterwards.

```bash
python scripts/pick_pilot.py ledger/run_02.csv --per-outcome 8 --out pilot/pilot_ids.txt
```

That picks 8 tasks each that were resolved, failed tests, and overflowed in run_02, spread across
repos in proportion. Until this file exists, the runner notebook's `pilot` mode will fail; use
`smoke` or `ids` instead.
