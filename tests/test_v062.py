"""v0.6.2: the Gemini wire schema defect found by the first live smoke run (2026-10-17) is reproduced offline and fixed.
Live, genesis-gemini-wire-1 (`params` as an object without properties) made constrained decoding return
`"params": {}` for every parameterised action. The constrained mock below imitates that behaviour."""
import json
from pathlib import Path

import pytest

from genesis.engine import OPTIONAL_PARAMS, PARAMS
from genesis.model import gemini
from genesis.model.fixtures import GeminiFixtureResponder, constrain_to_schema, gemini_in_process_transport
from genesis.model.profile import GEMINI_ORIGIN, AdapterConfig, Ceilings, ModelProfile, OperatorConfirmations, config_hash
from genesis.model.recorded import reexecute
from genesis.model.runtime import LiveCallsDisabled
from genesis.model.schema import parse_proposal
from genesis.models import Scenario
from genesis.storage import Store

ROOT = Path(__file__).resolve().parent.parent
BIG = Ceilings(requests=500, input_tokens=10**8, output_tokens=10**7, controller_time_ms=10**8)


def adapter(wire, **kw):
    return AdapterConfig(**{**dict(provider="gemini", base_url="http://127.0.0.1:9", model="gemini-3.5-flash-lite", thinking_level="minimal",
                                   max_output_tokens=1024, wire_schema=wire), **kw})


def run(tmp_path, wire, ticks=30, name="w.sqlite"):
    responder = GeminiFixtureResponder(constrain=True)
    store = Store(tmp_path / name)
    rid = store.create(Scenario(seed=101, task="workshop-1", ore_per_site=900),
                       model_profile=ModelProfile(mode="fixture", agents=["a01"], adapter=adapter(wire), run_budget=BIG, agent_budget=BIG, lease_grace_ms=0))
    store.model_transports[rid] = gemini_in_process_transport(responder)
    for _ in range(ticks):
        store.step(rid)
    return store, rid


def test_wire1_reproduces_the_live_empty_params_failure_offline(tmp_path):
    store, rid = run(tmp_path, None)
    rows = store.model_calls(rid)
    errors = [r["parse_error"] for r in rows if r.get("parse_error")]
    assert errors and all("needs parameters" in e and "got []" in e for e in errors)


def test_wire2_lets_parameterised_actions_through(tmp_path):
    store, rid = run(tmp_path, "genesis-gemini-wire-2")
    rows = store.model_calls(rid)
    parsed = [r["parsed"] for r in rows if r.get("parsed")]
    assert not any(r.get("parse_error") for r in rows)
    assert any(p["params"] for p in parsed)                       # e.g. gather with a site, use_artifact with an artifact
    assert reexecute(store, rid)["all_matched"]


def test_wire2_types_every_expressible_kind_exactly():
    schema = gemini.wire_schema("genesis-gemini-wire-2")
    branches = {b["properties"]["kind"]["enum"][0]: b for b in schema["anyOf"]}
    assert gemini.WIRE2_EXCLUDED == ["propose_artifact"] and set(branches) == set(PARAMS) - {"propose_artifact"}
    for kind, b in branches.items():
        params = b["properties"]["params"]
        names = PARAMS[kind] | OPTIONAL_PARAMS.get(kind, set())
        assert set(params.get("properties", {})) == names and set(params.get("required", [])) == PARAMS[kind]
        assert ("standing" in b["properties"]) == (kind in {"use_artifact", "produce", "gather", "consume", "wait"})
    assert branches["move"]["properties"]["params"]["properties"]["x"] == {"type": "integer"}
    assert branches["transfer"]["properties"]["params"]["properties"]["resource"]["enum"] == ["food", "ore", "alloy"]


def test_constrained_outputs_under_wire2_satisfy_the_strict_parser():
    schema = gemini.wire_schema("genesis-gemini-wire-2")
    samples = [{"kind": "gather", "params": {"site": "s1"}, "standing": True}, {"kind": "move", "params": {"x": 3, "y": 4}},
               {"kind": "transfer", "params": {"target": "a02", "resource": "ore", "amount": 2}}, {"kind": "submit_artifact", "params": {"artifact": "x", "host": "h"}}]
    for action in samples:
        assert constrain_to_schema(action, schema) == action
        parse_proposal(json.dumps(action), 2048)
    assert constrain_to_schema({"kind": "gather", "params": {"site": "s1"}}, gemini.wire_schema("genesis-gemini-wire-1"))["params"] == {}


def test_v061_profiles_keep_their_hash_and_live_dispatch_refuses_wire1(tmp_path, monkeypatch):
    cfg = json.loads((ROOT / "config/gemini-smoke.disabled.json").read_text(encoding="utf-8"))
    assert cfg["profile"]["adapter"]["wire_schema"] == "genesis-gemini-wire-2"
    old = json.loads(json.dumps(cfg["profile"]))
    old["adapter"].pop("wire_schema")
    old["endpoint_label"] = "Gemini Developer API via Google AI Studio, free tier UNCONFIRMED"
    v061 = json.loads((ROOT / "evidence/v0.6.1/contract.json").read_text(encoding="utf-8"))["smoke_template_show"]["config_hash"]
    assert config_hash(ModelProfile.model_validate(old)) == v061
    assert config_hash(ModelProfile.model_validate(cfg["profile"])) != v061
    ok = OperatorConfirmations(free_tier_billing_disabled=True, model_available=True, quota_sufficient=True, simulation_data_only=True,
                               confirmed_by="test", confirmed_on="2026-10-17")
    monkeypatch.setenv("GENESIS_LIVE_MODEL_CALLS", "1")
    store = Store(tmp_path / "g.sqlite")
    rid = store.create(Scenario(seed=101, task="workshop-1", ore_per_site=900),
                       model_profile=ModelProfile(mode="live", agents=["a01"], adapter=adapter(None, base_url=GEMINI_ORIGIN), run_budget=BIG,
                                                  agent_budget=BIG, live_authorized=True, run_deadline_s=900, operator_confirmations=ok))
    with pytest.raises(LiveCallsDisabled, match="wire-1"):
        store.step(rid)
    assert store.model_calls(rid) == []


def test_wire1_recordings_still_reexecute(tmp_path):
    store, rid = run(tmp_path, None, ticks=20, name="old.sqlite")
    assert reexecute(store, rid)["all_matched"]
