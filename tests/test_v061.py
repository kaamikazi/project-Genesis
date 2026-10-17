"""v0.6.1: Gemini Developer API (generateContent) adapter verified offline: envelopes, credentials, response
classification, usage with thinking, quotas, budgets, origin pinning, crash recovery and replay modes.
Only synthetic keys are used; no request leaves 127.0.0.1."""
import gzip
import json
import socket
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from genesis.model import gemini
from genesis.model.budget import totals
from genesis.model.fixtures import GeminiFixtureResponder, MockGeminiServer, gemini_in_process_transport
from genesis.model.profile import GEMINI_ORIGIN, AdapterConfig, Ceilings, ModelProfile, OperatorConfirmations, config_hash
from genesis.model.prompt import build_messages
from genesis.model.recorded import reexecute
from genesis.model.runtime import DecisionInFlight, LiveCallsDisabled, RecordingMismatch, SimulatedCrash, run_halt
from genesis.model.transport import CredentialMissing, GeminiTransport, NotDelivered
from genesis.models import Scenario, digest
from genesis.reducer import reduce_export
from genesis.storage import Store
from genesis.world import LocalObservations, new_world

ROOT = Path(__file__).resolve().parent.parent
KEY = "synthetic-gemini-test-key-0123456789"
BIG = Ceilings(requests=500, input_tokens=10**8, output_tokens=10**7, controller_time_ms=10**8)
MODEL = "gemini-3.5-flash-lite"


def scenario():
    return Scenario(seed=101, task="workshop-1", ore_per_site=900)


def gadapter(**kw):
    base = dict(provider="gemini", base_url="http://127.0.0.1:9", model=MODEL, thinking_level="minimal", request_logging=False, max_output_tokens=1024,
                wire_schema="genesis-gemini-wire-2")
    return AdapterConfig(**{**base, **kw})


def gprofile(**kw):
    base = dict(mode="fixture", agents=["a01"], adapter=gadapter(), run_budget=BIG, agent_budget=BIG, lease_grace_ms=0)
    return ModelProfile(**{**base, **kw})


def run_inproc(tmp_path, script=None, ticks=1, name="g.sqlite", **kw):
    responder = GeminiFixtureResponder(script=script)
    store = Store(tmp_path / name)
    rid = store.create(scenario(), model_profile=gprofile(**kw))
    store.model_transports[rid] = gemini_in_process_transport(responder)
    for _ in range(ticks):
        store.step(rid)
    return store, rid, responder


def model_decisions(store, rid, agent="a01"):
    return [d for e in store.export(rid)["ticks"] for d in e["record"]["decisions"] if d["action"]["agent"] == agent]


# --- envelopes and schema -----------------------------------------------------------------------------------------

def test_request_envelope_is_native_generate_content_without_ollama_fields_or_key():
    obs = LocalObservations().build(new_world(scenario()), "a01")
    messages, _ = build_messages(obs, 16000)
    url, body, headers = gemini.build_request(messages, gadapter(base_url=GEMINI_ORIGIN, seed=3).model_dump())
    req = json.loads(body)
    assert url == f"{GEMINI_ORIGIN}/v1beta/models/{MODEL}:generateContent"
    assert set(req) == {"systemInstruction", "contents", "generationConfig", "store"} and req["store"] is False
    assert req["systemInstruction"]["parts"][0]["text"] == messages[0]["content"]
    assert req["contents"] == [{"role": "user", "parts": [{"text": messages[1]["content"]}]}]
    gen = req["generationConfig"]
    assert gen["candidateCount"] == 1 and gen["maxOutputTokens"] == 1024 and gen["seed"] == 3
    assert gen["responseFormat"] == {"text": {"mimeType": "APPLICATION_JSON", "schema": gemini.wire_schema()}}
    assert gen["thinkingConfig"] == {"thinkingLevel": "MINIMAL", "includeThoughts": False}
    for ollama_field in ("messages", "options", "format", "stream", "keep_alive", "think", "model"):
        assert ollama_field not in req
    for forbidden in ("tools", "toolConfig", "cachedContent", "safetySettings", "previousInteractionId"):
        assert forbidden not in req
    assert set(headers) == {"Content-Type", "Accept"} and "key" not in url.lower()
    plain = json.loads(gemini.build_request(messages, gadapter(structured_outputs=False, request_logging=None).model_dump())[1])
    assert plain["generationConfig"]["responseFormat"] == {"text": {"mimeType": "APPLICATION_JSON"}} and "store" not in plain


def test_wire_schema_uses_only_the_documented_subset_and_the_parser_keeps_the_full_contract(tmp_path):
    allowed = {"type", "properties", "required", "additionalProperties", "enum", "description", "title", "items", "minimum", "maximum",
               "minItems", "maxItems", "format", "anyOf", "prefixItems"}

    def walk(node):
        assert set(node) <= allowed, set(node) - allowed
        for sub in (node.get("properties") or {}).values():
            walk(sub)
        for sub in node.get("anyOf") or []:
            walk(sub)
    walk(gemini.wire_schema())
    assert "maxLength" not in json.dumps(gemini.wire_schema())
    # outputs the wire schema would allow but the internal contract forbids are still parse errors
    from genesis.model.schema import ParseError, parse_proposal
    for text in ('{"kind":"wait","params":{},"explanation":"' + "x" * 201 + '"}', '{"kind":"gather","params":{}}', '{"kind":"move","params":{"x":1,"y":2,"z":3}}'):
        with pytest.raises(ParseError):
            parse_proposal(text, 2048)


def test_provider_specific_fields_cannot_be_mixed():
    with pytest.raises(ValidationError, match="do not apply"):
        AdapterConfig(provider="gemini", model=MODEL, keep_alive="5m")
    with pytest.raises(ValidationError, match="do not apply"):
        AdapterConfig(model="llama", thinking_level="low")


def test_ollama_config_hash_is_unchanged_from_v060():
    export = json.loads(gzip.decompress((ROOT / "evidence/v0.6.0/integration/integration-export.json.gz").read_bytes()))
    stored = export["model_profile"]
    profile = ModelProfile.model_validate(stored.get("profile", stored) if "profile" in stored else {k: v for k, v in stored.items() if k != "config_hash"})
    assert config_hash(profile) == export["model_ledger"][0]["identity"]["config_hash"]
    assert config_hash(gprofile()) != config_hash(profile)


# --- response classification ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("fault,expect,repairable", [
    ("blocked-prompt", "prompt blocked", False), ("no-candidates", "no candidates", False), ("two-candidates", "exactly one candidate", False),
    ("safety", "SAFETY", False), ("max-tokens", "truncated (MAX_TOKENS)", False), ("non-text-part", "non-text part", False),
    ("empty-text", "empty", True)])
def test_unusable_candidates_are_classified_and_only_parse_style_failures_are_repaired(tmp_path, fault, expect, repairable):
    store, rid, responder = run_inproc(tmp_path, script={1: fault})
    rows = store.model_calls(rid)
    assert expect in rows[0]["parse_error"] and rows[0]["usage"]["repairable"] is repairable
    assert responder.calls == (2 if repairable else 1)
    d = model_decisions(store, rid)[0]
    assert d["controller"] == ("model-proposal" if repairable else "fallback")


def test_thought_parts_are_dropped_and_never_stored(tmp_path):
    store, rid, _ = run_inproc(tmp_path, script={1: "thought-parts"})
    row = store.model_calls(rid)[0]
    assert row["parsed"] and row["usage"]["dropped_thought_parts"] == 1
    assert "FIXTURE THOUGHT" not in json.dumps(store.export(rid)) and "c2ln" not in json.dumps(store.export(rid))


def test_malformed_json_gets_one_bounded_repair(tmp_path):
    store, rid, responder = run_inproc(tmp_path, script={1: "invalid-json", 2: "invalid-json"})
    assert responder.calls == 2 and [r["role"] for r in store.model_calls(rid)] == ["primary", "repair"]
    assert model_decisions(store, rid)[0]["controller"] == "fallback"


def test_usage_normalization_counts_thinking_once_and_handles_bad_reports():
    n = gemini.normalize_usage({"promptTokenCount": 100, "cachedContentTokenCount": 40, "candidatesTokenCount": 10, "thoughtsTokenCount": 30, "totalTokenCount": 140})
    assert (n["input_tokens"], n["output_tokens"], n["thinking_tokens"], n["cached_input_tokens"], n["basis"]) == (100, 40, 30, 40, "reported")
    assert gemini.normalize_usage({"promptTokenCount": 100, "candidatesTokenCount": 10, "totalTokenCount": 111})["basis"] == "inconsistent"
    assert gemini.normalize_usage({"promptTokenCount": 100, "candidatesTokenCount": 10, "thoughtsTokenCount": float("nan")})["basis"] == "inconsistent"
    assert gemini.normalize_usage({"promptTokenCount": True, "candidatesTokenCount": 1})["basis"] == "inconsistent"
    assert gemini.normalize_usage({"candidatesTokenCount": 10})["basis"] == "incomplete"
    assert gemini.normalize_usage(None)["basis"] == "missing"


@pytest.mark.parametrize("fault", ["no-usage", "inconsistent-usage", "nonfinite-usage"])
def test_missing_or_inconsistent_usage_charges_at_least_the_reservation(tmp_path, fault):
    store, rid, _ = run_inproc(tmp_path, script={1: fault})
    row = store.model_calls(rid)[0]
    assert row["reconciled"]["basis"].startswith("estimated")
    assert row["reconciled"]["output_tokens"] >= row["reservation"]["output_tokens"] and row["reconciled"]["input_tokens"] >= row["reservation"]["input_tokens"]


def test_reported_usage_includes_thinking_in_output_and_reconciles(tmp_path):
    store, rid, _ = run_inproc(tmp_path, ticks=30, agents=["a01", "a05"])
    rows = store.model_calls(rid)
    for r in rows:
        u = r["usage"]["normalized_usage"]
        assert r["reconciled"]["output_tokens"] == u["candidate_tokens"] + u["thinking_tokens"] and r["reconciled"]["thinking_tokens"] == 24
    red = reduce_export(store.export(rid))["model"]
    assert red["reconciled"]
    t = totals(rows)
    per_agent = [totals([r for r in rows if r["agent"] == a])["committed"] for a in ("a01", "a05")]
    assert all(t["committed"][k] == per_agent[0][k] + per_agent[1][k] for k in ("requests", "input_tokens", "output_tokens"))


def test_usage_above_the_reservation_halts_further_dispatch(tmp_path):
    store, rid, responder = run_inproc(tmp_path, script={1: "overshoot"}, ticks=20)
    assert store.model_calls(rid)[0]["usage"]["reservation_exceeded"] and responder.calls == 1
    assert any("exceeded its reservation" in (d["model"] or {}).get("reason", "") for d in model_decisions(store, rid) if d["controller"] == "fallback")


# --- quotas, budgets, pacing, deadlines -------------------------------------------------------------------------

def test_http_429_stops_model_dispatch_without_retry(tmp_path):
    store, rid, responder = run_inproc(tmp_path, script={2: "http-429"}, ticks=30)
    rows = store.model_calls(rid)
    quota = [r for r in rows if r["status"] == "failed-delivered"]
    assert len(quota) == 1 and quota[0]["usage"]["halt"] == "quota" and responder.calls == 2
    assert all(r["status"] == "blocked" and "quota" in r["fallback"] for r in rows[2:])
    assert run_halt(store.model_profile(rid), [dict(r, created_at=None) for r in rows], time.time())


def test_request_ceiling_counts_repairs_for_the_run_and_each_agent(tmp_path):
    every = {i: "invalid-json" for i in range(1, 40)}
    run3 = Ceilings(requests=3, input_tokens=10**8, output_tokens=10**7, controller_time_ms=10**8)
    store, rid, responder = run_inproc(tmp_path, script=every, ticks=30, run_budget=run3)
    assert responder.calls == 3 and sum(1 for r in store.model_calls(rid) if r["status"] == "consumed") == 3
    agent2 = Ceilings(requests=2, input_tokens=10**8, output_tokens=10**7, controller_time_ms=10**8)
    store, rid, responder = run_inproc(tmp_path, script=every, ticks=30, name="b.sqlite", agents=["a01", "a05"], agent_budget=agent2)
    by_agent = {a: sum(1 for r in store.model_calls(rid) if r["agent"] == a and r["status"] != "blocked") for a in ("a01", "a05")}
    assert by_agent == {"a01": 2, "a05": 2} and responder.calls == 4


def test_output_token_ceiling_is_reserved_before_dispatch(tmp_path):
    # a request is sent only if charged usage + its full 1024-token reservation fits; after a response the actual usage
    # (candidates + thinking) is charged instead of the reservation
    below = Ceilings(requests=100, input_tokens=10**8, output_tokens=1000, controller_time_ms=10**8)
    store, rid, responder = run_inproc(tmp_path, ticks=10, run_budget=below)
    assert responder.calls == 0 and "output_tokens" in store.model_calls(rid)[0]["fallback"]
    tight = Ceilings(requests=100, input_tokens=10**8, output_tokens=1100, controller_time_ms=10**8)
    store, rid, responder = run_inproc(tmp_path, ticks=120, name="t.sqlite", run_budget=tight)
    rows = store.model_calls(rid)
    committed = totals(rows)["committed"]["output_tokens"]
    assert responder.calls >= 1 and committed <= 1100 and committed + 1024 > 1100
    assert any("output_tokens" in (r["fallback"] or "") for r in rows)


def test_local_pacing_spaces_dispatches_in_wall_clock_time(tmp_path):
    store, rid, responder = run_inproc(tmp_path, ticks=11, adapter=gadapter(min_dispatch_interval_s=0.4))
    with store.connection() as db:
        times = [r[0] for r in db.execute("SELECT created_at FROM model_calls WHERE run_id=? ORDER BY seq", (rid,))]
    assert len(times) >= 3 and all(b - a >= 0.39 for a, b in zip(times, times[1:]))


def test_run_wall_clock_deadline_stops_dispatch(tmp_path):
    store, rid, responder = run_inproc(tmp_path, ticks=1, run_deadline_s=1)
    time.sleep(1.2)
    for _ in range(10):
        store.step(rid)
    assert responder.calls == 1 and any("deadline" in (r["fallback"] or "") for r in store.model_calls(rid))


# --- credentials, origins, redirects ----------------------------------------------------------------------------

def test_missing_key_is_a_concise_setup_error_before_anything_is_reserved(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("UNRELATED_SECRET_TOKEN", "do-not-print-this-value-123")
    with MockGeminiServer(GeminiFixtureResponder()) as srv:
        store = Store(tmp_path / "k.sqlite")
        rid = store.create(scenario(), model_profile=gprofile(mode="mock-http", adapter=gadapter(base_url=srv.base_url)))
        with pytest.raises(CredentialMissing) as exc:
            store.step(rid)
    assert "GEMINI_API_KEY is not set" in str(exc.value) and "do-not-print" not in str(exc.value)
    assert store.model_calls(rid) == [] and srv.seen == []


def test_key_travels_only_in_the_header_and_never_into_records_or_api_output(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    responder = GeminiFixtureResponder(script={3: "secret-echo"})
    with MockGeminiServer(responder) as srv:
        store = Store(tmp_path / "s.sqlite")
        rid = store.create(scenario(), model_profile=gprofile(mode="mock-http", adapter=gadapter(base_url=srv.base_url)))
        for _ in range(12):
            store.step(rid)
    assert srv.seen and all(s["key_header"] == KEY and "key" not in s["path"].lower() for s in srv.seen)
    echo = store.model_calls(rid)[2]
    assert "AIza" not in (echo["response"] or "") and echo["parsed"] is None and echo["usage"]["repairable"] is False
    with store.connection() as db:
        dump = "\n".join(str(tuple(r)) for t in ("model_calls", "model_profiles", "ticks", "runs") for r in db.execute(f"SELECT * FROM {t}"))
    assert KEY not in dump and KEY not in json.dumps(store.export(rid))
    obs = LocalObservations().build(store.load(rid), "a01")
    assert KEY not in json.dumps(obs)
    from fastapi.testclient import TestClient
    from genesis.api import create_app
    client = TestClient(create_app(tmp_path / "s.sqlite"))
    summary = client.get(f"/api/runs/{rid}/model")
    assert summary.status_code == 200 and KEY not in summary.text and summary.json()["provider"] == "gemini"
    detail = client.get(f"/api/runs/{rid}/model/calls/{echo['decision_id']}")
    assert KEY not in detail.text and "AIza" not in detail.text


def test_error_text_containing_the_key_is_scrubbed(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)

    def handler(url, body, headers):
        from genesis.model.transport import WireResponse
        return WireResponse(400, json.dumps({"error": {"status": "INVALID_ARGUMENT", "message": f"bad key {KEY}"}}).encode())
    from genesis.model.transport import InProcessTransport
    store = Store(tmp_path / "e.sqlite")
    rid = store.create(scenario(), model_profile=gprofile())
    store.model_transports[rid] = InProcessTransport(handler)
    store.step(rid)
    row = store.model_calls(rid)[0]
    assert row["status"] == "failed-delivered" and KEY not in row["termination"] and "[REDACTED]" in row["termination"]


def test_transport_pins_the_official_origin_and_api_path(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    with pytest.raises(ValueError):
        GeminiTransport("live", origin="https://evil.example")
    with pytest.raises(ValueError):
        GeminiTransport.for_loopback_test("http://example.com")
    prod = GeminiTransport("live")
    for url in ("https://generativelanguage.googleapis.com.evil.example/v1beta/models/m:generateContent",
                "http://generativelanguage.googleapis.com/v1beta/models/m:generateContent",
                f"{GEMINI_ORIGIN}/v1beta/models/m:generateContent?key=x", f"{GEMINI_ORIGIN}/upload/v1beta/files",
                f"{GEMINI_ORIGIN}/v1beta/models/m:streamGenerateContent"):
        with pytest.raises(NotDelivered, match="refusing"):
            prod.send(url, b"{}", {}, 1, 100)
    with pytest.raises(ValidationError, match="official origin"):
        gprofile(mode="live", adapter=gadapter(base_url="https://proxy.example"))
    with pytest.raises(ValidationError, match="free tier only"):
        gprofile(mode="live", adapter=gadapter(base_url=GEMINI_ORIGIN), paid=True,
                 pricing={"currency": "USD", "version": "x", "input_micros_per_mtok": 1, "output_micros_per_mtok": 1},
                 run_budget=Ceilings(requests=1, input_tokens=1, output_tokens=1, controller_time_ms=1, cost_micros=1),
                 agent_budget=Ceilings(requests=1, input_tokens=1, output_tokens=1, controller_time_ms=1, cost_micros=1))


def test_redirects_are_not_followed_and_credentials_are_not_forwarded(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    with MockGeminiServer(GeminiFixtureResponder()) as target:
        with MockGeminiServer(GeminiFixtureResponder(script={1: "redirect"}), redirect_target=target.base_url + f"/v1beta/models/{MODEL}:generateContent") as srv:
            store = Store(tmp_path / "r.sqlite")
            rid = store.create(scenario(), model_profile=gprofile(mode="mock-http", adapter=gadapter(base_url=srv.base_url)))
            store.step(rid)
    row = store.model_calls(rid)[0]
    assert row["status"] == "failed-delivered" and "302 redirect refused" in row["termination"] and target.seen == []


# --- live guard -------------------------------------------------------------------------------------------------------

def test_live_gemini_needs_authorization_confirmations_deadline_and_a_key(tmp_path, monkeypatch):
    def attempt(profile, env_flag=True, key=True):
        monkeypatch.setenv("GENESIS_LIVE_MODEL_CALLS", "1") if env_flag else monkeypatch.delenv("GENESIS_LIVE_MODEL_CALLS", raising=False)
        monkeypatch.setenv("GEMINI_API_KEY", KEY) if key else monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        store = Store(tmp_path / f"{time.perf_counter_ns()}.sqlite")
        rid = store.create(scenario(), model_profile=profile)
        sent = []
        monkeypatch.setattr(GeminiTransport, "send", lambda *a, **k: sent.append(1) or (_ for _ in ()).throw(AssertionError("no live send in tests")))
        with pytest.raises((LiveCallsDisabled, CredentialMissing)) as exc:
            store.step(rid)
        assert sent == [] and store.model_calls(rid) == []
        return str(exc.value)
    ok = OperatorConfirmations(free_tier_billing_disabled=True, model_available=True, quota_sufficient=True, simulation_data_only=True,
                               confirmed_by="owner", confirmed_on="2026-10-17")
    live = dict(mode="live", adapter=gadapter(base_url=GEMINI_ORIGIN), live_authorized=True, run_deadline_s=900, operator_confirmations=ok)
    assert "GENESIS_LIVE_MODEL_CALLS" in attempt(gprofile(**live), env_flag=False)
    assert "live_authorized" in attempt(gprofile(**{**live, "live_authorized": False}))
    assert "free_tier_billing_disabled" in attempt(gprofile(**{**live, "operator_confirmations": OperatorConfirmations()}))
    assert "run_deadline_s" in attempt(gprofile(**{**live, "run_deadline_s": None}))
    assert "GEMINI_API_KEY is not set" in attempt(gprofile(**live), key=False)
    cfg = json.loads((ROOT / "config/gemini-smoke.disabled.json").read_text(encoding="utf-8"))
    assert "live_authorized" in attempt(ModelProfile.model_validate(cfg["profile"]))


def test_smoke_template_limits_are_internally_consistent():
    cfg = json.loads((ROOT / "config/gemini-smoke.disabled.json").read_text(encoding="utf-8"))
    p = ModelProfile.model_validate(cfg["profile"])
    a, b = p.adapter, p.run_budget
    assert (a.provider, a.model, p.mode, p.live_authorized, p.paid) == ("gemini", MODEL, "live", False, False)
    assert p.agents == ["a01"] and cfg["ticks"] == 40 and cfg["scenario"]["seed"] == 101 and p.scheduler.min_interval == 5 and p.concurrency == 1
    assert b.requests == 10 and p.repair_limit == 1 and b.input_tokens == 200000 and b.output_tokens == 10240 and a.max_output_tokens == 1024
    assert b.requests * a.max_input_bytes <= b.input_tokens and b.requests * a.max_output_tokens <= b.output_tokens
    assert b.requests * a.deadline_ms <= b.controller_time_ms and a.deadline_ms == 20000 and p.run_deadline_s and a.min_dispatch_interval_s > 0
    from genesis.model.runtime import SECRET_PATTERNS
    assert not any(p.search(json.dumps(cfg)) for p in SECRET_PATTERNS) and "key" not in json.dumps(cfg["profile"]).lower()


# --- crash recovery, identities, replay modes ---------------------------------------------------------------------

def test_crash_after_possible_dispatch_is_never_resent(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    responder = GeminiFixtureResponder()
    store = Store(tmp_path / "c.sqlite")
    rid = store.create(scenario(), model_profile=gprofile(adapter=gadapter(deadline_ms=50), lease_grace_ms=600))
    store.model_transports[rid] = gemini_in_process_transport(responder)
    store.model_hooks[rid] = {"during-dispatch": lambda: (_ for _ in ()).throw(SimulatedCrash("during-dispatch"))}
    with pytest.raises(SimulatedCrash):
        store.step(rid)
    other = Store(tmp_path / "c.sqlite")
    other.model_transports[rid] = gemini_in_process_transport(responder)
    with pytest.raises(DecisionInFlight):
        other.step(rid)
    time.sleep(0.8)
    other.step(rid)
    row = other.model_calls(rid)[0]
    assert row["status"] == "outcome-unknown" and responder.calls == 0 and row["reservation"]["output_tokens"] == 1024
    assert totals(other.model_calls(rid))["uncertain"]["requests"] == 1


def test_saved_gemini_response_is_reused_after_restart(tmp_path):
    responder = GeminiFixtureResponder()
    store = Store(tmp_path / "p.sqlite")
    rid = store.create(scenario(), model_profile=gprofile(adapter=gadapter(deadline_ms=50)))
    store.model_transports[rid] = gemini_in_process_transport(responder)
    store.model_hooks[rid] = {"after-persist": lambda: (_ for _ in ()).throw(SimulatedCrash("after-persist"))}
    with pytest.raises(SimulatedCrash):
        store.step(rid)
    again = Store(tmp_path / "p.sqlite")
    again.model_transports[rid] = gemini_in_process_transport(responder)
    again.step(rid)
    assert responder.calls == 1 and again.model_calls(rid)[0]["status"] == "consumed"


def test_repeated_observations_get_distinct_identities(tmp_path):
    store, rid, _ = run_inproc(tmp_path, script={1: "invalid-json"}, ticks=6)
    forks = [store.fork(rid, 5, model_profile=gprofile()) for _ in range(2)]
    for f in forks:
        store.model_transports[f] = gemini_in_process_transport(GeminiFixtureResponder())
        store.step(f)
    rows = [r for x in (rid, *forks) for r in store.model_calls(x)]
    hashes = [r["identity"]["observation_hash"] for r in rows]
    assert len(set(hashes)) < len(hashes) and len({r["decision_id"] for r in rows}) == len(rows)


def test_state_replay_and_reexecution_need_no_network(tmp_path, monkeypatch):
    store, rid, _ = run_inproc(tmp_path, script={2: "empty-text", 4: "invalid-json", 6: "safety"}, ticks=40, agents=["a01", "a05"])
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    assert digest(store.replay(rid, 40)) == digest(store.load(rid))
    report = reexecute(store, rid)
    assert report["all_matched"] and report["checked"] > 5


def test_reexecution_detects_a_tampered_gemini_recording(tmp_path):
    store, rid, _ = run_inproc(tmp_path, ticks=10)
    with store.connection() as db, db:
        db.execute("UPDATE model_calls SET response=? WHERE seq=(SELECT MIN(seq) FROM model_calls WHERE run_id=?)", ('{"kind":"wait","params":{}}', rid))
    assert not reexecute(store, rid)["all_matched"]


def test_recorded_fork_reuses_gemini_recordings_and_fails_explicitly_on_mismatch(tmp_path):
    store, rid, responder = run_inproc(tmp_path, ticks=20)
    recorded = gprofile(mode="recorded", source_run=rid)
    fork = store.fork(rid, 10, model_profile=recorded)
    for _ in range(10):
        store.step(fork)
    reused = store.model_calls(fork)
    assert reused and all(r["source"] == "recorded" and r["reconciled"]["basis"].startswith("historical") for r in reused)
    assert totals(reused)["committed"]["requests"] == 0
    diverged = store.fork(rid, 10, {"invention": "frozen"}, model_profile=recorded)
    with pytest.raises(RecordingMismatch):
        for _ in range(10):
            store.step(diverged)


# --- observer -----------------------------------------------------------------------------------------------------------

def test_observer_reports_gemini_identity_usage_and_halts(tmp_path):
    from genesis.model.observer import summary
    store, rid, _ = run_inproc(tmp_path, script={3: "http-429"}, ticks=20)
    s = summary(store, rid)
    assert s["provider"] == "gemini" and s["requested_model"] == MODEL and s["capabilities"]["adapter"] == "gemini-generatecontent-1"
    assert s["usage_totals"]["thinking_tokens"] == 48 and "quota" in s["halt"]
    assert any(c["finish_reason"] == "STOP" for c in s["calls"]) and any(c["usage"] and c["usage"].get("thinking_tokens") == 24 for c in s["calls"])
