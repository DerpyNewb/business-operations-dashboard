# Operations Dashboard Handoff

Updated: 2026-10-13. Repository: `business-operations-dashboard`, branch `main`. GitHub target: `DerpyNewb/business-operations-dashboard`; publication requested by the user on 2026-10-13.

The user requested the same Superpowers brainstorm-plan-build method as lead-to-CRM and selected CSV. Design/plan are under `docs/superpowers/`.

Implemented: Python/SQLite atomic source validation and optimistic revisions, derived maintenance tasks, local reminders/summary, exact totals, leasing stages, source health/failures, authenticated loopback API, buildless dashboard, two inactive n8n exports, fictional samples/templates, asserted demo, setup guide, and SOP.

Verified: 25 tests, offline demo, JavaScript syntax, desktop/mobile browser actions, and computed contrast. Independent-review fixes are regression-tested. See `docs/VERIFICATION.md`.

Run `python demo.py` for offline proof. Set `OPERATIONS_API_TOKEN`, run `python app.py serve --files samples`, open loopback port 8766, and connect for UI. No pip dependencies. Fictional screenshots tracked under `docs/screenshots/`; operating data ignored.

Limits: freshness is last accepted import; notifications are local logs; posted totals span all periods. No deployment, staff roles, cloud files, accounting sync, AI, or external messages. n8n runtime unverified. Uploads do not rewrite CSV files; align versions before folder refresh. Do not drop the database to resolve conflicts.
