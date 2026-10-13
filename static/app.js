"use strict";

const $ = (id) => document.getElementById(id);
let token = "";
let snapshot = null;
let busy = false;
let generation = 0;
let controller = null;
const pesos = new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" });
const dates = new Intl.DateTimeFormat("en-PH", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Manila" });
const money = (cents) => pesos.format(Number(cents || 0) / 100);
const date = (value) => value && Number.isFinite(Date.parse(value)) ? dates.format(new Date(value)) : "Never";
const words = (value) => String(value || "").replaceAll("_", " ");

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = String(text);
  if (className) element.className = className;
  return element;
}

function message(text, error = false) {
  $("action-status").textContent = text;
  $("action-status").classList.toggle("error", error);
}

function controls() {
  const ready = Boolean(token && snapshot && !busy);
  for (const id of ["request-fields", "import-fields", "refresh-button", "automations-button", "search", "status-filter", "owner-filter"]) $(id).disabled = !ready;
  $("connect-button").disabled = busy || Boolean(token);
  $("token").disabled = Boolean(token) || busy;
  $("disconnect-button").disabled = !token;
  $("action-status").setAttribute("aria-busy", String(busy));
}

async function api(path, payload) {
  const response = await fetch(path, {
    method: payload === undefined ? "GET" : "POST",
    headers: { Authorization: `Bearer ${token}`, ...(payload === undefined ? {} : { "Content-Type": "application/json" }) },
    ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
    signal: controller.signal,
    cache: "no-store"
  });
  let result;
  try { result = await response.json(); }
  catch { throw new Error(`Server returned an unreadable response (${response.status}).`); }
  if (!response.ok) throw new Error(typeof result.error === "string" ? result.error : `Request failed (${response.status}).`);
  return result;
}

function cell(row, text, secondary) {
  const td = node("td");
  td.append(node("strong", text));
  if (secondary) td.append(node("small", secondary));
  row.append(td);
  return td;
}

function renderQueue() {
  const tasks = snapshot?.tasks || [];
  const search = $("search").value.trim().toLowerCase();
  const status = $("status-filter").value;
  const owner = $("owner-filter").value;
  const filtered = tasks.filter((task) => (!status || task.status === status) && (!owner || task.owner === owner) && (!search || [task.summary, task.property, task.record_id].some((value) => String(value || "").toLowerCase().includes(search))));
  $("maintenance-rows").replaceChildren();
  for (const task of filtered) {
    const row = node("tr", undefined, task.urgent_review ? "urgent-row" : "");
    cell(row, task.summary, `${task.record_id} · ${task.property}`);
    const priority = cell(row, words(task.priority), task.urgent_review ? "Urgent review required" : ["completed", "cancelled"].includes(task.status) ? "Closed request" : "Standard assignment");
    if (task.urgent_review) priority.classList.add("urgent-label");
    cell(row, words(task.status));
    cell(row, task.owner);
    const due = cell(row, date(task.due_at), task.overdue ? "Overdue" : "");
    if (task.overdue) due.classList.add("urgent-label");
    cell(row, date(task.updated_at), `Version ${task.version} · ${task.updated_by}`);
    $("maintenance-rows").append(row);
  }
  $("queue-count").textContent = `${filtered.length} of ${tasks.length} tasks`;
  $("maintenance-empty").hidden = filtered.length > 0;
  $("maintenance-empty").textContent = !snapshot ? "Connect to view assigned maintenance work." : tasks.length ? "No tasks match these filters. Change the search, status or owner." : "No maintenance tasks yet. Import a maintenance CSV or record a request below.";
}

function render() {
  const metrics = snapshot?.metrics || {};
  $("snapshot-time").textContent = snapshot ? `Updated ${date(snapshot.generated_at)} · Manila time` : "Disconnected";
  $("metrics").replaceChildren();
  if (snapshot) {
    for (const [key, label, urgent] of [["open_requests", "Open requests", false], ["urgent_requests", "Urgent requests", true], ["overdue_tasks", "Overdue tasks", true], ["active_leasing", "Active leasing records", false]]) {
      const item = node("div", undefined, `metric${urgent && metrics[key] ? " urgent" : ""}`);
      item.append(node("strong", metrics[key] || 0), node("span", label));
      $("metrics").append(item);
    }
  }
  const previousOwner = $("owner-filter").value;
  $("owner-filter").replaceChildren(node("option", "All owners"));
  $("owner-filter").firstElementChild.value = "";
  for (const owner of [...new Set((snapshot?.tasks || []).map((task) => task.owner))].sort()) {
    const option = node("option", owner);
    option.value = owner;
    $("owner-filter").append(option);
  }
  $("owner-filter").value = previousOwner;
  if (!$("owner-filter").value) $("owner-filter").value = "";
  renderQueue();
  $("leasing-rows").replaceChildren();
  for (const record of snapshot?.leasing || []) {
    const row = node("tr");
    cell(row, record.record_id, record.property);
    cell(row, record.applicant);
    cell(row, words(record.stage));
    cell(row, money(record.monthly_rent_cents));
    cell(row, record.owner);
    cell(row, date(record.updated_at), `Version ${record.version} · ${record.updated_by}`);
    $("leasing-rows").append(row);
  }
  $("leasing-empty").hidden = Boolean(snapshot?.leasing?.length);
  $("leasing-empty").textContent = snapshot ? "No leasing records yet. Import a leasing CSV above." : "Connect to view leasing records.";
  $("finance-totals").replaceChildren();
  if (snapshot) for (const [key, label] of [["income_cents", "Posted income, all periods"], ["expense_cents", "Posted expenses, all periods"], ["net_cents", "Net, all periods"]]) {
    const item = node("div");
    item.append(node("span", label), node("strong", money(metrics[key])));
    $("finance-totals").append(item);
  }
  $("finance-rows").replaceChildren();
  let previousPeriod;
  for (const record of [...(snapshot?.finance || [])].sort((a, b) => String(b.period).localeCompare(String(a.period)) || String(a.record_id).localeCompare(String(b.record_id)))) {
    const row = node("tr", undefined, previousPeriod !== record.period ? "period-start" : "");
    cell(row, record.period);
    cell(row, record.record_id, record.property);
    cell(row, words(record.category));
    cell(row, money(record.amount_cents));
    cell(row, words(record.status));
    cell(row, date(record.updated_at), `Version ${record.version} · ${record.updated_by}`);
    $("finance-rows").append(row);
    previousPeriod = record.period;
  }
  $("finance-empty").hidden = Boolean(snapshot?.finance?.length);
  $("finance-empty").textContent = snapshot ? "No finance records yet. Import a finance CSV above." : "Connect to view financial records.";
  $("sources").replaceChildren();
  for (const source of snapshot?.sources || []) {
    const rejected = ["rejected", "failed", "error"].includes(source.status);
    const item = node("article", undefined, `source${rejected || source.stale ? " bad" : ""}`);
    item.append(node("h3", words(source.kind)), node("p", `${words(source.status)} · ${source.record_count} stored records`));
    item.append(node("p", source.stale ? "Stale: accepted import older than 24 hours or missing." : "Fresh: accepted import within 24 hours.", source.stale ? "issue" : ""));
    item.append(node("p", `Last accepted: ${date(source.last_success_at)}`), node("p", `Last attempt: ${date(source.last_attempt_at)}`));
    if (source.error) item.append(node("p", `Rejected update: ${source.error}`, "issue"));
    $("sources").append(item);
  }
  if (!snapshot) $("sources").append(node("p", "Connect to inspect source freshness and rejected updates.", "empty"));
  $("failures").replaceChildren();
  for (const failure of snapshot?.failures || []) $("failures").append(node("li", `${words(failure.kind || failure.source_kind)} · ${date(failure.attempted_at || failure.created_at || failure.attempt_at)}: ${failure.error}`));
  if (!snapshot?.failures?.length) $("failures").append(node("li", snapshot ? "No import failures recorded." : "No operating data loaded."));
  $("notification-list").replaceChildren();
  for (const notification of snapshot?.notifications || []) {
    const item = node("li");
    item.append(node("p", notification.message), node("small", `${words(notification.kind)} · ${date(notification.created_at)} · ${notification.owner || "Operations"}${notification.record_id ? ` · ${notification.record_id}` : ""} · recorded locally`));
    $("notification-list").append(item);
  }
  $("notifications-empty").hidden = Boolean(snapshot?.notifications?.length);
  $("notifications-empty").textContent = snapshot ? "No notifications recorded. Run reminders and the daily summary above." : "Connect to view recorded notifications.";
  controls();
}

function disconnect() {
  generation += 1;
  controller?.abort();
  controller = null;
  token = "";
  snapshot = null;
  busy = false;
  $("token").value = "";
  $("search").value = "";
  $("status-filter").value = "";
  $("request-form").reset();
  $("import-form").reset();
  $("failure-details").open = false;
  $("connection-status").textContent = "Disconnected. Token and displayed operating data cleared.";
  $("connection-status").classList.remove("error");
  message("No operating data loaded.");
  render();
}

$("connect-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy || token) return;
  token = $("token").value;
  $("token").value = "";
  busy = true;
  controller = new AbortController();
  const current = ++generation;
  controls();
  $("connection-status").textContent = "Connecting to local API…";
  $("connection-status").classList.remove("error");
  message("Loading operating data…");
  try {
    const state = await api("/api/state");
    if (current !== generation) return;
    snapshot = state;
    $("connection-status").textContent = "Connected. The token is held only for this page session.";
    message("Operating data loaded.");
  } catch (error) {
    if (current !== generation) return;
    token = "";
    snapshot = null;
    $("connection-status").textContent = `Connection failed: ${error.message} Re-enter the token to retry.`;
    $("connection-status").classList.add("error");
    message("No operating data loaded.");
  } finally {
    if (current === generation) { busy = false; render(); }
  }
});

async function action(path, payload, loading, success) {
  if (!token || !snapshot || busy) return false;
  const current = generation;
  busy = true;
  controls();
  message(loading);
  let failure = null;
  let result = null;
  try { result = await api(path, payload); }
  catch (error) { failure = error; }
  if (current !== generation) return false;
  try {
    snapshot = await api("/api/state");
    if (current !== generation) return false;
    const rejected = path === "/api/import" ? snapshot.sources.find((source) => source.kind === payload.kind && source.error) : path === "/api/refresh" ? snapshot.sources.find((source) => source.error) : null;
    if (rejected && !failure) failure = new Error(`Update rejected for ${rejected.kind}: ${rejected.error} Last accepted data retained; inspect source health.`);
    if (result?.status === "rejected" && !failure) failure = new Error(result.error || "Update rejected. Inspect source health.");
    message(failure ? failure.message : success, Boolean(failure));
  } catch (error) {
    if (current !== generation) return false;
    failure = failure || error;
    message(`Could not reload state: ${error.message} Displayed data is the last loaded snapshot. Disconnect and reconnect to retry.`, true);
  } finally {
    if (current === generation) { busy = false; render(); }
  }
  return !failure;
}

$("disconnect-button").addEventListener("click", disconnect);
for (const id of ["search", "status-filter", "owner-filter"]) $(id).addEventListener(id === "search" ? "input" : "change", renderQueue);
$("refresh-button").addEventListener("click", () => action("/api/refresh", {}, "Refreshing configured CSV files…", "Configured source refresh finished. Source health shows each result."));
$("automations-button").addEventListener("click", () => action("/api/automations", {}, "Recording reminders and the daily summary…", "Automation run finished. Review the local log; repeated runs reuse today's recorded reminders and summary."));
$("import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("csv-file").files[0];
  if (!file || busy || !token) return;
  if (file.size > 512 * 1024) { message("CSV exceeds 512 KiB. Choose a smaller source export.", true); return; }
  const current = generation;
  try {
    const csv_text = await file.text();
    if (current !== generation) return;
    await action("/api/import", { kind: $("csv-kind").value, csv_text }, "Validating and importing selected CSV…", "CSV accepted. Assigned tasks and department ledgers are current.");
  } catch (error) { if (current === generation) message(`Could not read CSV: ${error.message}`, true); }
});
$("request-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const fields = new FormData(event.currentTarget);
  const payload = Object.fromEntries(fields.entries());
  payload.due_at += ":00+08:00";
  if (!payload.owner.trim()) delete payload.owner;
  if (await action("/api/maintenance", payload, "Creating assigned maintenance request…", "Maintenance request recorded with its assigned task.")) $("request-form").reset();
});

render();
