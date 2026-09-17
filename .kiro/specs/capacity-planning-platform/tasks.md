# Implementation Plan

Tasks are incremental and ordered so each builds on the previous. The rules engine and data model are prioritized because they carry the existing business logic. Each task references the requirements it satisfies.

- [ ] 1. Initialize the repository and project scaffolding
  - Create a monorepo: `frontend/`, `backend/`, `infra/`, `docs/`.
  - Add root README, `.gitignore`, editorconfig, linters/formatters (ESLint/Prettier, Ruff/Black), and pre-commit hooks.
  - _Requirements: R12, R13_

- [ ] 2. Define the data model and migrations
- [ ] 2.1 Model core planning entities
  - SQLAlchemy models: Company, Plant (with `frozenWeeks`), ProductLine, WeekCell, WorkforceTarget, Note.
  - Alembic initial migration.
  - _Requirements: R1, R2, R3, R6, R9_
- [ ] 2.2 Model master data, versions, scenarios, and links
  - CadenceOption, Platform + line↔platform link, LineLink (combined process), PlanVersion, WeekCellSnapshot, Scenario.
  - _Requirements: R2, R4, R5, R7, R8_
- [ ] 2.3 Model governance and configuration
  - User, Role, Permission, RoleScope (plant/region), ConfigEntry, RuleDefinition.
  - _Requirements: R12, R13, R15_

- [ ] 3. Implement the business rules engine (highest priority)
- [ ] 3.1 Theoretical output and capacity delta
  - `expectedPieces = f(cadenceOption, workers, workingDays)`; encode examples (1 worker → 60; "11 + 11" → 144); `actualOutput = expectedPieces + capacityDelta`.
  - _Requirements: R2.1, R2.3, R2.4_
- [ ] 3.2 Approved-combination enforcement
  - Reject cadence/worker values not present in CadenceOption master data.
  - _Requirements: R2.2_
- [ ] 3.3 Workforce target evaluation
  - Aggregate assigned workers per plant/period vs. target; return above/at/below and delta.
  - _Requirements: R3.1, R3.2, R3.3_
- [ ] 3.4 Combined/linked-line rule
  - When a LineLink exists, a cadence change on one line transactionally adjusts the related line across affected weeks.
  - _Requirements: R4.1, R4.3_
- [ ] 3.5 Frozen-period enforcement
  - Compute frozen weeks per plant; block edits; enforce Friday finalization of the first open week.
  - _Requirements: R1.5, R6.3, R6.4_
- [ ] 3.6 Regional aggregation and configurable special rules
  - Total potential output across plants sharing a platform; evaluate RuleDefinition entries for nonstandard cases.
  - _Requirements: R4.2, R8.2, R13.2_
- [ ] 3.7 Unit tests for the rules engine
  - Cover 3.1–3.6 including edge cases (frozen boundaries, linked-line cascades, above/below target).
  - _Requirements: R2, R3, R4, R6, R8_

- [ ] 4. Backend API foundation
- [ ] 4.1 FastAPI app skeleton
  - App bootstrap, config from env/SSM, structured logging + correlation id, global error handler, `/health`.
  - _Requirements: R12, R5 (reliability)_
- [ ] 4.2 Pydantic schemas and validation
  - Request/response schemas for cells, grids, versions, scenarios, notes, imports, exports, config.
  - _Requirements: R1, R2, R5, R7_

- [ ] 5. Authentication, authorization, and governance
- [ ] 5.1 Cognito JWT verification
  - Verify tokens against Cognito JWKS; extract user identity.
  - _Requirements: R12.1, R12.2_
- [ ] 5.2 Role- and scope-based authorization
  - Enforce roles (central-admin, planner, viewer, plant-viewer) and plant/region scope on every endpoint.
  - _Requirements: R12.1, R12.2, R12.4, R12.5_
- [ ] 5.3 Single central dataset guarantees
  - All reads/writes go through RDS; no local-file paths; audit who changed what.
  - _Requirements: R12.3_

- [ ] 6. Grid and cell-editing endpoints
  - `GET /plants`, `GET /plants/{id}/grid`, `PUT /cells/{lineId}/{week}` invoking the rules engine.
  - Return derived values, target status, frozen flags, and note indicators.
  - _Requirements: R1, R2, R3, R4, R9_

- [ ] 7. Regional and multi-plant views
  - `GET /regional/grid?platform=` aggregating overlapping products; support single/multi/region combinations.
  - Record intended cross-plant transfers flagged "sales to be consulted / agreement required".
  - _Requirements: R8.1, R8.2, R8.3_

- [ ] 8. Scenarios, versions, and history
- [ ] 8.1 Scenario management
  - Create scenarios without copying official data; tag as proposal vs. applied; promote to official.
  - _Requirements: R5.1, R5.2, R5.3, R7.3_
- [ ] 8.2 Version control
  - Save named versions (plant/time/explanation); release official version; diff vs. last official.
  - _Requirements: R6.1, R6.2, R7.1, R7.2_
- [ ] 8.3 History and official summary
  - Reveal closed/hidden weeks read-only; read-only official-versions summary area.
  - _Requirements: R7.4, R7.5_

- [ ] 9. Planning notes
  - `POST /notes` on cells/areas; return note presence for grid highlighting and note context on open.
  - _Requirements: R9.1, R9.2, R9.3_

- [ ] 10. Master-data import
  - Excel import of pieces, time values, and line data into CadenceOption/line master data.
  - Validate and reject bad files without corrupting existing data; allow re-import without code changes.
  - _Requirements: R11.1, R11.2, R11.3_

- [ ] 11. Reporting and export
- [ ] 11.1 Compass export
  - Generate `.xlsx` of approved cadence updates in Compass import format (no manual week-by-week copying).
  - _Requirements: R10.2, R10.3_
- [ ] 11.2 Click Sense reporting tables
  - Produce structured/flat tables for Qlik Sense analysis via endpoint or S3 dataset.
  - _Requirements: R10.1_

- [ ] 12. Configuration-over-code layer
  - Admin APIs to add/switch/remove lines, maintain master data, define special rules, add dashboard fields/KPIs.
  - Add hypothetical plants/lines for testing without affecting official data.
  - _Requirements: R13.1, R13.2, R13.3, R13.4, R15.1, R15.2, R15.3_

- [ ] 13. Backend integration tests
  - Postgres test container; cover RBAC scope, frozen-period blocking, linked-line cascades, scenario promotion, import/export round-trips.
  - _Requirements: R2, R3, R4, R5, R6, R7, R10, R11, R12_

- [ ] 14. Frontend scaffolding
  - Vite + React + TS; React Router; Axios + TanStack Query; API client with token injection and 401 handling.
  - react-i18next with `en`, `it` bundles (fr/tr feature-flagged).
  - _Requirements: R1, R14_

- [ ] 15. Spreadsheet-like planning grid UI
  - AG Grid (or TanStack Table + virtualization): lines as rows, weeks as columns; editable cells; note highlighting; frozen-week styling; target above/below indicator.
  - _Requirements: R1.1, R1.2, R1.3, R1.4, R1.5, R2, R3, R9_

- [ ] 16. Views, scenarios, versions, and history UI
  - Plant/multi-plant/regional view switcher; scenario create/promote; version save/release; diff-to-official view; history and official-summary panels.
  - _Requirements: R5, R6, R7, R8_

- [ ] 17. Notes, import, export, and config UI
  - Note editor with highlight indicators; master-data import upload with validation feedback; Compass export and Click Sense report triggers; guarded config/admin screens.
  - _Requirements: R9, R10, R11, R13, R15_

- [ ] 18. Frontend tests
  - Vitest + RTL + MSW: grid editing, frozen-week block, note highlight, version diff, language switching, config screens.
  - _Requirements: R1, R7, R9, R13, R14_

- [ ] 19. Infrastructure as code (AWS CDK)
- [ ] 19.1 Identity and data stacks
  - Cognito user pool/client + app roles; RDS PostgreSQL (+ RDS Proxy); S3 buckets (imports, notes, export artifacts) with public access blocked.
  - _Requirements: R12, R11, R10_
- [ ] 19.2 Compute and API stack
  - ECS Fargate + ALB (or Lambda + API Gateway) running FastAPI; least-privilege IAM; config/secrets via SSM/Secrets Manager; CORS to the frontend origin.
  - _Requirements: R12.3, R13, R5_
- [ ] 19.3 Frontend delivery stack
  - S3 site bucket + CloudFront (HTTPS/OAC); `/api/*` routed to the backend.
  - _Requirements: R12, R5_

- [ ] 20. CI/CD and staging
  - Pipeline: lint, test, build frontend, package backend, run migrations, deploy; staging environment with smoke tests.
  - _Requirements: R12, R15_

- [ ] 21. Data seeding and pilot
  - Seed from the existing spreadsheet via master-data import and a one-time historical-version load where available.
  - Pilot with hypothetical new facilities/lines; validate configurability; gather business feedback before production.
  - _Requirements: R11, R15_

- [ ] 22. End-to-end verification
  - E2E covering release official → create scenario → promote → edit within/against frozen period → linked-line adjustment → Compass export → Click Sense tables.
  - Verify RBAC scopes, single-dataset consistency, HTTPS, and i18n in the deployed environment.
  - _Requirements: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R14_
