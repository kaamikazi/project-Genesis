# Baseline verification before milestone 3 edits
Recorded: 2026-10-14T19:20:23.2469601+06:00
Engine on disk: ENGINE_VERSION = "0.2.0"; RULE_VERSION = "phase-world-2"; EVALUATOR_VERSION = "phase-evaluator-2"

## python -m pytest -q
```
...................................                                      [100%]
============================== warnings summary ===============================
.venv\lib\site-packages\fastapi\testclient.py:1
  E:\Project GENESIS\.venv\lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
35 passed, 1 warning in 33.56s
```

## npm run build (frontend)
```

> genesis-observatory@0.2.0 build
> tsc --noEmit && vite build

vite v8.3.4 building client environment for production...
transforming...
✓ 17 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.61 kB │ gzip:  0.40 kB
dist/assets/index-BgF53PaR.css   27.58 kB │ gzip:  6.04 kB
dist/assets/index-C6KmPO0r.js   272.70 kB │ gzip: 83.48 kB

✓ built in 181ms
```
