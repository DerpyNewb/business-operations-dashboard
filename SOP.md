# Colleague Operating Procedure

**Operator:** The colleague assigned to a department's data. **Escalation owner:** The business's designated operations administrator. Assign actual people before operating with real data.

## 1. Prepare your source

Start from the matching template. Keep each `record_id` stable. For new records use version 1; for edits first check the current accepted version, then increment by one. Fill `updated_at` with the actual edit time and timezone, and `updated_by` with your name or team label. These labels are not verified user identities.

Maintain complete record values rather than leaving unchanged cells blank. Use valid statuses/stages and plain decimal PHP amounts. Export UTF-8 CSV without renamed headers or duplicate IDs. Save private files in the configured data folder, not `samples/`.

## 2. Refresh or upload

Connect to the local dashboard with the administrator's shared token. Choose **Refresh configured CSV files** for the three configured files, or choose a department, select one CSV, and choose **Import selected CSV**.

Read the action result and source health. `accepted` means validation succeeded; `rejected` retains the last accepted records. A partial refresh may update other departments. Inspect **Import failure history** for the rejected field, row, or record ID. Do not assume all sources succeeded because the page loaded.

Uploads update the database, not the source file. Bring the canonical departmental file to the same accepted version before the next folder refresh.

## 3. Resolve conflicts

If a record version conflicts, compare the current dashboard record to your intended edit. Keep the accepted values unless you have a deliberate correction. Resubmit the merged record using exactly the next stored version and a current timestamp. Do not merely change the version on an old whole-file export; it can overwrite newer information you did not review.

A stale, skipped, or conflicting revision rejects its whole department source. Previously accepted data stays visible. Fix all conflicts in that file and import again. Missing rows do not delete data: close maintenance with `completed`/`cancelled`, close leasing with `leased`/`lost`, and void a financial record using `void` at its next revision.

## 4. Capture maintenance work

Use a new request ID, property, description, priority, due date in Manila time, and reporter label. Leave owner blank to assign `Duty manager` for an urgent request or `Maintenance team` for a normal one. Choose **Create assigned request** and verify it in the queue.

Urgent requests visibly require review; this flag does not prove someone reviewed them. The assigned colleague follows the business's actual escalation procedure. Update status, owner, or due date through a versioned maintenance CSV. Repeating the same intake ID does not create a second task; different details under an existing ID require a versioned edit.

## 5. Review reminders and summaries

Choose **Record reminders and daily summary**, or use the configured n8n schedule. Inspect the **Local notification log**. Nothing is sent externally. The operator acts on overdue tasks and uses the business's approved communication channel manually.

Runs reuse one reminder per task, owner, and Manila day and one summary per day. Summaries retain their original count snapshot; changes later that day do not rewrite them. Reminder history remains after a task closes. A reassigned owner can get a new reminder the same day.

## 6. Interpret health and totals

Source freshness is based on the last accepted import, not proof that its records were recently reviewed. Stale or rejected sources can still contribute their last valid data. Always inspect source health before relying on totals.

Financial totals include posted records across all supplied periods; they are a demonstration of aggregation, not a reconciliation with a bank or accounting system. Void rows remain visible but are excluded from totals.

## 7. Recovery and privacy

Correct malformed exports and rerun refresh. For unreadable files, check the configured folder, filenames, encoding, and operator permissions. For auth problems, ask the administrator for the intended local token. Do not disable authentication or expose the server publicly.

Back up the private SQLite database before upgrading or relocating it. Never delete the database to bypass a conflict: that also removes revision checks, source history, and notification receipts. Publish fictional fixtures and sanitized recordings only; do not commit business data or tokens.
