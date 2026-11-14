# Baymax API

Python 3.12 + FastAPI is the approved backend target. This supporting foundation
adds project metadata and checks only; it does not implement API routes, auth,
database access, or business logic.

From this directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pytest
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. See
[local development](../../docs/development/LOCAL_DEVELOPMENT.md) and the
[implementation handoff](../../docs/IMPLEMENTATION_HANDOFF.md).
