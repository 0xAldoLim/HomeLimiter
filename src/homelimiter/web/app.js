const $ = (s) => document.querySelector(s);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const nav = [
  ["overview", "overview", "Overview"],
  ["devices", "devices", "Connected devices"],
  ["bandwidth", "bandwidth", "Bandwidth"],
  ["access", "access", "Internet access"],
  ["scheduling", "scheduling", "Scheduling"],
  ["agents", "agents", "Enforcement agents"],
  ["diagnostics", "diagnostics", "Network diagnostics"],
  ["logs", "logs", "Audit logs"],
  ["settings", "settings", "Settings"],
];
const iconPaths = {
  overview: '<path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z"/>',
  devices:
    '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
  bandwidth: '<path d="M7 3v18m-4-4 4 4 4-4M17 21V3m-4 4 4-4 4 4"/>',
  access: '<circle cx="12" cy="12" r="9"/><path d="m5.5 5.5 13 13"/>',
  scheduling: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  agents:
    '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01"/>',
  diagnostics: '<path d="M2 12h4l3-7 5 14 3-7h5"/>',
  logs: '<path d="M8 5h13M8 12h13M8 19h13M3 5h.01M3 12h.01M3 19h.01"/>',
  settings:
    '<path d="M4 7h9m4 0h3M4 17h3m4 0h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  refresh:
    '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 6a8 8 0 0 1 13 2M18 18A8 8 0 0 1 5 16"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  shield:
    '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
};
function icon(key) {
  return `<svg class="icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[key] || iconPaths.devices}</svg>`;
}
let token = "",
  status,
  devices = [],
  policies = [],
  logs = [],
  routeVersion = 0;
let presets;
try {
  presets = JSON.parse(localStorage.getItem("hl-presets") || "[]");
  if (!Array.isArray(presets)) presets = [];
} catch {
  presets = [];
}
const date = (value) =>
  value
    ? new Date(value).toLocaleString([], {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "No expiry";
const name = (id) => devices.find((d) => d.id === id)?.nickname || id;
const badge = (text, type = "") =>
  `<span class="badge ${type}">${esc(text)}</span>`;
function notice(title, description, type = "") {
  return `<div class="notice ${type}">${icon("info")}<div><strong>${esc(title)}</strong><p>${esc(description)}</p></div></div>`;
}
function empty(title, description) {
  return `<div class="empty"><strong>${esc(title)}</strong><p>${esc(description)}</p></div>`;
}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => ($("#toast").hidden = true), 6000);
}
async function api(path, options = {}) {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      Authorization: "Bearer " + token,
      ...(options.method ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) {
    const message =
      typeof data.detail === "string"
        ? data.detail
        : "Check the form values and try again.";
    throw new Error(message);
  }
  return data;
}
const post = (path, data = {}) =>
  api(path, { method: "POST", body: JSON.stringify(data) });
function heading(title, subtitle, action = "") {
  return `<div class="page-heading"><div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="heading-actions">${action}</div></div>`;
}
function capsNotice() {
  const c = status.capabilities;
  return notice(
    c.simulated
      ? "You’re exploring a demo workspace"
      : c.mode === "MONITOR ONLY"
        ? "Observe first. Connect an agent when you’re ready."
        : "Your enforcement point is connected",
    c.reason,
    c.simulated ? "warn" : "",
  );
}
function controlsAllowed(device, kind = "bandwidth") {
  return (
    status.capabilities[kind] &&
    device?.confirmed &&
    device?.status === "online" &&
    !device?.protected
  );
}
function deviceRow(d) {
  const count = policies.filter((p) => p.device_id === d.id).length;
  return `<a href="#device/${encodeURIComponent(d.id)}" class="device-row"><div class="device-identity"><span class="device-name">${esc(d.nickname)}</span><span class="device-meta measured">${esc(d.addresses[0] || "No address")}</span></div><span class="connection-status" data-state="${esc(d.status)}">${esc(d.status)}</span><span class="row-policy">${count ? badge(count + " policies") : d.protected ? badge("Protected", "neutral") : '<span class="muted">No policy</span>'}</span><span class="row-source">${esc(d.source)}</span></a>`;
}
function activities(items) {
  return items.length
    ? items
        .map(
          (l) =>
            `<div class="activity-row"><time class="measured activity-time" datetime="${esc(l.time)}">${esc(date(l.time))}</time><strong>${esc(l.action.replaceAll(".", " / "))}</strong><span class="activity-outcome">${esc(l.outcome)}</span></div>`,
        )
        .join("")
    : empty(
        "Your activity starts here",
        "Changes and recovery events will appear in your local audit trail.",
      );
}
function overview() {
  const online = devices.filter((d) => d.status === "online").length;
  const protectedCount = devices.filter((d) => d.protected).length;
  const scheduled = policies.filter(
    (p) => p.window || p.starts_at || p.expires_at,
  ).length;
  const stats = [
    ["Connected devices", online, `${devices.length} in your inventory`],
    ["Configured policies", policies.length, "Active and scheduled"],
    ["Scheduled restrictions", scheduled, "Persistent across restarts"],
    ["Protected devices", protectedCount, "Excluded from restrictions"],
  ];
  return (
    heading(
      "A clearer view of your network.",
      "Inspect identities, policies and the enforcement path.",
      `<button class="secondary" type="button" data-action="refresh">${icon("refresh")}Refresh inventory</button><a class="primary" href="#devices">View devices</a>`,
    ) +
    capsNotice() +
    `<dl class="stats-grid">${stats.map(([label, n, note]) => `<div class="stat"><dt class="stat-top">${label}</dt><dd class="stat-number measured">${n}</dd><dd class="stat-note">${esc(note)}</dd></div>`).join("")}</dl>
    <div class="columns"><section class="panel device-ledger"><div class="panel-header"><div><h2>Your devices</h2><p>Known addresses and policy assignments.</p></div><a class="quiet" href="#devices">View all</a></div><div class="ledger-labels" aria-hidden="true"><span>Device / address</span><span>Connection</span><span>Policy</span><span>Source</span></div>${devices.slice(0, 4).map(deviceRow).join("") || empty("Make your network familiar", "Add authorized network ranges in settings, then refresh your passive inventory.")}</section>
    <section class="panel connection-readout"><div class="panel-header"><h2>Connection at a glance</h2></div><div class="panel-content"><dl class="path"><div><dt>Controller</dt><dd>Local workspace</dd></div><div><dt>Enforcement</dt><dd>${status.capabilities.adapter === "gateway" ? "Linux gateway" : "No live agent"}</dd></div><div><dt>Network data</dt><dd>${status.capabilities.simulated ? "Simulation" : "Local observations"}</dd></div></dl><div class="fact-row"><span>Operating mode</span><strong>${esc(status.capabilities.mode)}</strong></div><div class="fact-row"><span>Measured throughput</span><span>Unavailable</span></div><div class="fact-row"><span>Last reconciliation</span><time class="measured">${status.last_reconciled ? esc(date(status.last_reconciled)) : "Waiting"}</time></div></div></section></div>
    <section class="panel activity-ledger"><div class="panel-header"><div><h2>Recent activity</h2><p>A transparent record of what changed.</p></div><a class="quiet" href="#logs">Open audit log</a></div><div class="panel-content">${activities(logs.slice(0, 4))}</div></section>`
  );
}
function deviceCards(filter = "", state = "all") {
  const selected = devices.filter(
    (d) =>
      `${d.nickname} ${d.mac} ${d.addresses.join(" ")}`
        .toLowerCase()
        .includes(filter.toLowerCase()) &&
      (state === "all" || d.status === state),
  );
  return (
    selected
      .map(
        (d) =>
          `<article class="device-card"><div class="device-card-top"><h2>${esc(d.nickname)}</h2><span class="address measured">${esc(d.addresses[0] || "No address")}</span></div><div class="device-addresses"><span class="muted">MAC address</span><span class="measured">${esc(d.mac || "Unknown")}</span><span class="muted">${esc(d.source)}</span></div><div class="facts"><span class="muted">Identity</span><span>${d.confirmed ? "Confirmed" : "Needs review"}</span></div><div class="facts"><span class="muted">Policies</span><span class="measured">${policies.filter((p) => p.device_id === d.id).length} configured</span></div><div class="card-footer"><div>${badge(d.simulated ? "Simulated" : d.status, d.status === "online" ? "" : "neutral")}${d.protected ? badge("Protected", "neutral") : ""}</div><a href="#device/${encodeURIComponent(d.id)}">View device</a></div></article>`,
      )
      .join("") ||
    empty(
      "No matching devices",
      "Refresh inventory or update your search. Passive discovery requires configured authorized CIDRs.",
    )
  );
}
function connected() {
  const query = new URLSearchParams(location.hash.split("?")[1] || "");
  const search = query.get("search") || "";
  const filter = ["online", "offline", "unknown"].includes(query.get("state"))
    ? query.get("state")
    : "all";
  return (
    heading(
      "Your connected devices.",
      "Verify each identity before assigning a restriction.",
      `<button class="secondary" type="button" data-action="refresh">${icon("refresh")}Refresh inventory</button>`,
    ) +
    capsNotice() +
    `<div class="toolbar"><input id="search" aria-label="Search devices" value="${esc(search)}" placeholder="Name, IP, or MAC address"><select id="filter" aria-label="Filter connection status"><option value="all" ${filter === "all" ? "selected" : ""}>All devices</option><option value="online" ${filter === "online" ? "selected" : ""}>Online</option><option value="offline" ${filter === "offline" ? "selected" : ""}>Offline</option><option value="unknown" ${filter === "unknown" ? "selected" : ""}>Unknown</option></select><span class="count">${devices.length} devices in your inventory</span></div><div id="device-grid" class="device-grid">${deviceCards(search, filter)}</div>`
  );
}
function detail(id) {
  const d = devices.find((d) => d.id === id);
  if (!d)
    return empty(
      "Device not found",
      "Refresh inventory to check the latest observations.",
    );
  const facts = [
    ["IPv4 / IPv6", d.addresses.join(", ")],
    ["MAC address", d.mac || "Unknown"],
    ["Discovery source", d.source],
    ["Interface", d.interface || "Simulated"],
    ["Connection", d.status],
    ["Last seen", date(d.last_seen)],
    ["Vendor", d.vendor || "Unknown"],
    ["Identity", d.confirmed ? "Confirmed by administrator" : "Unconfirmed"],
    ["Protected", d.protected ? "Yes" : "No"],
  ];
  return (
    heading(
      d.nickname,
      "Device details / " + d.id,
      `<button class="secondary" type="button" data-action="rename" data-id="${esc(id)}">Edit device</button><button class="primary" type="button" data-action="limit" data-id="${esc(id)}" ${controlsAllowed(d) ? "" : "disabled"}>Set a limit</button>`,
    ) +
    (d.simulated
      ? notice(
          "Simulated device",
          "Changes affect this demo workspace only.",
          "warn",
        )
      : "") +
    `<div class="detail-grid"><section class="panel"><div class="panel-header"><h2>Identity & connection</h2></div><div class="panel-content">${facts.map(([k, v]) => `<div class="fact-row"><span>${k}</span><span>${esc(v)}</span></div>`).join("")}${!d.confirmed ? `<button class="secondary section-gap" type="button" data-action="identify" data-id="${esc(id)}">Confirm this identity</button>` : ""}</div></section><section class="panel"><div class="panel-header"><h2>Device policies</h2><button class="quiet" type="button" data-action="resume" data-id="${esc(id)}">Restore all</button></div>${policyRows(policies.filter((p) => p.device_id === id))}<div class="panel-content">${notice("Throughput is unavailable", "No measured traffic statistics are supplied by this adapter. Configured caps are not measurements.")}</div></section></div>`
  );
}
function policyRows(items) {
  return items.length
    ? items
        .map(
          (p) =>
            `<div class="policy-row"><div class="policy-symbol">${icon(p.blocked ? "access" : "bandwidth")}</div><div class="policy-info"><h3>${esc(p.label)} <span class="muted">/ ${esc(name(p.device_id))}</span></h3><p>${p.window ? esc(`${p.window.start.slice(0, 5)} to ${p.window.end.slice(0, 5)} / ${p.window.timezone} / ${p.window.weekdays.map((d) => ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d]).join(", ")}`) : p.starts_at ? "Starts " + esc(date(p.starts_at)) : "Immediate"}</p><p>${p.expires_at ? "Expires " + esc(date(p.expires_at)) : "No expiry"}</p></div><div class="rate measured">${p.blocked ? "Internet pause" : `<span>Download ${esc(p.download_mbps ?? "unlimited")}</span><span>Upload ${esc(p.upload_mbps ?? "unlimited")}</span><small>Configured Mbps cap</small>`}</div><button class="quiet" type="button" data-action="remove" data-id="${esc(p.id)}" aria-label="Remove ${esc(p.label)}">Remove</button></div>`,
        )
        .join("")
    : empty(
        "A little room to breathe",
        "No policies here. Restrictions appear after you explicitly confirm a target.",
      );
}
function policyPage(kind) {
  const schedule = kind === "scheduling",
    access = kind === "access";
  const items = policies.filter((p) =>
    schedule
      ? p.window || p.starts_at || p.expires_at
      : access
        ? p.blocked
        : !p.blocked,
  );
  return (
    heading(
      schedule
        ? "Make balance a routine."
        : access
          ? "A pause when it matters."
          : "More bandwidth. Less friction.",
      schedule
        ? "Set recurring windows or one-time restrictions in your timezone."
        : access
          ? "Manage internet access without losing sight of your devices."
          : "Set separate upload and download caps for confirmed devices.",
      `<button class="primary" type="button" data-action="${schedule ? "schedule" : access ? "pause" : "limit"}" ${status.capabilities[access ? "access" : "bandwidth"] || (schedule && status.capabilities.access) ? "" : "disabled"}>${schedule ? "New schedule" : access ? "Pause a device" : "Set a limit"}</button>`,
    ) +
    capsNotice() +
    `<section class="panel policy-ledger"><div class="panel-header"><h2>${schedule ? "Scheduled policies" : access ? "Internet access policies" : "Bandwidth policies"}</h2>${badge(items.length + " configured", "neutral")}</div>${policyRows(items)}</section><div class="policy-footnotes">${notice("Predictable policy conflicts", "An internet pause takes precedence. For overlapping limits, the lowest active cap in each direction wins. Restoring a device removes its future schedules too.")}${!access && !schedule ? notice("Caps, not traffic measurements", "Configured limits are not live throughput measurements. Live throughput statistics are unavailable.") : ""}</div>`
  );
}
async function agents() {
  const data = await api("/adapters"),
    c = data.current;
  return (
    heading(
      "Control starts with the right path.",
      "An authorized enforcement point makes network policies possible.",
    ) +
    capsNotice() +
    `<div class="settings-grid"><section class="panel"><div class="panel-header"><h2>Current adapter</h2>${badge(c.adapter)}</div><div class="panel-content"><p class="mode-readout">${esc(c.mode)}</p><p class="muted">${esc(c.reason)}</p>${[
      ["Discovery", c.discovery],
      ["Bandwidth limits", c.bandwidth],
      ["Internet access", c.access],
      ["IPv6", c.ipv6],
      ["Live statistics", c.statistics],
    ]
      .map(
        ([k, v]) =>
          `<div class="fact-row"><span>${k}</span><span>${v ? "Available" : "Unavailable"}</span></div>`,
      )
      .join(
        "",
      )}</div></section><section class="panel"><div class="panel-header"><h2>Deployment notes</h2></div><div class="panel-content"><div class="setting-item"><strong>Linux routed gateway</strong><p>Requires an explicitly configured traffic path, forwarding, authorized CIDRs and delegated interfaces. Experimental enforcement.</p></div><div class="setting-item"><strong>Inline bridge</strong><p>${esc(data.bridge)}.</p></div><div class="setting-item"><strong>Windows & Kali VMware</strong><p>The controller runs directly on Windows. A VM’s network mode does not establish control of household traffic. Use a secure connection to an authorized Linux gateway.</p></div></div></section></div>`
  );
}
async function diagnostics() {
  const d = await api("/diagnostics");
  return (
    heading(
      "A clear picture of your environment.",
      "Read-only diagnostics. No host networking is changed.",
    ) +
    notice("Configuration does not prove traffic coverage", d.note) +
    `<section class="panel"><div class="panel-header"><h2>${esc(d.os)} / Python ${esc(d.python)}</h2>${badge(d.administrator ? "Administrator" : "Standard user", "neutral")}</div><div class="panel-content"><div class="fact-row"><span>Virtualization</span><span>${esc(d.virtualization)}</span></div><div class="fact-row"><span>Network tools</span><span>${esc(
      Object.entries(d.tools)
        .map(([k, v]) => `${k}: ${v ? "available" : "unavailable"}`)
        .join("; "),
    )}</span></div><pre>${esc(JSON.stringify(d, null, 2))}</pre></div></section>`
  );
}
function audit() {
  return (
    heading(
      "Every change has a record.",
      "Local, structured history of policy decisions and recovery.",
    ) +
    `<section class="panel audit-ledger"><div class="table-wrap"><table><thead><tr><th>Time</th><th>Action</th><th>Outcome</th><th>Detail</th></tr></thead><tbody>${logs.map((l) => `<tr><td data-label="Time" class="measured">${esc(date(l.time))}</td><td data-label="Action">${esc(l.action)}</td><td data-label="Outcome">${badge(l.outcome, l.outcome === "failed" ? "warning" : "neutral")}</td><td data-label="Detail">${esc(l.detail)}</td></tr>`).join("")}</tbody></table></div>${!logs.length ? empty("No events yet", "Administrative actions will be recorded here.") : ""}</section>`
  );
}
async function settings() {
  const s = await api("/settings");
  return (
    heading(
      "A workspace that stays yours.",
      "Local settings, explicit permissions, and a way back.",
    ) +
    `<div class="settings-grid"><section class="panel"><div class="panel-header"><h2>Network & privacy</h2></div><div class="panel-content"><div class="setting-item"><strong>Authorized networks</strong><p>${esc(s.authorized_cidrs.join(", ") || "No ranges configured. Passive discovery is disabled.")}</p></div><div class="setting-item"><strong>Protected addresses</strong><p>${esc(s.protected_addresses.join(", ") || "No additional addresses configured.")}</p></div><div class="setting-item"><strong>Loopback binding / No telemetry</strong><p>${esc(s.configuration)}</p></div></div></section><section class="panel"><div class="panel-header"><h2>Your preferences</h2></div><div class="panel-content"><div class="setting-item"><strong>Appearance</strong><p>Choose the light or dark workspace.</p><button class="secondary section-gap" type="button" data-action="theme">Toggle theme</button></div><div class="setting-item"><strong>Custom bandwidth presets</strong><p>${presets.length} saved in this browser. Save new presets while setting a limit.</p></div><div class="setting-item"><strong>Emergency restoration</strong><p>Remove HomeLimiter restrictions and future policies. Other firewall rules remain under their existing administrator.</p><button class="danger section-gap" type="button" data-action="emergency">Restore all HomeLimiter policies</button></div></div></section></div>`
  );
}

const windowIcon = icon;
async function render() {
  if (!token) return;
  const version = ++routeVersion,
    hash = location.hash.slice(1) || "overview",
    [route, id] = hash.split("?")[0].split("/");
  $("#main").setAttribute("aria-busy", "true");
  if (!$("#main").innerHTML)
    $("#main").innerHTML =
      '<div class="loading" role="status">Loading network inventory…<div class="loading-skeleton" aria-hidden="true"></div></div>';
  $("#breadcrumb").textContent =
    route === "device"
      ? "Device details"
      : nav.find((n) => n[0] === route)?.[2] || "Overview";
  $("#navigation").innerHTML = nav
    .map(
      ([key, icon, label]) =>
        `<a class="nav-link ${key === route || (key === "devices" && route === "device") ? "active" : ""}" href="#${key}" title="${label}"><span class="nav-icon" aria-hidden="true">${windowIcon(icon)}</span><span class="nav-text">${label}</span></a>`,
    )
    .join("");
  try {
    [status, devices, policies, logs] = await Promise.all([
      api("/status"),
      api("/devices"),
      api("/policies"),
      api("/logs"),
    ]);
    const routes = {
      overview,
      devices: connected,
      bandwidth: () => policyPage("bandwidth"),
      access: () => policyPage("access"),
      scheduling: () => policyPage("scheduling"),
      agents,
      diagnostics,
      logs: audit,
      settings,
      device: () => detail(decodeURIComponent(id || "")),
    };
    const html = await (routes[route] || overview)();
    if (version !== routeVersion) return;
    $("#mode").textContent = status.capabilities.mode;
    $("#mode").className =
      "badge " + (status.capabilities.simulated ? "warning" : "");
    $("#main").innerHTML =
      (status.last_error
        ? notice("A reconciliation needs attention", status.last_error, "error")
        : "") + html;
  } catch (e) {
    if (version === routeVersion)
      $("#main").innerHTML = notice(
        "Unable to load this view",
        e.message,
        "error",
      );
  } finally {
    if (version === routeVersion) $("#main").setAttribute("aria-busy", "false");
  }
}
function modal(html, submit, label = "Confirm") {
  $("#modal-body").innerHTML = html;
  $("#modal-submit").textContent = label;
  $("#modal").showModal();
  $("#modal-form").onsubmit = async (e) => {
    e.preventDefault();
    $("#modal-submit").disabled = true;
    $("#modal-submit").setAttribute("aria-busy", "true");
    try {
      await submit(new FormData(e.target));
      $("#modal").close();
      await render();
    } catch (e) {
      toast(e.message);
    } finally {
      $("#modal-submit").disabled = false;
      $("#modal-submit").setAttribute("aria-busy", "false");
    }
  };
}
function policyDialog(action, id) {
  const access = action === "pause",
    schedule = action === "schedule";
  const candidates = devices.filter(
    (d) =>
      controlsAllowed(d, access ? "access" : "bandwidth") ||
      (schedule && controlsAllowed(d, "access")),
  );
  if (!candidates.length) {
    toast("No confirmed, online, unprotected device supports this control.");
    return;
  }
  modal(
    `<h2>${schedule ? "Create a schedule" : access ? "Pause internet access" : "Set a bandwidth limit"}</h2><p>${status.capabilities.simulated ? "This is a simulation. No real traffic will change." : "This changes traffic only at your authorized enforcement point."} Confirm the exact device before applying.</p><label for="target">Target device</label><select id="target" name="device_id">${candidates.map((d) => `<option value="${esc(d.id)}" ${d.id === id ? "selected" : ""}>${esc(d.nickname)} / ${esc(d.addresses[0])} / ${esc(d.mac)}</option>`).join("")}</select><label for="label">Policy name</label><input id="label" name="label" value="${schedule ? "Evening routine" : access ? "Take a break" : "Custom limit"}" required maxlength="80">${schedule ? '<label for="kind">Restriction</label><select id="kind" name="kind"><option value="block">Internet pause</option><option value="limit">Bandwidth limit</option></select>' : ""}${!access ? `<div class="field-pair"><div><label for="download">Download cap / Mbps</label><input id="download" name="download" type="number" min="0.008" max="10000" step="any" placeholder="Unlimited"></div><div><label for="upload">Upload cap / Mbps</label><input id="upload" name="upload" type="number" min="0.008" max="10000" step="any" placeholder="Unlimited"></div></div><div class="preset-list">${[{ name: "Study / 2 / 1", download: 2, upload: 1 }, { name: "Balanced / 10 / 5", download: 10, upload: 5 }, ...presets].map((p, i) => `<button type="button" data-preset="${i}">${esc(p.name)}</button>`).join("")}<button type="button" data-action="save-preset">+ Save preset</button></div>` : ""}${schedule ? `<label for="recurrence">Schedule type</label><select id="recurrence" name="recurrence"><option value="weekly">Recurring weekly window</option><option value="once">One-time window</option></select><div id="weekly-fields"><label for="zone">IANA timezone</label><input id="zone" name="timezone" value="${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)}"><label for="days">Start days (0 = Monday, 6 = Sunday)</label><input id="days" name="days" value="0,1,2,3,4" required><div class="field-pair"><div><label for="start">Start time</label><input id="start" name="start" type="time" value="22:30"></div><div><label for="end">End time</label><input id="end" name="end" type="time" value="06:30"></div></div><p class="hint">An overnight window belongs to its start day. Repeated DST hours follow the same local window.</p></div><div id="once-fields" hidden><label for="starts">Starts at (your local time)</label><input id="starts" name="starts" type="datetime-local"><label for="expires">Ends at (your local time)</label><input id="expires" name="expires" type="datetime-local"></div>` : `<label for="duration">Automatically restore after</label><select id="duration" name="duration"><option value="30">30 minutes</option><option value="60">1 hour</option><option value="120">2 hours</option>${!access ? '<option value="">No expiry</option>' : ""}</select>`}<label class="checkbox-label"><input type="checkbox" required>I confirm this target is authorized for this restriction.</label>`,
    async (f) => {
      const blocked = access || (schedule && f.get("kind") === "block");
      if (!status.capabilities[blocked ? "access" : "bandwidth"])
        throw new Error("The adapter does not support this restriction.");
      const target = f.get("device_id"),
        data = {
          device_id: target,
          confirm_device_id: target,
          label: f.get("label"),
          blocked,
        };
      if (!blocked) {
        if (f.get("download")) data.download_mbps = Number(f.get("download"));
        if (f.get("upload")) data.upload_mbps = Number(f.get("upload"));
      }
      if (schedule) {
        if (f.get("recurrence") === "weekly") {
          data.window = {
            timezone: f.get("timezone"),
            weekdays: f
              .get("days")
              .split(",")
              .map((x) => Number(x.trim())),
            start: f.get("start"),
            end: f.get("end"),
          };
        } else {
          if (!f.get("starts") || !f.get("expires"))
            throw new Error("Choose both one-time timestamps.");
          data.starts_at = new Date(f.get("starts")).toISOString();
          data.expires_at = new Date(f.get("expires")).toISOString();
        }
      } else if (f.get("duration"))
        data.expires_at = new Date(
          Date.now() + Number(f.get("duration")) * 60000,
        ).toISOString();
      await post("/policies", data);
    },
    "Confirm & apply",
  );
}
async function actionHandler(action, id) {
  if (["limit", "pause", "schedule"].includes(action))
    return policyDialog(action, id);
  if (action === "theme") {
    document.body.classList.toggle("dark");
    localStorage.setItem(
      "hl-theme",
      document.body.classList.contains("dark") ? "dark" : "light",
    );
    return;
  }
  if (action === "refresh") {
    await post("/discover");
    await render();
    toast("Inventory refreshed from the configured source.");
    return;
  }
  if (action === "remove") {
    await api("/policies/" + encodeURIComponent(id), {
      method: "DELETE",
      body: "{}",
    });
    await render();

    return;
  }
  if (action === "resume") {
    modal(
      "<h2>Restore this device?</h2><p>Remove all HomeLimiter policies for " +
        esc(name(id)) +
        ", including future schedules.</p>",
      () => post("/devices/" + encodeURIComponent(id) + "/resume"),
      "Restore device",
    );
    return;
  }
  if (action === "emergency") {
    modal(
      "<h2>Restore all devices?</h2><p>Remove every HomeLimiter restriction and future policy. This is recorded in your audit log.</p>",
      () => post("/emergency", { confirm: true }),
      "Restore all",
    );
    return;
  }
  if (action === "rename" || action === "identify") {
    const d = devices.find((d) => d.id === id);
    modal(
      `<h2>${action === "identify" ? "Confirm this identity" : "Edit your device"}</h2><p>Verify the MAC address against the device itself before allowing restrictions.</p><p><code>${esc(d.mac)}</code> / ${esc(d.addresses.join(", "))}</p><label for="nickname">Nickname</label><input id="nickname" name="nickname" value="${esc(d.nickname)}" maxlength="80" required><label class="checkbox-label"><input type="checkbox" name="confirm" ${d.confirmed ? "checked" : ""}>I have verified this device identity.</label><label class="checkbox-label"><input type="checkbox" name="protect" ${d.protected ? "checked disabled" : ""}>Protect this device from restrictions.</label>`,
      (f) =>
        api("/devices/" + encodeURIComponent(id), {
          method: "PATCH",
          body: JSON.stringify({
            nickname: f.get("nickname"),
            confirm_identity: f.has("confirm"),
            protect: f.has("protect"),
          }),
        }),
      "Save device",
    );
    return;
  }
  if (action === "save-preset") {
    const download = Number($("#download").value) || null,
      upload = Number($("#upload").value) || null;
    if (!download && !upload) {
      toast("Enter a cap before saving a preset.");
      return;
    }
    if (presets.length >= 12) {
      toast("You can save up to 12 custom presets.");
      return;
    }
    presets.push({
      name: `Custom / ${download ?? "∞"} / ${upload ?? "∞"}`,
      download,
      upload,
    });
    localStorage.setItem("hl-presets", JSON.stringify(presets));
    toast("Preset saved for your next limit.");
  }
}
document.addEventListener("click", (e) => {
  if (e.target.closest(".nav-link") && navigationMedia.matches)
    navigationDisclosure.open = false;
  const button = e.target.closest("[data-action]");
  if (button && !button.disabled)
    actionHandler(button.dataset.action, button.dataset.id).catch((e) =>
      toast(e.message),
    );
  const preset = e.target.closest("[data-preset]");
  if (preset) {
    const p = [
      { download: 2, upload: 1 },
      { download: 10, upload: 5 },
      ...presets,
    ][Number(preset.dataset.preset)];
    if (p) {
      $("#download").value = p.download ?? "";
      $("#upload").value = p.upload ?? "";
    }
  }
});
document.addEventListener("input", (e) => {
  if (e.target.matches("#search,#filter")) {
    $("#device-grid").innerHTML = deviceCards(
      $("#search").value,
      $("#filter").value,
    );
    const query = new URLSearchParams();
    if ($("#search").value) query.set("search", $("#search").value);
    if ($("#filter").value !== "all") query.set("state", $("#filter").value);
    history.replaceState(
      null,
      "",
      "#devices" + (query.size ? "?" + query : ""),
    );
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "recurrence") {
    const once = e.target.value === "once";
    $("#weekly-fields").hidden = once;
    $("#once-fields").hidden = !once;
  }
});
$("#modal-cancel").onclick = () => $("#modal").close();
$("#theme").onclick = () => actionHandler("theme");
$("#logout").onclick = () => {
  token = "";
  routeVersion++;
  $("#app").hidden = true;
  $("#login").hidden = false;
  $("#main").replaceChildren();
};
$("#login-form").onsubmit = async (e) => {
  e.preventDefault();
  const submitButton = e.target.querySelector('[type="submit"]');
  submitButton.disabled = true;
  submitButton.setAttribute("aria-busy", "true");
  $("#token").removeAttribute("aria-invalid");
  token = $("#token").value.trim();
  try {
    await api("/status");
    $("#token").value = "";
    $("#login-error").textContent = "";
    $("#login").hidden = true;
    $("#app").hidden = false;
    await render();
  } catch (e) {
    token = "";
    $("#login-error").textContent = e.message;
    $("#token").setAttribute("aria-invalid", "true");
    $("#token").focus();
  } finally {
    submitButton.disabled = false;
    submitButton.setAttribute("aria-busy", "false");
  }
};
window.addEventListener("hashchange", render);
const navigationMedia = matchMedia("(max-width: 60rem)");
const navigationDisclosure = $(".navigation-disclosure");
if (navigationMedia.matches) navigationDisclosure.open = false;
navigationMedia.addEventListener("change", (event) => {
  if (!event.matches) navigationDisclosure.open = true;
});
if (localStorage.getItem("hl-theme") === "dark")
  document.body.classList.add("dark");
setInterval(() => {
  if (token && !$("#modal").open) render();
}, 30000);
