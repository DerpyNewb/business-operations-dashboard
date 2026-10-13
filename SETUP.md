# Setup

## Local demonstration

Python 3.11+; no pip installation. Node.js runs the workflow-expression tests but is not required to serve the dashboard.

```powershell
python -m unittest discover -v
python demo.py
$env:OPERATIONS_API_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
python app.py serve --files samples --db output/operations.sqlite --port 8766
```

Open `http://127.0.0.1:8766`. Paste the generated token into **Local API token** and connect. The app stores it only in page memory and clears it on disconnect or reload. Static files are public on loopback; all data and mutation API routes require the token. The server also validates Host and Origin. This standard-library server is intended for local verification, not public hosting.

The default server folder is `samples/`, database `output/operations.sqlite`, port 8766. `--files`, `--db`, and `--port` can be changed. No `.env` auto-loader is included; `.env.example` lists the environment key.

Local CLI commands use the database directly and do not need the API token:

```powershell
python app.py refresh --files samples --db output/operations.sqlite
python app.py automations --db output/operations.sqlite
python app.py state --db output/operations.sqlite
```

Check JSON source statuses after refresh; a completed command may report rejected or partial operational data. The offline demo uses a separate temporary database and fixed fictional reference time, so it does not modify server data.

## Colleague-maintained files

Create a private `data/` directory from the templates. The directory is Git-ignored. Populate these fixed filenames and export as UTF-8 CSV:

- `maintenance.csv`
- `leasing.csv`
- `finance.csv`

Run with `--files data`. Staff edit these files externally or upload a selected source through the browser. Uploads apply to SQLite only; they do not rewrite the configured file. Keep the canonical file updated after a successful upload or the next folder refresh may reveal a stale revision conflict.

Every source requires at least one record and the exact template headers, in any order. UTF-8 BOM is accepted. Limits: 512 KiB, 1,000 records per source, bounded fields, and exact enums. Text can be CSV-quoted, including commas. Do not use formulas as a substitute for values. Money accepts nonnegative plain decimals with at most two places and a per-record maximum of PHP 1,000,000,000.

New record versions start at 1. For a changed record, increment its current version by exactly one and supply a timezone-aware `updated_at` no earlier than its stored update time and no later than the current time. Use `updated_by` as the colleague's label. Example timestamp: `2026-10-13T10:00:00+08:00`. `due_at` may be past or future; the browser interprets its local date picker as Manila time.

## API

Use `Authorization: Bearer <OPERATIONS_API_TOKEN>` for every API request. POST bodies are JSON with a 1 MiB limit; CSV text itself has a 512 KiB limit.

| Route | Method | Body |
| --- | --- | --- |
| `/api/state` | GET | None |
| `/api/import` | POST | `kind` and `csv_text` |
| `/api/refresh` | POST | `{}`; uses configured folder only |
| `/api/maintenance` | POST | `record_id`, `property`, `summary`, `priority`, `due_at`, `reported_by`, optional `owner` |
| `/api/automations` | POST | `{}` |

Import/refresh return detailed operational results, including rejections. A JSON HTTP 200 is not proof that a source was accepted. Inspect `status` and the source results. Framing/auth errors and unsupported routes return HTTP errors.

## n8n

Import the two inactive exports. They assume n8n shares the engine's host network; container loopback is a different host. Bind Header Auth credentials after import, never in the committed JSON.

1. Outgoing HTTP nodes: credential name/value `Authorization: Bearer <OPERATIONS_API_TOKEN>`.
2. Maintenance webhook: inbound Header Auth credential `X-Workflow-Token: <separate shared secret>`.
3. Test maintenance intake with the same JSON contract as `/api/maintenance`.
4. The refresh workflow uses an hourly trigger at minute 05 with `Asia/Manila` workflow timezone. It refreshes configured files, rejects any partial/failed source result, then records reminders and a summary. Activate only when intentional.
5. Inspect source health/failure history after workflow errors. Correct invalid files before the next run. No external notification node is included.

Node parameters were checked against [official n8n documentation](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook/), [HTTP Request](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/), and [Schedule Trigger](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.scheduletrigger/). Actual runtime import/execution remains a separate verification step.
