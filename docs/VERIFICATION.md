# Verification Record

Recorded on 2026-10-13, Asia/Manila.

## Automated checks

- `python -W error::ResourceWarning -m unittest discover -v`: 25 tests passed against real SQLite and loopback HTTP. Node executed n8n forwarding/response and refresh-gate expressions.
- `python demo.py`: asserted source refresh, replay, assignment, staff revision, reminder deduplication, invalid/conflicting refresh retention, and recovery. Zero external messages sent. Evidence: ignored `output/demo-run.json`.
- `node --check static/app.js`: passed.

Independent review reproduced malformed CSV header parsing and UTC timestamp overflow that could abort sibling-source refreshes. Both now have regression tests and fixes. Maintenance revision metadata was added after final review.

## Real-browser checks

Playwright exercised the actual local API with fictional data at 1400x1000 and 390x844.

| Check | Observed result |
| --- | --- |
| Connection | Empty/rejected/loading/disconnected states work; disconnect clears token and records |
| Token storage | localStorage/sessionStorage empty; input clears after connection |
| Refresh | Three maintenance, three leasing, five finance records; sample net PHP 71,500 |
| Filters | Search, completed status, and Duty manager select appropriate records |
| CSV revision | MNT-001 version 2 changes task to completed; editor/version/update time visible |
| CSV rejection | Invalid status reports row/field; previous completed record retained |
| Intake | Urgent request assigned Duty manager when owner is blank |
| ID validation | Colon-containing ID rejected; hyphenated ID valid; corrected HTML Unicode-v pattern |
| Untrusted text | Image/onerror-like text rendered literally, without elements or execution |
| Reminders | Replay retains notification count 3 after a new overdue request |
| Navigation | Five anchors and failure disclosure function |
| Focus | Solid 3px focus outline; labeled native controls and focusable table regions |
| Mobile | Page/document width 390px; tables scroll within 320px containers; action buttons at least 44px high |
| Console | Zero errors/warnings after final reload; intentional auth rejection separately checked |

Screenshots show final UI and unchanged fictional samples under `docs/screenshots/`. Browser mutations remain in ignored databases.

## Visual and accessibility gate

Antislop contrast script results: slate text on white 12.67:1; secondary text on white 6.09:1; white on action blue 7.61:1; urgent red on pale red 6.64:1; secondary text on table background 5.37:1. All exceed 4.5:1 for normal text. Input boundary against white is 3.15:1, exceeding the non-text 3:1 criterion.

- **Hard gate PASS:** Functional controls and states, no page overflow at tested width, no fabricated customer/production claims or em-dash product filler.
- **Purpose gate PASS:** Colors serve action/urgency; system typography supports staff readability; forms/ledgers serve operations. No decorative assets or marketing template sections.
- **Liveliness PASS:** ENERGY 1 / RHYTHM 2 / MOTION 1 declared before implementation; maintenance focal, with spacing separating tasks.
- **Craftsmanship PASS:** Actual actions, recovery information, responsive layouts, native controls, and fictional screenshots verified.

This is practical verification, not comprehensive accessibility certification.

## Limits

n8n runtime import/scheduling, connected services, authenticated staff identities/roles, external notifications, accounting reconciliation, multi-worker production use, public deployment, and measured savings are unverified or outside scope.
