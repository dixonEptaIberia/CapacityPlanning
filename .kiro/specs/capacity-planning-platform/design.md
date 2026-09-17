# Design Document

## Overview

The capacity planning platform replaces spreadsheet-based assembly-line capacity planning across EMEA plants (Limana, Solesino, Casale, Istanbul, France, Bradford) with a single, governed web application. It preserves the existing business logic — theoretical output from cadence × workers, approved staffing combinations, frozen periods, combined lines — while adding scenario management, versioning, notes, regional views, reporting/export, master-data import, and role-based governance.

The system is a **React + TypeScript** frontend presenting a spreadsheet-like grid, a **Python (FastAPI)** backend enforcing planning rules, and **AWS** for hosting, identity, data, and storage. It is a **cadence and capacity** tool. It does not generate planned orders and does not modify the SAP interface — those remain in Compass. The platform's integration surface is a one-way **export** of approved cadence for import into Compass, plus structured tables for Click Sense (Qlik Sense).

This design maps to the 15 requirements (R1–R15) defined in `requirements.md`.

## Architecture

```
                         +------------------+
   Browser (SPA)  <-----> |   CloudFront     |  HTTPS, CDN
                          +---------+--------+
                                    |
             static assets (S3)     |     /api/* -> API Gateway
                    +---------------+----------------+
                    |                                |
             +------v------+                  +------v---------+
             |  S3 (SPA)   |                  |  API Gateway   |
             +-------------+                  +------+---------+
                                                     |
                                              +------v-----------+
                                              | FastAPI backend  |
                                              | (Lambda/Mangum   |
                                              |  or ECS Fargate) |
                                              +--+---+----+---+--+
                                                 |   |    |   |
              +----------------+-----------------+   |    |   +------------------+
              |                |                     |    |                      |
        +-----v-----+   +------v------+       +------v----+           +----------v--------+
        | Cognito   |   | PostgreSQL  |       |    S3     |           | Export artifacts  |
        | (identity/|   | (RDS)       |       | (imports/ |           | (Compass xlsx,    |
        |  RBAC)    |   | planning db |       |  notes)   |           | Click Sense feed) |
        +-----------+   +-------------+       +-----------+           +-------------------+

  Config/Secrets: SSM Parameter Store / Secrets Manager
  Observability:  CloudWatch logs/metrics (+ optional X-Ray)
```

### Why relational (PostgreSQL/RDS) instead of a document store

The domain is highly relational and rule-driven: plants → lines → weekly cells, approved cadence combinations, linked-line relationships, versions and version diffs, and role assignments. Strong consistency, multi-row transactions (e.g., promoting a scenario to official, applying a linked-line rule across cells), and ad-hoc relational queries for regional aggregation favor a relational database. Amazon RDS for PostgreSQL is the primary choice.

### Compute model decision

Two viable options; the choice does not change the application code (FastAPI + SQLAlchemy):

- **Lambda + API Gateway (via Mangum)** — lowest ops overhead, scales to zero. Watch for cold starts and the RDS connection model (use RDS Proxy).
- **ECS Fargate behind an ALB** — steadier latency, simpler long-lived DB connections, better for heavier reporting/export jobs.

**Recommendation:** start on **ECS Fargate + RDS Proxy** because export/reporting and regional aggregation are compute- and connection-heavy, then revisit Lambda if traffic is spiky and low-volume. This is a deployment decision, not a code decision.

## Technology Decisions

| Concern | Choice | Rationale |
|---|---|---|
| Frontend build | Vite + React + TypeScript | Fast dev, first-class TS |
| Grid UI | AG Grid (or TanStack Table + virtualization) | Spreadsheet-like editing, large grids, cell styling for notes |
| Data fetching | TanStack Query + Axios | Caching, optimistic edits, request state |
| i18n | react-i18next | EN/IT required, FR/TR pluggable (R14) |
| Backend | FastAPI + Pydantic | Async, schema validation, auto OpenAPI |
| ORM/migrations | SQLAlchemy + Alembic | Relational model + versioned schema |
| Database | Amazon RDS (PostgreSQL) | Relational, transactional, aggregation |
| Identity/RBAC | Amazon Cognito + app roles | Managed auth; roles enforced in backend |
| Object storage | Amazon S3 | Excel imports, note attachments, export artifacts |
| Excel I/O | openpyxl / pandas | Master-data import, Compass export (R10, R11) |
| IaC | AWS CDK (TypeScript) | Typed infra alongside TS frontend |
| Config/secrets | SSM Parameter Store / Secrets Manager | Config outside code (R13) |

## Domain Model

```
Company 1───* Plant 1───* ProductLine 1───* WeekCell
                 │                              │
                 │                              *── Note
                 │
Plant 1───* WorkforceTarget (by week/period)
ProductLine *───* Platform (overlap: A1, Alpha 1, NC5)   // regional aggregation
ProductLine 1───* LineLink (combined-process relationship)
CadenceOption (approved rate/worker combos, technical dept)  // master data
PlanVersion 1───* WeekCellSnapshot   // official + named versions + history
Scenario 1───* WeekCellSnapshot      // hypotheses, promotable to official
User *───* Role ; Role *───* Permission ; RoleScope -> Plant/Region
ConfigEntry / RuleDefinition          // config-over-code layer
```

### Key entities

- **Plant** — name, country, `frozenWeeks` config, region membership (EMEA).
- **ProductLine** — product/project name, product family, production-scheduler info (routings + SAP work centers, display-only), plant, platform links, line-link relationships.
- **CadenceOption** — approved `{ workers, shifts, ratePerConfig }` combinations supplied by the technical department; the source of truth for theoretical output (R2.1, R2.2). Imported as master data (R11).
- **WeekCell** — `(productLineId, isoYearWeek)` with `workingDays`, `cadenceOptionId`, `workersAssigned`, `expectedPieces` (derived), `capacityDelta`, `actualOutput` (derived), `frozen` (derived from plant + week).
- **WorkforceTarget** — target staffing per plant/period; drives above/below-target indicator (R3).
- **Note** — attached to a WeekCell or planning area, with author/time; drives cell highlighting (R9).
- **PlanVersion** — official releases and named saves with plant, timestamp, explanation; contains immutable `WeekCellSnapshot`s for diffing and history (R7).
- **Scenario** — hypothesis branch of week cells, comparable to official, promotable (R5).
- **LineLink** — declares two lines as one combined process so a cadence change on one adjusts the other (R4).
- **User / Role / Permission / RoleScope** — RBAC with plant/region scoping (R12).
- **ConfigEntry / RuleDefinition** — configuration-driven lines, master data, special rules, KPIs (R13, R15).

## Business Rules Engine

A dedicated backend module (`domain/rules`) computes derived values and enforces constraints. It runs on every cell edit and on scenario/version operations.

1. **Theoretical output (R2.1, R2.4):** `expectedPieces = f(cadenceOption, workersAssigned, workingDays)`. Examples encoded via CadenceOption: 1-worker → 60; "11 + 11" (two shifts × 11) → 144. `actualOutput = expectedPieces + capacityDelta`.
2. **Approved combinations only (R2.2):** a WeekCell must reference a valid `CadenceOption`; arbitrary staffing values are rejected with a validation error.
3. **Capacity adjustment (R2.3):** `capacityDelta` records delay/ahead/extra-capacity and overrides the theoretical value in `actualOutput`.
4. **Workforce target (R3):** aggregate `workersAssigned` per plant/period vs. `WorkforceTarget`; expose `above | at | below` and the numeric delta.
5. **Combined/linked lines (R4):** when a `LineLink` exists, a cadence change on the primary line triggers a transactional adjustment to the linked line's output; applied consistently across affected weeks.
6. **Frozen period (R1.5, R6.3, R6.4):** a week is frozen if it falls within the plant's `frozenWeeks` window from the current week; edits are blocked. The first non-frozen week must be finalized by Friday of the current week.
7. **Regional aggregation (R8.2):** for lines sharing a Platform (A1, Alpha 1, NC5), compute total potential output across plants rather than per-facility.
8. **Special rules (R4.2, R13.2):** additional `RuleDefinition`s are evaluated by the engine so nonstandard cases are configuration, not code.

> Per the meeting, ~90% is already prototyped; the combined-line rule and other nonstandard cases are the main remaining domain logic.

## Versioning, Scenarios, and History

- **Official version (R6.1):** central planning releases a `PlanVersion` flagged official; it becomes the shared agreement and the baseline for diffs.
- **Named versions (R7.1):** any save stores plant, time, and explanation.
- **Diff to last official (R7.2):** cell-level comparison highlighting changed values.
- **Applied vs. hypothesis (R7.3, R5.2):** each change is tagged `applied-in-compass` or `proposal`, so exported/applied changes are distinguishable from open ideas.
- **History (R7.4):** closed/hidden weeks can be revealed read-only for review.
- **Official summary area (R7.5):** a read-only surface listing saved official versions without exposing main-grid editing.
- **Change cadence (R6.2):** the official balance changes on the weekly meeting cadence, not continuously; scenarios absorb interim exploration.

## Integrations

- **Compass export (R10.2, R10.3):** generate an `.xlsx` of approved cadence updates in Compass's import format, replacing week-by-week manual copying. One-way; Compass still owns planned-order creation and the SAP export.
- **Click Sense / Qlik Sense (R10.1):** publish structured tables (flat, analysis-friendly) via a reporting endpoint or a materialized dataset in S3.
- **Master-data import (R11):** upload an Excel file with pieces, time values, and line data; validate and upsert `CadenceOption` and line master data without code changes; reject invalid files without corrupting existing data.

## API Surface (representative)

| Method | Path | Auth/Role | Purpose | Requirement |
|---|---|---|---|---|
| GET | `/plants` | viewer+ | List plants and frozen-week config | R1, R6 |
| GET | `/plants/{id}/grid?weeks=` | viewer+ | Grid data (lines × weeks) | R1, R8 |
| PUT | `/cells/{lineId}/{week}` | planner (edit) | Edit cell; runs rules engine | R1, R2, R3, R4 |
| GET | `/regional/grid?platform=` | viewer+ | Cross-plant aggregation | R8 |
| POST | `/scenarios` | planner | Create scenario | R5 |
| POST | `/scenarios/{id}/promote` | central | Promote scenario | R5.3 |
| POST | `/versions` | planner | Save named version | R7.1 |
| POST | `/versions/{id}/release` | central | Release official version | R6.1 |
| GET | `/versions/diff?base=&target=` | viewer+ | Diff vs. official | R7.2 |
| GET | `/versions/official` | viewer+ | Read-only official summary | R7.5 |
| POST | `/notes` | planner | Add note to cell/area | R9 |
| POST | `/imports/master-data` | admin | Import Excel master data | R11 |
| GET | `/exports/compass` | planner | Compass xlsx export | R10.2 |
| GET | `/reports/clicksense` | viewer+ | Click Sense tables | R10.1 |
| GET/PUT | `/config/*` | admin | Config-over-code layer | R13, R15 |
| GET | `/health` | none | Health check | — |

All endpoints validate payloads with Pydantic and are documented via auto-generated OpenAPI.

## Access Control and Governance (R12)

- **Roles:** `central-admin` (full maintenance + config), `planner` (edit within scope), `viewer` (official + history read-only), `plant-viewer` (official/history for own plant, no main-grid edit).
- **Scoping:** roles are scoped to a plant or region; the backend enforces scope on every request (not just the UI).
- **One central dataset (R12.3):** all data lives in RDS; no laptop-local files. Cognito identities map to app roles.
- **Least privilege (infra):** the backend's IAM role is scoped to its RDS, S3 prefixes, and SSM parameters only.

## Configuration over Code (R13, R15)

- A `config`/`rules` layer (DB-backed, admin API + guarded UI) lets authorized users add/switch/remove production lines, maintain master data, define special rules, and add dashboard fields/KPIs.
- `RuleDefinition` entries feed the rules engine so most nonstandard cases are data, not deployments.
- New plants/lines/companies and hypothetical test facilities are added through config without affecting official data (R15.1–R15.3).
- Ordinary business changes require no source-code access.

## Internationalization (R14)

- `react-i18next` with resource bundles: `en` (company language), `it` (essential), `fr` and `tr` (desirable, feature-flagged).
- Backend validation/error messages carry stable codes; the frontend localizes them, so adding a language is a resource-bundle change.

## Error Handling

- Global FastAPI handler returns `{ "error": { "code", "message", "correlationId" } }`.
- Validation (invalid cadence combo, frozen-week edit, cross-scope access) → 400/403 with actionable detail.
- Auth failures → 401; scope violations → 403.
- Unexpected errors → 500, logged with correlation id, no internal leakage.

## Observability

- Structured JSON logs to CloudWatch with per-request correlation id.
- Metrics for edit throughput, rule-engine evaluations, export/import outcomes.
- `/health` for uptime checks; optional X-Ray tracing.

## Testing Strategy

- **Rules engine (highest priority):** unit tests for theoretical output (60; 144 for "11+11"), approved-combo enforcement, capacity delta, workforce target above/below, combined-line adjustment, frozen-week blocking, regional aggregation.
- **Backend:** Pytest + FastAPI TestClient; Postgres test container (or SQLite for fast unit runs where compatible); RBAC scope tests.
- **Frontend:** Vitest + React Testing Library; grid editing, note highlighting, version diff view, i18n switching; MSW to mock the API.
- **Import/export:** round-trip tests for master-data import validation and Compass export format; Click Sense table shape tests.
- **Integration:** staging deploy with real Cognito/RDS/S3; smoke tests covering release → scenario → promote → export.

## Migration and Rollout

- The spreadsheet remains the productive tool until the platform is ready; no competing parallel launch.
- Seed the platform from the existing spreadsheet via the master-data import path and a one-time historical-version load where available.
- Pilot with hypothetical new facilities/lines to validate configurability before production.
- Introduce the platform only after sufficient development, testing, and review; iterate collaboratively with the business team.
