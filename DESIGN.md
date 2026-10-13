# Operations dashboard visual direction

Local reference for a fictional property-management team. ENERGY 1 / RHYTHM 2 / MOTION 1. The maintenance queue is the focal working surface; departmental ledgers and source health support it.

Palette: cool paper `#f2f5f8`, white work surface `#ffffff`, dark slate text `#243447`, secondary slate `#526477`, blue action `#245782`, urgent/error red `#a32632`. Pale red `#fff1f2` marks requests requiring review. Borders `#c5ced8` separate records. Red always accompanies a written status.

Use the installed Segoe UI/system sans-serif stack for familiar, readable staff controls, tabular numerals for money, and an unembellished heading. No fonts, images, icons, gradients, shadows, or remote assets. Small control corners separate editable controls from square ledger surfaces.

Layout: left-aligned header and connection strip; compact operational count ribbon; large maintenance ledger; maintenance intake and source import forms beside each other when they fit; leasing and financial ledgers; source health and local notification log. Section anchors provide direct navigation. Narrow layouts stack forms, wrap navigation, and contain tables in labeled horizontal scroll regions. Spacing separates working areas, while tight row rhythm enables scanning.

Controls have 44px minimum targets, visible focus, native labels, inline live status, disabled/loading states, and actionable empty states. No private data is included in the static shell. User text enters through textContent. Token and state remain in memory and clear on disconnect. Financial totals explicitly cover posted records across all imported periods.

Verification evidence is recorded by the coordinating agent in docs/VERIFICATION.md after API and browser checks.
