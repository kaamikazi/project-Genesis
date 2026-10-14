from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from .experiments import PairedExperiments, benchmark, metrics
from .models import Scenario, digest
from .storage import Store


def write(path: str, value):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(value, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(prog="genesis", description="GENESIS offline world laboratory")
    parser.add_argument("--db", default="data/genesis.sqlite")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    for name in ("new", "demo"):
        sub = commands.add_parser(name)
        sub.add_argument("--seed", type=int, default=42)
        sub.add_argument("--restricted", action="store_true")
        sub.add_argument("--baseline", action="store_true")
        sub.add_argument("--scenario")
        sub.add_argument("--ticks", type=int, default=80)
        sub.add_argument("--removal", choices=["none", "creators", "matched"], default="none")
        sub.add_argument("--removal-tick", type=int, default=80)
        if name == "demo":
            sub.add_argument("--out", default="evidence/offline-demo.json")
    commands.add_parser("list")
    for name in ("step", "replay", "fork", "checkpoint", "export"):
        sub = commands.add_parser(name)
        sub.add_argument("run_id")
        if name in ("replay", "fork"):
            sub.add_argument("tick", type=int)
        if name == "step":
            sub.add_argument("--ticks", type=int, default=1)
        if name == "export":
            sub.add_argument("--out", required=True)
    imp = commands.add_parser("import")
    imp.add_argument("path")
    compare = commands.add_parser("compare")
    compare.add_argument("--seeds", type=int, nargs="+", default=[11, 42, 77])
    compare.add_argument("--ticks", type=int, default=160)
    compare.add_argument("--removal-tick", type=int)
    compare.add_argument("--out", default="evidence/comparison")
    bench = commands.add_parser("benchmark")
    bench.add_argument("--ticks", type=int, default=60)
    bench.add_argument("--out", default="evidence/benchmark.json")
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        from .api import create_app
        uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)
        return
    if args.command == "compare":
        report = PairedExperiments().run(args.seeds, args.ticks, args.out, args.removal_tick)
        summary = [{"seed": a["seed"], "condition": a["condition"], "status": a["status"],
                    **({k: a["metrics"][k] for k in ("produced", "energy_per_alloy", "adoptions", "energy_per_alloy_after_removal", "uses_after_creator_removal")} if a["status"] == "completed" else {"failure": a.get("failure")})}
                   for a in report["attempts"]]
        print(json.dumps({"completed": report["completed_runs"], "attempted": len(report["attempts"]), "runs": summary, "output": args.out}, indent=2))
        return
    store = Store(args.db)
    if args.command in ("new", "demo"):
        config = Scenario.model_validate_json(Path(args.scenario).read_text()) if args.scenario else Scenario(seed=args.seed, sharing=not args.restricted, controller="baseline" if args.baseline else "search", max_ticks=max(300, args.ticks), removal=args.removal, removal_tick=args.removal_tick)
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
        print(store.fork(args.run_id, args.tick))
    elif args.command == "checkpoint":
        print(json.dumps(store.checkpoint(args.run_id)))
    elif args.command == "export":
        write(args.out, store.export(args.run_id))
        print(args.out)
    elif args.command == "import":
        path = Path(args.path)
        text = gzip.decompress(path.read_bytes()).decode("utf-8") if path.suffix == ".gz" else path.read_text(encoding="utf-8")
        print(store.import_run(json.loads(text)))
    elif args.command == "benchmark":
        result = benchmark(store, args.ticks)
        write(args.out, result)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
