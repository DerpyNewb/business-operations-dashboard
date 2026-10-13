# Business Operations Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task by task; use superpowers:requesting-code-review for independent review.

**Goal:** Consolidate staff CSV updates into a working dashboard with assigned maintenance tasks, reminders, source health, and safe conflict recovery.

**Architecture:** Standard-library Python/SQLite engine, loopback authenticated HTTP API, and buildless frontend. CSV sources update independently and atomically using optimistic record versions. Local notification logs demonstrate automation without external accounts.

**Tech Stack:** Python 3.11+, sqlite3, csv, decimal, http.server; native HTML/CSS/JavaScript; optional n8n orchestration.

**Spec:** `docs/superpowers/specs/2026-10-13-operations-design.md`

## Global constraints

- Fictional sample data only; runtime databases, private inputs, and tokens ignored.
- Entire-source validation before writes; retain last valid data on failed refresh.
- Version 1 for new IDs; exact next revision for changes; identical revisions are no-ops.
- Money stored and summed as integer centavos.
- Asia/Manila dates for reminders/summaries; local log only.
- No public server, account calls, GitHub publication, or hosted deployment in this build.

## Task 1: CSV engine and task behavior

**Files:** `engine.py`, `test_engine.py`, `samples/*.csv`, `templates/*.csv`, `.gitignore`.
**Interfaces:** `Engine(db_path, clock=None)`, `import_csv(kind,csv_text)`, `refresh(folder)`, `create_request(payload)`, `run_automations()`, `snapshot()`.

- [x] Write and run failing tests on temporary SQLite databases for accepted rows, repeat no-op imports, invalid rows, duplicate IDs/headers, version conflicts, missing files, retained last valid records, exact financial totals, and derived task updates.
- [x] Implement bounded CSV parsing, typed validation, all-or-nothing transactions, source health, and version checks; run tests green.
- [x] Write failing intake/reminder tests: defaults and urgency, repeat intake, conflict protection, overdue tasks, completed suppression, Manila day rollover, and one daily summary per day.
- [x] Implement intake and durable local notifications; run engine tests green.

Representative behavior:

```python
result = engine.import_csv('maintenance', csv_text)
assert result['status'] == 'accepted'
assert engine.snapshot()['tasks'][0]['owner'] == 'Maintenance team'
assert engine.import_csv('maintenance', csv_text)['changed'] == 0
```

## Task 2: API and n8n entry points

**Files:** `app.py`, `test_app.py`, `n8n-maintenance.json`, `n8n-refresh.json`, `.env.example`.
**Interfaces:** documented `/api` routes; `make_server(engine,token,folder,port=0)`; `python app.py serve --files <folder> --db <path> --port 8766`.

- [x] Before code, test auth, host/origin checks, route/body allowlists, oversized/malformed JSON, fixed static routes, configured-folder refresh, and failed-source responses using real local HTTP.
- [x] Adapt the prior project's safe loopback patterns into this standalone repository; no imports from sibling projects. Static assets are publicly served but every data/mutation API route requires a token.
- [x] Confirm n8n parameters through official documentation; create inactive credential-free intake and scheduled refresh/automation workflows with stable IDs. Execute forwarding expressions against fixtures and check graph contracts.
- [x] Run API and workflow checks green.

## Task 3: Functional dashboard

**Files:** `static/index.html`, `static/app.js`, `static/style.css`, `DESIGN.md`.
**Consumes:** exact snapshot and API payload contracts in the spec.

- [x] Document visual tokens and layout purpose before implementation.
- [x] Implement connect/disconnect, real CSV refresh/upload, maintenance intake, automation action, filter controls, tables, source health, notifications, and meaningful states. Use textContent for untrusted data, memory-only token, native controls, and no dependencies.
- [x] Run against the API and verify each control, empty/error/success/loading states, keyboard focus, narrow layout, and HTML injection handling. Capture screenshots.

## Task 4: Demo, docs, review, and evidence

**Files:** `demo.py`, `README.md`, `SETUP.md`, `SOP.md`, `HANDOFF.md`, `.github/workflows/checks.yml`, `docs/VERIFICATION.md`.

- [x] Run an asserted offline demo importing three sources, creating a request, accepting a revised staff record, replaying reminders, rejecting a conflicting/invalid refresh, and preserving the last valid data.
- [x] Write exact templates/field instructions and conflict-resolution SOP. Document local reminders, shared-token identity limits, all-period financial totals, and unverified n8n runtime/deployment.
- [x] Obtain independent correctness review; reproduce and fix consequential findings with regression tests.
- [x] Run the complete tests and demo, record browser/contrast evidence, check Git exclusions, and commit locally on `feature/operations-dashboard`.

## Execution decisions

The user already authorized the same build sequence and selected CSV. Continue in this session. New standalone project directory provides isolation; initialize its own Git repository without a remote. Use independent scoped work for frontend and API under the applicable Superpowers delegation/review skills.
