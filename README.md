# Capacity Planning Platform

Replaces spreadsheet-based assembly-line capacity planning across EMEA plants with a single, governed web application.

- **Backend:** Python + FastAPI + SQLAlchemy (see `backend/`)
- **Frontend:** React + TypeScript + Vite (see `frontend/`)
- **Spec:** `.kiro/specs/capacity-planning-platform/`

This repository implements the design in `.kiro/specs/capacity-planning-platform/design.md`. It manages **cadence and capacity** only; it does not create planned orders or replace the SAP interface (those remain in Compass).

## Features

The frontend has two pages, switchable from the top navigation:

- **Assembly Line** — the spreadsheet-like planning grid (product lines as rows,
  ISO weeks as columns). Per cell you edit the working days, the takt/cadence,
  the assigned workers, and the **Adj. Qnty** (a manual adjustment added to or
  subtracted from the theoretical weekly output). A note can be attached to any
  cell. An **Export CSV** button downloads the current grid.
- **Official Version** — a read-only view of released official versions. Selecting
  a version shows its captured cells in a compact table and offers an **Export
  Excel** download in a tabular layout.

Key behaviours:

- **Theoretical output** = cadence output pro-rated by working days (per the
  plant's standard working week, e.g. 5-day EMEA or 6-day Istanbul).
- **Adj. Qnty** (`capacity_delta`) is added to the theoretical output to give the
  actual output (floored at zero), so planners can recover delays or add capacity.
- **Custom takt labels** — the per-cadence label (e.g. "11 + 11") is editable
  master data (`CadenceOption.label`, imported from Excel). The grid's takt
  column heading is also configurable via the `takt_label` config key
  (defaults to "Takt").
- **Linee_Collegate (Master/Slave linked lines)** — two lines that share the same
  physical output are linked. The **Master's** theoretical output is *deducted*
  from the **Slave's** output for the same week, then the Slave's Adj. Qnty is
  applied: `slave_output = slave_expected − master_expected + adj` (floored at
  zero; the deduction applies only while the Master is producing). Both lines
  keep their own cadence and workers. Links are managed via `/config/line-links`.
- **Approved combinations only** — planners can only pick technical-department
  cadences, and assigned workers must match the cadence headcount.
- **Frozen periods, versions, scenarios, notes, regional views, RBAC, and
  configuration-over-code** as described in the spec.

Relevant new/updated endpoints:

- `GET /plants/{id}/grid` — now returns `takt_label` and applies the linked-line
  deduction to Slave lines.
- `GET`/`POST`/`DELETE /config/line-links` — manage Master/Slave links
  (central-admin only; validates that both lines belong to the given plant and
  are distinct).
- `GET /versions/{id}/export.xlsx` — tabular Excel export of a saved version,
  including the takt label and Adj. Qnty columns.
- `GET /exports/compass` — the Compass spreadsheet now includes an Adj. Qnty
  column.

## Run it locally (end to end)

You need two terminals: one for the backend API, one for the frontend. Start the
backend first, then the frontend. Prerequisites: Python 3.11+ and Node.js 18+.

**Terminal 1 — backend API (http://localhost:8000):**

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

**Terminal 2 — frontend app (http://localhost:5173):**

```powershell
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173 in your browser. Interactive API docs are at
http://localhost:8000/docs.

Quick smoke check that the API is up (from any terminal):

```powershell
curl.exe http://localhost:8000/health
# -> {"status":"ok"}
```

Section details for each part follow below.

## Details

### Backend

The install and run commands are in the section above. On first start the app
creates a local SQLite database (`backend/planning.db`) and seeds it with the
EMEA plants, approved cadence options, sample lines, and a user for each role.
API docs are at http://localhost:8000/docs.

Auth in dev mode is by the `X-User` header naming a seeded user
(`admin`, `planner`, `viewer`, `limana_viewer`); it defaults to `admin` when the
header is omitted. Example:

```powershell
curl.exe -H "X-User: viewer" http://localhost:8000/plants
```

If you change the SQLAlchemy models, delete `backend/planning.db` and restart so
the schema is recreated (there are no migrations in this build).

### Frontend

The install and run commands are in the section above. The Vite dev server
proxies requests under `/api` to the FastAPI backend on port 8000 (stripping the
`/api` prefix), so start the backend first.

## Running the tests

The backend tests use pytest and live in `backend/tests`. pytest is configured
in `backend/pyproject.toml` (`testpaths = ["tests"]`, `pythonpath = ["."]`), so
run it from the `backend/` directory. The test fixtures point the app at a
throwaway SQLite database and set dev auth automatically, so no setup is needed
beyond installing the dev dependencies.

```powershell
cd backend
.\.venv\Scripts\Activate.ps1   # if not already activated
pytest
```

Useful variations (all run from `backend/`):

```powershell
pytest -v                                  # verbose
pytest tests\test_rules.py                 # a single file
pytest tests\test_api.py::test_health      # a single test
pytest -k transfer                         # tests matching a keyword
```

If you prefer not to activate the venv, invoke it directly:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

### Backend linting

```powershell
cd backend
.\.venv\Scripts\python.exe -m ruff check app tests
```

### Frontend checks

The frontend has no unit-test runner configured yet. It provides a type-check
and a production build, run from the `frontend/` directory:

```powershell
cd frontend
npm run lint     # TypeScript type-check (tsc --noEmit)
npm run build    # type-check + production build
```

## Architecture

See `.kiro/specs/capacity-planning-platform/design.md`. The backend uses a
local SQLite database by default for development and can target PostgreSQL
(RDS) in production via the `DATABASE_URL` environment variable.
