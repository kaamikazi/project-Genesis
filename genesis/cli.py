from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from .experiments import InheritanceExperiment, PairedExperiments, benchmark, metrics
from .models import Scenario, digest
from .reducer import post_removal_window, reduce_export
from .storage import Store

CURRENT_EVIDENCE = "evidence/v0.3.0"


def write(path: str, value):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(value, indent=2), encoding="utf-8")


def read_json(path: str):
    p = Path(path)
    return json.loads(gzip.decompress(p.read_bytes()).decode("utf-8") if p.suffix == ".gz" else p.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(prog="genesis", description="GENESIS offline world laboratory")
    parser.add_argument("--db", default="data/genesis.sqlite")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    for name in ("new", "demo"):
        sub = commands.add_parser(name)
        sub.add_argument("--seed", type=int, default=42)
        sub.add_argument("--population", type=int, default=8)
        sub.add_argument("--restricted", action="store_true")
        sub.add_argument("--baseline", action="store_true")
        sub.add_argument("--scenario")
        sub.add_argument("--ticks", type=int, default=80)
        sub.add_argument("--removal", choices=["none", "creators", "matched"], default="none")
        sub.add_argument("--removal-tick", type=int, default=80)
        sub.add_argument("--succession", choices=["none", "fresh"], default="none")
        sub.add_argument("--successor-access", choices=["library", "none", "direct"], default="library")
        if name == "demo":
            sub.add_argument("--out", default=f"{CURRENT_EVIDENCE}/demo/offline-demo.json")
    commands.add_parser("list")
    for name in ("step", "replay", "fork", "checkpoint", "export", "reduce-run"):
        sub = commands.add_parser(name)
        sub.add_argument("run_id")
        if name in ("replay", "fork"):
            sub.add_argument("tick", type=int)
        if name == "fork":
            sub.add_argument("--intervention", help='JSON, e.g. {"removal":"creators","removal_tick":61,"succession":"fresh"}')
            sub.add_argument("--label")
        if name == "step":
            sub.add_argument("--ticks", type=int, default=1)
        if name == "export":
            sub.add_argument("--out", required=True)
    imp = commands.add_parser("import")
    imp.add_argument("path")
    red = commands.add_parser("reduce", help="independent event-derived metrics for an export (.json or .json.gz)")
    red.add_argument("path")
    compare = commands.add_parser("compare")
    compare.add_argument("--seeds", type=int, nargs="+", default=[11, 42, 77])
    compare.add_argument("--ticks", type=int, default=160)
    compare.add_argument("--removal-tick", type=int)
    compare.add_argument("--out", default=f"{CURRENT_EVIDENCE}/comparison")
    inherit = commands.add_parser("inherit", help="controlled successor-inheritance experiment from checkpoint forks")
    inherit.add_argument("--seeds", type=int, nargs="+", default=[11, 42, 77])
    inherit.add_argument("--checkpoint", type=int, default=60)
    inherit.add_argument("--window", type=int, default=40)
    inherit.add_argument("--live-window", type=int, default=100)
    inherit.add_argument("--out", default=f"{CURRENT_EVIDENCE}/inheritance")
    bench = commands.add_parser("benchmark")
    bench.add_argument("--ticks", type=int, default=60)
    bench.add_argument("--population", type=int, default=8)
    bench.add_argument("--out", default=f"{CURRENT_EVIDENCE}/benchmark/benchmark.json")
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)
        return
    if args.command == "compare":
        report = PairedExperiments().run(args.seeds, args.ticks, args.out, args.removal_tick)
        summary = [{"seed": a["seed"], "condition": a["condition"], "status": a["status"],
                    **({"produced_alloy": a["reducer"]["overall"]["produced_alloy"],
                        "production_energy_per_alloy": a["reducer"]["overall"]["production_energy_per_alloy"]["value"]}
                       if a["status"] == "completed" else {"failure": a.get("failure")})} for a in report["attempts"]]
        print(json.dumps({"completed": report["completed_runs"], "attempted": len(report["attempts"]), "runs": summary, "output": args.out}, indent=2))
        return
    if args.command == "inherit":
        report = InheritanceExperiment().run(args.seeds, args.out, args.checkpoint, args.window, args.live_window)
        print(json.dumps({"seeds": [{"seed": s["seed"], "status": s["status"], "parity": s.get("physical_parity", {}).get("identical")} for s in report["seeds"]],
                          "aggregates": report["aggregates"], "output": args.out}, indent=2))
        return
    if args.command == "reduce":
        export = read_json(args.path)
        window = post_removal_window(export)
        print(json.dumps(reduce_export(export, [window] if window else []), indent=2))
        return
    store = Store(args.db)
    if args.command in ("new", "demo"):
        config = Scenario.model_validate_json(Path(args.scenario).read_text()) if args.scenario else Scenario(
            seed=args.seed, population=args.population, sharing=not args.restricted, controller="baseline" if args.baseline else "search",
            max_ticks=max(300, args.ticks), removal=args.removal, removal_tick=args.removal_tick,
            succession=args.succession, successor_access=args.successor_access)
        rid = store.create(config)
        if args.command == "demo":
            for _ in range(args.ticks):
                store.step(rid)
            store.checkpoint(rid)
            final = store.load(rid)
            assert digest(store.replay(rid, final["tick"])) == digest(final)
            write(args.out, store.export(rid))
            print(json.dumps({"run_id": rid, "export": args.out, "metrics": metrics(final)}, indent=2))
        else:
            print(rid)
    elif args.command == "list":
        print(json.dumps(store.list_runs(), indent=2))
    elif args.command == "step":
        if not 1 <= args.ticks <= 10000:
            parser.error("ticks must be in 1..10000")
        for _ in range(args.ticks):
            store.step(args.run_id)
        print(json.dumps(metrics(store.load(args.run_id)), indent=2))
    elif args.command == "replay":
        state = store.replay(args.run_id, args.tick)
        print(json.dumps({"tick": state["tick"], "hash": digest(state), "metrics": metrics(state)}, indent=2))
    elif args.command == "fork":
        print(store.fork(args.run_id, args.tick, json.loads(args.intervention) if args.intervention else None, args.label))
    elif args.command == "checkpoint":
        print(json.dumps(store.checkpoint(args.run_id)))
    elif args.command == "export":
        write(args.out, store.export(args.run_id))
        print(args.out)
    elif args.command == "reduce-run":
        export = store.export(args.run_id)
        window = post_removal_window(export)
        print(json.dumps(reduce_export(export, [window] if window else []), indent=2))
    elif args.command == "import":
        print(store.import_run(read_json(args.path)))
    elif args.command == "benchmark":
        result = benchmark(store, args.ticks, args.population)
        write(args.out, result)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
