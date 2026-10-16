"""Prints state and tick-record hashes of two offline worlds after 120 ticks. Run with PYTHONPATH set to a checkout
(used by generate_evidence_m6.py to compare v0.5.2 with the current tree)."""
import json
import tempfile
from pathlib import Path
from genesis.storage import Store
from genesis.models import Scenario, digest
import genesis
out = {"engine": genesis.ENGINE_VERSION}
for name, cfg in {"phase-1": dict(seed=7), "workshop": dict(seed=101, task="workshop-1", ore_per_site=900, lifecycle="cohorts", cohort_ticks=60, cohort_count=3, teaching=True)}.items():
    d = tempfile.mkdtemp(); s = Store(Path(d) / "x.sqlite"); rid = s.create(Scenario(**cfg))
    for _ in range(120): s.step(rid)
    st = s.load(rid); out[name] = digest({k: v for k, v in st.items()})
    out[name + "_records"] = digest([e["record"] for e in s.export(rid)["ticks"]])
print(json.dumps(out))
