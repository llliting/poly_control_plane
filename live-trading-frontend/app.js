const API_BASE = localStorage.getItem("liveTradingApiBase") || "/api/v1";
const STORAGE_KEY = "liveTradingFrontendPrefsV1";
const POLL_INTERVAL_MS = 5000;
const ET_TIME_ZONE = "America/New_York";
const PM_TRADE_COLUMNS = [
  { key: "timestamp", label: "Time" },
  { key: "slug", label: "Market" },
  { key: "outcome", label: "Outcome" },
  { key: "side", label: "Side" },
  { key: "price", label: "Price" },
  { key: "size", label: "Size" },
  { key: "amount_usdc", label: "Amt USDC" },
];

const TRADE_COLUMNS = [
  { key: "time", label: "Time" },
  { key: "service", label: "Service" },
  { key: "market", label: "Market" },
  { key: "dir", label: "Dir" },
  { key: "pUp", label: "p_up" },
  { key: "entry", label: "Entry Px" },
  { key: "amt", label: "Amt USDC" },
  { key: "result", label: "Result" },
  { key: "pnl", label: "PnL" },
  { key: "pnlPct", label: "PnL %" },
  { key: "status", label: "Status" },
];

const state = {
  activePage: "overview",
  pageScrollByPage: {},
  selectedService: "btc_5m_main",
  selectedOverviewService: "all",
  selectedTradeService: "all",
  selectedLogService: "all",
  overviewDateFrom: "2026-03-10",
  overviewDateTo: "2026-03-12",
  tradeSort: { key: "time", dir: "desc" },
  services: [],
  incidents: [],
  decisionsByService: {},
  serviceTradesByService: {},
  liveRowsByService: {},
  serviceHealthByKey: {},
  serviceControlsByKey: {},
  trades: [],
  pmTrades: [],
  pmTradeSort: { key: "timestamp", dir: "desc" },
  pmTradeSlugFilter: "",
  pmTradeSideFilter: "",
  pmTradeOutcomeFilter: "",
  openPositions: [],
  logs: [],
  marketSummary: {
    asset: "BTC",
    binance_price: 0,
    chainlink_price: 0,
    spread: 0,
    market_slug: "-",
    as_of: null,
  },
  marketTape: [],
  overviewData: null,
  pollTimer: null,
  logsAutoPinTop: true,
  overviewRedeemStatus: "redeem: idle",
  overviewRedeemTone: "",
  overviewRedeemBusy: false,
  overviewRedeemActionId: null,
  overviewRedeemPollTimer: null,
  serviceActionStatus: "action: idle",
  serviceActionTone: "",
  serviceActionBusy: false,
  serviceActionActionId: null,
  serviceActionPollTimer: null,
};

let scrollSaveTimer = null;
let _renderingLogs = false;

function formatNumber(value, decimals = 2) {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Number(value || 0));
}

function formatEtDateTime(isoTs) {
  if (!isoTs) return "-";
  const date = new Date(isoTs);
  if (Number.isNaN(date.getTime())) return String(isoTs);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: ET_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const get = (type) => parts.find((p) => p.type === type)?.value || "00";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}:${get("second")} ET`;
}

function formatEtTime(isoTs) {
  if (!isoTs) return "-";
  const date = new Date(isoTs);
  if (Number.isNaN(date.getTime())) return String(isoTs);
  return new Intl.DateTimeFormat("en-US", {
    timeZone: ET_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date) + " ET";
}

function asUiService(raw) {
  return {
    name: raw.service_key,
    runner: raw.runner_key,
    asset: raw.asset,
    status: raw.status,
    signal: raw.signal,
    pUp: Number(raw.p_up || 0),
    edge: Number(raw.edge || 0),
    traded: raw.traded ? "yes" : "no",
    commit: raw.git_commit || "-",
    heartbeat: `${Number(raw.heartbeat_age_sec || 0)}s`,
    portfolio: Number(raw.portfolio_usdc || 0),
    position: Number(raw.position_usdc || 0),
    cash: Number(raw.cash_usdc || 0),
    strategy: raw.strategy_key || "-",
    branch: raw.git_branch || "-",
    threshold: Number(raw.model_threshold || 0),
    edgeFloor: Number(raw.edge_floor || 0),
    edgeCeiling: Number(raw.edge_ceiling || 0),
  };
}

function normalizeSelections() {
  const names = new Set(state.services.map((s) => s.name));
  if (!names.has(state.selectedService)) state.selectedService = state.services[0]?.name || "btc_5m_main";
  if (!(state.selectedOverviewService === "all" || names.has(state.selectedOverviewService))) {
    state.selectedOverviewService = "all";
  }
  if (!(state.selectedTradeService === "all" || names.has(state.selectedTradeService))) {
    state.selectedTradeService = "all";
  }
  if (!(state.selectedLogService === "all" || names.has(state.selectedLogService))) {
    state.selectedLogService = "all";
  }
}

function normalizedApiOrigin() {
  const raw = String(API_BASE || "").trim();
  if (!raw) return window.location.origin;
  try {
    const u = new URL(raw);
    return u.origin + u.pathname.replace(/\/$/, "");
  } catch (_err) {
    if (raw.startsWith("/")) return `${window.location.origin}${raw}`.replace(/\/$/, "");
    return `${window.location.origin}/api/v1`;
  }
}

async function apiGet(path, params = {}) {
  const url = new URL(`${normalizedApiOrigin()}${path}`);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  });
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`GET ${path} failed (${res.status})`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(`${normalizedApiOrigin()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed (${res.status})`);
  return res.json();
}

function clearOverviewRedeemPollTimer() {
  if (state.overviewRedeemPollTimer) {
    clearTimeout(state.overviewRedeemPollTimer);
    state.overviewRedeemPollTimer = null;
  }
}

function clearServiceActionPollTimer() {
  if (state.serviceActionPollTimer) {
    clearTimeout(state.serviceActionPollTimer);
    state.serviceActionPollTimer = null;
  }
}

function updateOverviewRedeemStatus(text, tone = "") {
  state.overviewRedeemStatus = text;
  state.overviewRedeemTone = tone;
  const redeemStatus = document.getElementById("overview-redeem-status");
  if (redeemStatus) {
    redeemStatus.textContent = text;
    redeemStatus.className = `chip${tone ? ` ${tone}` : ""}`;
  }
  const redeemBtn = document.getElementById("overview-redeem-btn");
  if (redeemBtn) {
    const targetService =
      state.selectedOverviewService !== "all"
        ? state.selectedOverviewService
        : state.selectedService || state.services[0]?.name || "";
    redeemBtn.disabled = state.overviewRedeemBusy || !targetService;
  }
}

function updateServiceActionStatus(text, tone = "") {
  state.serviceActionStatus = text;
  state.serviceActionTone = tone;
  const status = document.getElementById("service-action-status");
  if (status) {
    status.textContent = text;
    status.className = `chip${tone ? ` ${tone}` : ""}`;
  }
  renderServiceControls();
}

async function pollOverviewRedeemAction(actionId, serviceKey) {
  try {
    const result = await apiGet(`/actions/${actionId}`);
    const status = String(result.status || "").toLowerCase();
    if (status === "queued") {
      updateOverviewRedeemStatus(`redeem: queued ${actionId}`, "warn");
    } else if (status === "running") {
      updateOverviewRedeemStatus(`redeem: running on ${serviceKey}`, "warn");
    } else if (status === "succeeded") {
      state.overviewRedeemBusy = false;
      state.overviewRedeemActionId = null;
      updateOverviewRedeemStatus(`redeem: succeeded`, "ok");
      return;
    } else if (status === "failed") {
      state.overviewRedeemBusy = false;
      state.overviewRedeemActionId = null;
      updateOverviewRedeemStatus(`redeem: failed`, "bad");
      return;
    } else {
      state.overviewRedeemBusy = false;
      state.overviewRedeemActionId = null;
      updateOverviewRedeemStatus(`redeem: ${status || "unknown"}`, "warn");
      return;
    }
    state.overviewRedeemPollTimer = setTimeout(() => {
      pollOverviewRedeemAction(actionId, serviceKey);
    }, 2000);
  } catch (err) {
    console.error(err);
    state.overviewRedeemBusy = false;
    state.overviewRedeemActionId = null;
    updateOverviewRedeemStatus(`redeem: queued, tracking unavailable`, "warn");
  }
}

async function pollServiceAction(actionId, serviceKey, action) {
  try {
    const result = await apiGet(`/actions/${actionId}`);
    const status = String(result.status || "").toLowerCase();
    if (status === "queued") {
      updateServiceActionStatus(`${action}: queued`, "warn");
    } else if (status === "running") {
      updateServiceActionStatus(`${action}: running`, "warn");
    } else if (status === "succeeded") {
      state.serviceActionBusy = false;
      state.serviceActionActionId = null;
      updateServiceActionStatus(`${action}: succeeded`, "ok");
      await refreshServices();
      await refreshOverviewData();
      await refreshServiceDetailData();
      if (state.selectedLogService === "all" || state.selectedLogService === serviceKey) {
        await refreshLogs();
      }
      renderAll();
      return;
    } else if (status === "failed") {
      state.serviceActionBusy = false;
      state.serviceActionActionId = null;
      updateServiceActionStatus(`${action}: failed`, "bad");
      await refreshLogs();
      renderLogs();
      return;
    } else {
      state.serviceActionBusy = false;
      state.serviceActionActionId = null;
      updateServiceActionStatus(`${action}: ${status || "unknown"}`, "warn");
      return;
    }
    state.serviceActionPollTimer = setTimeout(() => {
      pollServiceAction(actionId, serviceKey, action);
    }, 2000);
  } catch (err) {
    console.error(err);
    state.serviceActionBusy = false;
    state.serviceActionActionId = null;
    updateServiceActionStatus(`${action}: queued, tracking unavailable`, "warn");
  }
}

function statusPill(status) {
  if (status === "healthy") return `<span class="chip ok">${status}</span>`;
  if (status === "degraded") return `<span class="chip warn">${status}</span>`;
  if (status === "stopped") return `<span class="chip bad">${status}</span>`;
  return `<span class="chip bad">${status}</span>`;
}

function getService(name = state.selectedService) {
  return state.services.find((s) => s.name === name) || state.services[0];
}

function savePrefs() {
  const payload = {
    activePage: state.activePage,
    pageScrollByPage: state.pageScrollByPage,
    selectedService: state.selectedService,
    selectedOverviewService: state.selectedOverviewService,
    selectedTradeService: state.selectedTradeService,
    selectedLogService: state.selectedLogService,
    overviewDateFrom: state.overviewDateFrom,
    overviewDateTo: state.overviewDateTo,
    tradeSort: state.tradeSort,
    pmTradeSort: state.pmTradeSort,
    pmTradeSlugFilter: state.pmTradeSlugFilter,
    pmTradeSideFilter: state.pmTradeSideFilter,
    pmTradeOutcomeFilter: state.pmTradeOutcomeFilter,
  };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch (_err) {
    // Keep UI functional if localStorage is unavailable.
  }
}

function restorePrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return;

    if (typeof parsed.activePage === "string") {
      const validPages = ["overview", "services", "monitor", "trades", "pm-trades", "logs"];
      if (validPages.includes(parsed.activePage)) state.activePage = parsed.activePage;
    }
    if (parsed.pageScrollByPage && typeof parsed.pageScrollByPage === "object") {
      const next = {};
      ["overview", "services", "monitor", "trades", "pm-trades", "logs"].forEach((k) => {
        const entry = parsed.pageScrollByPage[k];
        if (!entry || typeof entry !== "object") return;
        const windowY = Number(entry.windowY);
        const contentY = Number(entry.contentY);
        next[k] = {
          windowY: Number.isFinite(windowY) ? Math.max(0, windowY) : 0,
          contentY: Number.isFinite(contentY) ? Math.max(0, contentY) : 0,
        };
      });
      state.pageScrollByPage = next;
    }
    if (typeof parsed.selectedService === "string") state.selectedService = parsed.selectedService;
    if (typeof parsed.selectedOverviewService === "string") state.selectedOverviewService = parsed.selectedOverviewService;
    if (typeof parsed.selectedTradeService === "string") state.selectedTradeService = parsed.selectedTradeService;
    if (typeof parsed.selectedLogService === "string") state.selectedLogService = parsed.selectedLogService;
    if (typeof parsed.overviewDateFrom === "string") state.overviewDateFrom = parsed.overviewDateFrom;
    if (typeof parsed.overviewDateTo === "string") state.overviewDateTo = parsed.overviewDateTo;
    if (
      parsed.tradeSort &&
      typeof parsed.tradeSort === "object" &&
      typeof parsed.tradeSort.key === "string" &&
      (parsed.tradeSort.dir === "asc" || parsed.tradeSort.dir === "desc") &&
      TRADE_COLUMNS.some((c) => c.key === parsed.tradeSort.key)
    ) {
      state.tradeSort = { key: parsed.tradeSort.key, dir: parsed.tradeSort.dir };
    }
    if (
      parsed.pmTradeSort &&
      typeof parsed.pmTradeSort === "object" &&
      typeof parsed.pmTradeSort.key === "string" &&
      (parsed.pmTradeSort.dir === "asc" || parsed.pmTradeSort.dir === "desc") &&
      PM_TRADE_COLUMNS.some((c) => c.key === parsed.pmTradeSort.key)
    ) {
      state.pmTradeSort = { key: parsed.pmTradeSort.key, dir: parsed.pmTradeSort.dir };
    }
    if (typeof parsed.pmTradeSlugFilter === "string") state.pmTradeSlugFilter = parsed.pmTradeSlugFilter;
    if (typeof parsed.pmTradeSideFilter === "string") state.pmTradeSideFilter = parsed.pmTradeSideFilter;
    if (typeof parsed.pmTradeOutcomeFilter === "string") state.pmTradeOutcomeFilter = parsed.pmTradeOutcomeFilter;
  } catch (_err) {
    // Ignore malformed persisted data.
  }
}

function getContentScrollTop() {
  const content = document.querySelector(".content");
  return content ? content.scrollTop : 0;
}

function capturePageScroll(page = state.activePage) {
  if (!page) return;
  state.pageScrollByPage[page] = {
    windowY: window.scrollY || window.pageYOffset || 0,
    contentY: getContentScrollTop(),
  };
}

function restorePageScroll(page = state.activePage) {
  const pos = state.pageScrollByPage[page] || { windowY: 0, contentY: 0 };
  requestAnimationFrame(() => {
    const content = document.querySelector(".content");
    if (content) content.scrollTop = pos.contentY || 0;
    window.scrollTo(0, pos.windowY || 0);
  });
}

function scheduleScrollSave() {
  if (scrollSaveTimer) clearTimeout(scrollSaveTimer);
  scrollSaveTimer = setTimeout(() => {
    capturePageScroll();
    savePrefs();
  }, 120);
}

function renderServiceSelector() {
  const select = document.getElementById("service-select");
  select.innerHTML = state.services.map((s) => `<option value="${s.name}">${s.name} (${s.runner})</option>`).join("");
  select.value = state.selectedService;
  select.onchange = async (e) => {
    state.selectedService = e.target.value;
    savePrefs();
    await refreshServiceDetailData();
    renderServiceDetail();
  };
}

function renderOverviewControls() {
  const serviceFilter = document.getElementById("overview-service-filter");
  const fromInput = document.getElementById("overview-date-from");
  const toInput = document.getElementById("overview-date-to");
  const redeemBtn = document.getElementById("overview-redeem-btn");
  const redeemStatus = document.getElementById("overview-redeem-status");
  serviceFilter.innerHTML = `
    <select id="overview-service-select">
      <option value="all">All</option>
      ${state.services.map((s) => `<option value="${s.name}">${s.name}</option>`).join("")}
    </select>
  `;
  const serviceSelect = document.getElementById("overview-service-select");
  serviceSelect.value = state.selectedOverviewService;
  serviceSelect.onchange = async (e) => {
    state.selectedOverviewService = e.target.value;
    savePrefs();
    await refreshOverviewData();
    renderOverview();
  };

  fromInput.value = state.overviewDateFrom;
  toInput.value = state.overviewDateTo;
  const onRangeChange = async () => {
    const from = fromInput.value || state.overviewDateFrom;
    const to = toInput.value || state.overviewDateTo;
    if (from > to) return;
    state.overviewDateFrom = from;
    state.overviewDateTo = to;
    savePrefs();
    await refreshOverviewData();
    renderOverview();
  };
  fromInput.onchange = onRangeChange;
  toInput.onchange = onRangeChange;

  if (redeemBtn && redeemStatus) {
    const targetService =
      state.selectedOverviewService !== "all"
        ? state.selectedOverviewService
        : state.selectedService || state.services[0]?.name || "";
    redeemBtn.disabled = state.overviewRedeemBusy || !targetService;
    redeemStatus.textContent = state.overviewRedeemStatus;
    redeemStatus.className = `chip${state.overviewRedeemTone ? ` ${state.overviewRedeemTone}` : ""}`;
    redeemBtn.onclick = async () => {
      if (!targetService) return;
      clearOverviewRedeemPollTimer();
      state.overviewRedeemBusy = true;
      updateOverviewRedeemStatus(`redeem: queueing on ${targetService}`, "warn");
      try {
        const result = await apiPost(`/services/${targetService}/actions`, { action: "redeem" });
        state.overviewRedeemActionId = result.action_id || null;
        updateOverviewRedeemStatus(`redeem: queued ${result.action_id || ""}`.trim(), "warn");
        if (state.overviewRedeemActionId) {
          pollOverviewRedeemAction(state.overviewRedeemActionId, targetService);
        } else {
          state.overviewRedeemBusy = false;
        }
        await refreshLogs();
        renderLogs();
      } catch (err) {
        console.error(err);
        state.overviewRedeemBusy = false;
        state.overviewRedeemActionId = null;
        updateOverviewRedeemStatus(`redeem: failed`, "bad");
      }
    };
  }
}

function renderTradeControls() {
  const serviceSelect = document.getElementById("trades-service-filter");
  serviceSelect.innerHTML = [
    `<option value="all">All</option>`,
    ...state.services.map((s) => `<option value="${s.name}">${s.name}</option>`),
  ].join("");
  serviceSelect.value = state.selectedTradeService;
  serviceSelect.onchange = async (e) => {
    state.selectedTradeService = e.target.value;
    savePrefs();
    await refreshTrades();
    renderTrades();
  };
}

function renderLogControls() {
  const serviceSelect = document.getElementById("logs-service-filter");
  serviceSelect.innerHTML = [
    `<option value="all">all services</option>`,
    ...state.services.map((s) => `<option value="${s.name}">${s.name}</option>`),
  ].join("");
  serviceSelect.value = state.selectedLogService;
  serviceSelect.onchange = async (e) => {
    state.selectedLogService = e.target.value;
    savePrefs();
    await refreshLogs();
    renderLogs();
  };
}

function renderOverview() {
  const data = state.overviewData;
  const stats = data?.stats || {};
  document.getElementById("stat-runners").textContent = `${stats.runners_online || 0} / ${stats.runners_total || 0}`;
  document.getElementById("stat-services").textContent = `${stats.services_healthy || 0} / ${stats.services_total || 0}`;
  const pnl = Number(stats.pnl_today_usdc || 0);
  const pnlEl = document.getElementById("stat-pnl");
  pnlEl.textContent = `${pnl >= 0 ? "+" : ""}$${formatNumber(pnl)}`;
  pnlEl.className = `value ${pnl >= 0 ? "pos" : "warn"}`;
  document.getElementById("stat-alerts").textContent = String(stats.open_alerts || 0);
  document.getElementById("stat-portfolio").textContent = `$${formatNumber(stats.portfolio_value_usdc || 0)}`;
  document.getElementById("stat-cash").textContent = `$${formatNumber(stats.cash_usdc || 0)}`;
  document.getElementById("stat-positions").textContent = `$${formatNumber(stats.positions_value_usdc || 0)}`;
  const redeemable = Number(stats.redeemable_usdc ?? stats.claimable_usdc ?? 0);
  document.getElementById("stat-redeemable").textContent = `$${formatNumber(redeemable)}`;

  const tbody = document.querySelector("#overview-services tbody");
  tbody.innerHTML = state.services
    .map(
      (s) => `
      <tr>
        <td>${s.name}</td>
        <td>${s.runner}</td>
        <td>${statusPill(s.status)}</td>
        <td>${s.signal}</td>
        <td>${Number(s.pUp || 0).toFixed(3)}</td>
        <td>${Number(s.edge || 0).toFixed(3)}</td>
        <td>${s.traded}</td>
        <td>$${formatNumber(s.portfolio)}</td>
        <td>$${formatNumber(s.position)}</td>
        <td>$${formatNumber(s.cash)}</td>
        <td class="mono">${s.commit}</td>
        <td>${s.heartbeat}</td>
      </tr>
    `,
    )
    .join("");

  // Open positions table
  const openPosTbody = document.querySelector("#overview-open-positions tbody");
  if (openPosTbody) {
    const openPositions = state.openPositions || [];
    if (openPositions.length === 0) {
      openPosTbody.innerHTML = `<tr><td colspan="6" style="text-align:center;opacity:0.5">No open positions</td></tr>`;
    } else {
      openPosTbody.innerHTML = openPositions
        .map((p) => {
          const pnl = Number(p.unrealized_pnl || 0);
          const pnlClass = pnl >= 0 ? "pos" : "warn";
          return `
          <tr>
            <td>${p.title || p.slug || "-"}</td>
            <td>${p.outcome || "-"}</td>
            <td>${Number(p.size || 0).toFixed(2)}</td>
            <td>${Number(p.avg_price || 0).toFixed(4)}</td>
            <td>$${formatNumber(p.current_value || 0)}</td>
            <td class="${pnlClass}">${pnl >= 0 ? "+" : ""}$${formatNumber(pnl)}</td>
          </tr>`;
        })
        .join("");
    }
  }

  const chips = document.getElementById("incident-chips");
  chips.innerHTML = state.incidents
    .map((i) => `<div class="chip ${i.level}">${i.text}</div>`)
    .join("");

  const range = data?.range_summary || {};
  const totalEl = document.getElementById("range-pnl-realized");
  const total = Number(range.realized_pnl_usdc || 0);
  totalEl.textContent = `${total >= 0 ? "+" : ""}$${formatNumber(total)}`;
  totalEl.className = `value ${total >= 0 ? "pos" : "warn"}`;
  document.getElementById("range-pnl-wl").textContent = `${range.wins || 0} / ${range.losses || 0}`;
  document.getElementById("range-pnl-count").textContent = String(range.trade_count || 0);
  const avg = Number(range.avg_pnl_usdc || 0);
  document.getElementById("range-pnl-avg").textContent = `${avg >= 0 ? "+" : ""}$${formatNumber(avg)}`;

  const portfolioCurve = data?.charts?.portfolio_curve || [];
  const pnlCurve = data?.charts?.cumulative_pnl_curve || [];
  const pVals = portfolioCurve.map((x) => Number(x.value_usdc || 0));
  const pLabels = portfolioCurve.map((x) => formatEtDateTime(x.ts));
  const cVals = pnlCurve.map((x) => Number(x.value_usdc || 0));
  const cLabels = pnlCurve.map((x) => formatEtDateTime(x.ts));
  document.getElementById("overview-chart-portfolio").innerHTML = sparklineSvg(pVals, "#8ef0c3", {
    labels: pLabels,
    prefix: "$",
    decimals: 2,
  });
  document.getElementById("overview-chart-pnl").innerHTML = sparklineSvg(cVals, "#7cc6fe", {
    labels: cLabels,
    prefix: "$",
    decimals: 2,
    showPlus: true,
  });
}

function renderServiceControls() {
  const s = getService();
  const ctl = state.serviceControlsByKey[s.name] || {};
  const buildBtn = document.getElementById("service-build-btn");
  const startBtn = document.getElementById("service-start-btn");
  const stopBtn = document.getElementById("service-stop-btn");
  const runState = document.getElementById("service-run-state");
  const actionStatus = document.getElementById("service-action-status");
  if (!buildBtn || !startBtn || !stopBtn || !runState) return;
  buildBtn.disabled = state.serviceActionBusy;
  startBtn.disabled = state.serviceActionBusy || !Boolean(ctl.can_start);
  stopBtn.disabled = state.serviceActionBusy || !Boolean(ctl.can_stop);
  runState.className = `chip ${s.status === "healthy" ? "ok" : s.status === "degraded" ? "warn" : "bad"}`;
  runState.textContent = `status: ${s.status}`;
  if (actionStatus) {
    actionStatus.className = `chip${state.serviceActionTone ? ` ${state.serviceActionTone}` : ""}`;
    actionStatus.textContent = state.serviceActionStatus;
  }
}

function renderServiceDetail() {
  const s = getService();
  if (!s) return;
  const health = state.serviceHealthByKey[s.name] || {};

  const serviceKv = document.getElementById("service-kv");
  serviceKv.innerHTML = [
    ["service", s.name],
    ["runner", s.runner],
    ["asset", s.asset],
    ["status", s.status],
    ["active strategy", s.strategy || "-"],
    ["model threshold", Number(s.threshold || 0).toFixed(2)],
    ["edge min / max", `${Number(s.edgeFloor || 0).toFixed(2)} / ${Number(s.edgeCeiling || 0).toFixed(2)}`],
    ["branch", s.branch || "-"],
    ["commit", s.commit || "-"],
  ]
    .map(([k, v]) => `<div class="k">${k}</div><div>${v}</div>`)
    .join("");

  const healthKv = document.getElementById("health-kv");
  healthKv.innerHTML = [
    ["ready", String(Boolean(health.ready))],
    ["binance connected", String(Boolean(health.binance_connected))],
    ["okx connected", String(Boolean(health.okx_connected))],
    ["rtds connected", String(Boolean(health.rtds_connected))],
    ["last event age", `${Number(health.last_event_age_ms || 0)} ms`],
    ["trade retries 10m", String(health.trade_retries_10m || 0)],
    ["portfolio", `$${formatNumber(s.portfolio || 0)}`],
    ["claimable", `$${formatNumber(health.claimable_usdc || 0)}`],
  ]
    .map(([k, v]) => `<div class="k">${k}</div><div>${v}</div>`)
    .join("");

  const decisions = state.decisionsByService[s.name] || [];
  const dtbody = document.querySelector("#service-decisions tbody");
  dtbody.innerHTML = decisions
    .map(
      (d) => `
      <tr>
        <td>${d.time}</td>
        <td>${d.market}</td>
        <td>${d.side}</td>
        <td>${Number(d.pUp || 0).toFixed(3)}</td>
        <td>${Number(d.th || 0).toFixed(2)}</td>
        <td>${Number(d.edge || 0).toFixed(3)}</td>
        <td>${d.streak}</td>
        <td>${d.traded}</td>
        <td>${d.reason || "-"}</td>
      </tr>
    `,
    )
    .join("");

  const serviceTrades = state.serviceTradesByService[s.name] || [];
  const tradeBody = document.querySelector("#service-trades tbody");
  if (tradeBody) {
    tradeBody.innerHTML = serviceTrades
      .map(
        (t) => `
        <tr>
          ${TRADE_COLUMNS.map((c) => tradeCell(t, c.key)).join("")}
        </tr>
      `,
      )
      .join("");
  }

  renderServiceControls();
}

function getTradeSortValue(trade, key) {
  if (key === "time") return Number(trade.timeEpoch || 0);
  if (key === "service") return trade.service;
  if (key === "market") return trade.market;
  if (key === "dir") return trade.dir;
  if (key === "pUp") return trade.pUp;
  if (key === "entry") return trade.entry;
  if (key === "amt") return trade.amt;
  if (key === "result") return trade.result;
  if (key === "pnl") return Number(trade.pnl.replace("+", "")) || 0;
  if (key === "pnlPct") {
    const pnlValue = Number(trade.pnl.replace("+", "")) || 0;
    return trade.amt > 0 ? (pnlValue / trade.amt) * 100 : 0;
  }
  if (key === "status") return trade.status;
  return "";
}

function tradeCell(trade, key) {
  if (key === "time") return `<td>${trade.time}</td>`;
  if (key === "service") return `<td>${trade.service}</td>`;
  if (key === "market") return `<td>${trade.market}</td>`;
  if (key === "dir") return `<td>${trade.dir}</td>`;
  if (key === "pUp") return `<td>${Number(trade.pUp || 0).toFixed(3)}</td>`;
  if (key === "entry") return `<td>${Number(trade.entry || 0).toFixed(3)}</td>`;
  if (key === "amt") return `<td>${Number(trade.amt || 0).toFixed(2)}</td>`;
  if (key === "result") return `<td>${trade.result}</td>`;
  if (key === "pnl") return `<td class="${trade.pnl.startsWith("+") ? "pos" : "warn"}">${trade.pnl}</td>`;
  if (key === "pnlPct") {
    const pnlValue = Number(trade.pnl.replace("+", "")) || 0;
    const pct = trade.amt > 0 ? (pnlValue / trade.amt) * 100 : 0;
    return `<td class="${pct >= 0 ? "pos" : "warn"}">${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%</td>`;
  }
  if (key === "status") return `<td>${trade.status}</td>`;
  return "<td>-</td>";
}

function renderTrades() {
  const table = document.getElementById("trade-table");
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");
  thead.innerHTML = `<tr>${TRADE_COLUMNS
    .map((c) => {
      const active = state.tradeSort.key === c.key;
      const arrow = active ? (state.tradeSort.dir === "asc" ? "▲" : "▼") : "";
      return `<th class="sortable ${active ? "active" : ""}" data-sort-key="${c.key}">${c.label} <span class="sort-arrow">${arrow}</span></th>`;
    })
    .join("")}</tr>`;

  const sorted = [...state.trades].sort((a, b) => {
    const av = getTradeSortValue(a, state.tradeSort.key);
    const bv = getTradeSortValue(b, state.tradeSort.key);
    let cmp = 0;
    if (typeof av === "number" && typeof bv === "number") cmp = av - bv;
    else cmp = String(av).localeCompare(String(bv));
    return state.tradeSort.dir === "asc" ? cmp : -cmp;
  });

  tbody.innerHTML = sorted
    .map(
      (t) => `
      <tr>
        ${TRADE_COLUMNS.map((c) => tradeCell(t, c.key)).join("")}
      </tr>
    `,
    )
    .join("");

  thead.querySelectorAll("[data-sort-key]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sortKey;
      if (!key) return;
      if (state.tradeSort.key === key) state.tradeSort.dir = state.tradeSort.dir === "asc" ? "desc" : "asc";
      else {
        state.tradeSort.key = key;
        state.tradeSort.dir = "asc";
      }
      savePrefs();
      renderTrades();
    });
  });
}

function getPmTradeSortValue(trade, key) {
  if (key === "timestamp") return trade.timestamp || "";
  if (key === "price") return Number(trade.price || 0);
  if (key === "size") return Number(trade.size || 0);
  if (key === "amount_usdc") return Number(trade.amount_usdc || 0);
  if (key === "slug") return trade.slug || "";
  if (key === "outcome") return trade.outcome || "";
  if (key === "side") return trade.side || "";
  return "";
}

function pmTradeCell(trade, key) {
  if (key === "timestamp") return `<td>${formatEtDateTime(trade.timestamp)}</td>`;
  if (key === "slug") return `<td>${trade.slug || "-"}</td>`;
  if (key === "outcome") return `<td>${trade.outcome || "-"}</td>`;
  if (key === "side") return `<td>${trade.side || "-"}</td>`;
  if (key === "price") return `<td>${Number(trade.price || 0).toFixed(4)}</td>`;
  if (key === "size") return `<td>${Number(trade.size || 0).toFixed(2)}</td>`;
  if (key === "amount_usdc") return `<td>$${formatNumber(trade.amount_usdc || 0)}</td>`;
  return "<td>-</td>";
}

function renderPmTrades() {
  const table = document.getElementById("pm-trade-table");
  if (!table) return;
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");

  thead.innerHTML = `<tr>${PM_TRADE_COLUMNS
    .map((c) => {
      const active = state.pmTradeSort.key === c.key;
      const arrow = active ? (state.pmTradeSort.dir === "asc" ? "▲" : "▼") : "";
      return `<th class="sortable ${active ? "active" : ""}" data-pm-sort-key="${c.key}">${c.label} <span class="sort-arrow">${arrow}</span></th>`;
    })
    .join("")}</tr>`;

  // Apply client-side filters
  let filtered = [...state.pmTrades];
  if (state.pmTradeSlugFilter) {
    const q = state.pmTradeSlugFilter.toLowerCase();
    filtered = filtered.filter((t) => (t.slug || "").toLowerCase().includes(q));
  }
  if (state.pmTradeSideFilter) {
    filtered = filtered.filter((t) => t.side === state.pmTradeSideFilter);
  }
  if (state.pmTradeOutcomeFilter) {
    const q = state.pmTradeOutcomeFilter.toLowerCase();
    filtered = filtered.filter((t) => (t.outcome || "").toLowerCase().includes(q));
  }

  // Sort
  const sorted = filtered.sort((a, b) => {
    const av = getPmTradeSortValue(a, state.pmTradeSort.key);
    const bv = getPmTradeSortValue(b, state.pmTradeSort.key);
    let cmp = 0;
    if (typeof av === "number" && typeof bv === "number") cmp = av - bv;
    else cmp = String(av).localeCompare(String(bv));
    return state.pmTradeSort.dir === "asc" ? cmp : -cmp;
  });

  tbody.innerHTML = sorted
    .map(
      (t) => `<tr>${PM_TRADE_COLUMNS.map((c) => pmTradeCell(t, c.key)).join("")}</tr>`,
    )
    .join("");

  // Wire sort headers
  thead.querySelectorAll("[data-pm-sort-key]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.pmSortKey;
      if (!key) return;
      if (state.pmTradeSort.key === key) state.pmTradeSort.dir = state.pmTradeSort.dir === "asc" ? "desc" : "asc";
      else {
        state.pmTradeSort.key = key;
        state.pmTradeSort.dir = "desc";
      }
      savePrefs();
      renderPmTrades();
    });
  });
}

function wirePmTradeControls() {
  const slugInput = document.getElementById("pm-trades-slug-filter");
  const sideSelect = document.getElementById("pm-trades-side-filter");
  const outcomeInput = document.getElementById("pm-trades-outcome-filter");

  if (slugInput) {
    slugInput.value = state.pmTradeSlugFilter;
    slugInput.oninput = () => {
      state.pmTradeSlugFilter = slugInput.value;
      savePrefs();
      renderPmTrades();
    };
  }
  if (sideSelect) {
    sideSelect.value = state.pmTradeSideFilter;
    sideSelect.onchange = () => {
      state.pmTradeSideFilter = sideSelect.value;
      savePrefs();
      renderPmTrades();
    };
  }
  if (outcomeInput) {
    outcomeInput.value = state.pmTradeOutcomeFilter;
    outcomeInput.oninput = () => {
      state.pmTradeOutcomeFilter = outcomeInput.value;
      savePrefs();
      renderPmTrades();
    };
  }
}

function renderLogs() {
  const logView = document.getElementById("log-view");
  if (!logView) return;
  const wasAutoPinTop = state.logsAutoPinTop;
  const prevScrollTop = logView.scrollTop;
  _renderingLogs = true;
  logView.innerHTML = state.logs
    .map((line) => `<div class="line-${line.level}">${line.text}</div>`)
    .join("");
  if (wasAutoPinTop) {
    logView.scrollTop = 0;
  } else {
    logView.scrollTop = prevScrollTop;
  }
  _renderingLogs = false;
}

function renderPriceMonitor() {
  document.getElementById("binance-price").textContent = formatNumber(state.marketSummary.binance_price || 0);
  document.getElementById("chainlink-price").textContent = formatNumber(state.marketSummary.chainlink_price || 0);
  document.getElementById("spread-price").textContent = Number(state.marketSummary.spread || 0).toFixed(2);
  document.getElementById("market-slug").textContent = state.marketSummary.market_slug || "-";

  const s = getService();
  const rows = state.liveRowsByService[s?.name] || [];
  const tbody = document.querySelector("#service-live-data tbody");
  if (tbody) {
    tbody.innerHTML = rows
      .map(
        (r) => `
        <tr>
          <td>${r.ts}</td>
          <td>${Number(r.binance || 0).toFixed(2)}</td>
          <td>${Number(r.chainlink || 0).toFixed(2)}</td>
          <td>${Number(r.pmMid || 0).toFixed(3)}</td>
          <td>${Number(r.pmBid || 0).toFixed(3)}</td>
          <td>${Number(r.pmAsk || 0).toFixed(3)}</td>
          <td>${Number(r.clBinSpread || 0).toFixed(2)}</td>
          <td>${r.bucketLeft}s</td>
          <td>${r.ingestLag}ms</td>
          <td>${r.streak}</td>
        </tr>
      `,
      )
      .join("");
  }
}

function formatTooltipValue(value, opts) {
  const decimals = typeof opts.decimals === "number" ? opts.decimals : 2;
  const prefix = opts.prefix || "";
  const suffix = opts.suffix || "";
  const showPlus = Boolean(opts.showPlus);
  const abs = Math.abs(value).toFixed(decimals);
  const sign = value < 0 ? "-" : showPlus && value > 0 ? "+" : "";
  return `${sign}${prefix}${abs}${suffix}`;
}

function escapeXml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function sparklineSvg(values, color, opts = {}) {
  if (!values.length) return "";
  const w = 420;
  const h = 78;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.0001);
  const pointsRaw = values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * w;
      const y = h - ((v - min) / range) * h;
      return { x, y };
    })
    .map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`)
    .join(" ");

  const labels = Array.isArray(opts.labels) ? opts.labels : [];
  const circles = values
    .map((v, i) => {
      const x = (i / Math.max(values.length - 1, 1)) * w;
      const y = h - ((v - min) / range) * h;
      const label = labels[i] || `point ${i + 1}`;
      const tip = escapeXml(`${label}: ${formatTooltipValue(v, opts)}`);
      return `
        <circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="3.2" fill="${color}" fill-opacity="0.38">
          <title>${tip}</title>
        </circle>
      `;
    })
    .join("");

  return `
    <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" width="100%" height="100%">
      <polyline fill="none" stroke="${color}" stroke-width="2.2" points="${pointsRaw}" />
      ${circles}
    </svg>
  `;
}

async function refreshServices() {
  const data = await apiGet("/services");
  state.services = (data.items || []).map(asUiService);
  normalizeSelections();
}

async function refreshOverviewData() {
  const data = await apiGet("/overview", {
    service_key: state.selectedOverviewService,
    from: state.overviewDateFrom,
    to: state.overviewDateTo,
  });
  state.overviewData = data;
  state.openPositions = data.open_positions || [];
  state.incidents = (data.incidents || []).map((i) => ({
    level: i.severity === "error" ? "bad" : i.severity === "warn" ? "warn" : "ok",
    text: i.message,
  }));
}

async function refreshServiceDetailData() {
  const key = state.selectedService;
  const [detail, decisions, runtime, trades] = await Promise.all([
    apiGet(`/services/${key}`),
    apiGet(`/services/${key}/decisions`, { limit: 50 }),
    apiGet(`/services/${key}/runtime-signals`, { limit: 50 }),
    apiGet("/trades", {
      service_key: key,
      limit: 50,
      sort_by: "open_time",
      sort_dir: "desc",
    }),
  ]);

  const s = asUiService(detail.service);
  const idx = state.services.findIndex((x) => x.name === key);
  if (idx >= 0) state.services[idx] = { ...state.services[idx], ...s };

  state.serviceHealthByKey[key] = detail.health || {};
  state.serviceControlsByKey[key] = detail.controls || {};
  state.decisionsByService[key] = (decisions.items || []).map((d) => ({
    time: formatEtDateTime(d.ts),
    market: d.market_slug,
    side: d.side,
    pUp: Number(d.p_up || 0),
    th: Number(d.threshold || 0),
    edge: Number(d.edge || 0),
    streak: `${d.streak_hits || 0}/${d.streak_target || 0}`,
    traded: d.traded ? "yes" : "no",
    reason: d.no_trade_reason || "",
  }));
  let serviceTradeRows = (trades.items || []).map(mapTradeRow);
  if (serviceTradeRows.length === 0) {
    serviceTradeRows = state.trades.filter((t) => t.service === key);
  }
  state.serviceTradesByService[key] = serviceTradeRows;
  state.liveRowsByService[key] = (runtime.items || []).map((r) => ({
    ts: formatEtDateTime(r.ts),
    binance: Number(r.binance_price || 0),
    chainlink: Number(r.chainlink_price || 0),
    pmMid: Number(r.pm_mid || 0),
    pmBid: Number(r.pm_bid || 0),
    pmAsk: Number(r.pm_ask || 0),
    clBinSpread: Number(r.cl_bin_spread || 0),
    bucketLeft: Number(r.bucket_seconds_left || 0),
    ingestLag: Number(r.ingest_lag_ms || 0),
    streak: `${r.streak_hits || 0}/${r.streak_target || 0}`,
  }));
}

async function refreshTrades() {
  const data = await apiGet("/trades", {
    service_key: state.selectedTradeService,
    limit: 200,
    sort_by: "open_time",
    sort_dir: "desc",
  });
  state.trades = (data.items || []).map(mapTradeRow);
}

async function refreshPmTrades() {
  const data = await apiGet("/polymarket-trades", {
    limit: 500,
    sort_by: "timestamp",
    sort_dir: "desc",
  });
  state.pmTrades = data.items || [];
}

function mapTradeRow(t) {
  return {
    time: formatEtDateTime(t.open_time),
    timeEpoch: Date.parse(t.open_time) || 0,
    service: t.service_key,
    market: t.market_slug,
    dir: t.side,
    pUp: Number(t.model_probability || 0),
    entry: Number(t.entry_price || 0),
    amt: Number(t.amount_usdc || 0),
    result: t.result,
    pnl: `${Number(t.pnl_usdc || 0) >= 0 ? "+" : ""}${Number(t.pnl_usdc || 0).toFixed(2)}`,
    status: t.status,
  };
}

async function refreshLogs() {
  const data = await apiGet("/logs", {
    service_key: state.selectedLogService,
    limit: 200,
  });
  state.logs = (data.items || []).map((line) => ({
    service: line.service_key,
    level: line.level,
    text: `${formatEtDateTime(line.ts)} ${line.message}`,
  }));
}

async function refreshMarket() {
  const [summary, tape] = await Promise.all([
    apiGet("/market/summary", { asset: "BTC" }),
    apiGet("/market/tape", { asset: "BTC", limit: 40 }),
  ]);
  state.marketSummary = summary;
  state.marketTape = tape.items || [];
}

function wireNav() {
  const navButtons = document.querySelectorAll(".nav-btn");
  const pages = document.querySelectorAll(".page");
  const setActivePage = (page, opts = {}) => {
    const { preserveScroll = true } = opts;
    if (!page) return;
    const exists = Array.from(navButtons).some((b) => b.dataset.page === page);
    if (!exists) return;
    navButtons.forEach((b) => b.classList.toggle("active", b.dataset.page === page));
    const target = `page-${page}`;
    pages.forEach((p) => p.classList.toggle("active", p.id === target));
    state.activePage = page;
    if (preserveScroll) restorePageScroll(page);
    savePrefs();
  };

  navButtons.forEach((btn) => {
    btn.addEventListener("click", async () => {
      capturePageScroll(state.activePage);
      setActivePage(btn.dataset.page, { preserveScroll: true });
      await refreshActivePage();
      renderAll();
    });
  });
  setActivePage(state.activePage, { preserveScroll: false });
}

function wireServiceActions() {
  const buildBtn = document.getElementById("service-build-btn");
  const startBtn = document.getElementById("service-start-btn");
  const stopBtn = document.getElementById("service-stop-btn");
  if (!buildBtn || !startBtn || !stopBtn) return;

  const runServiceAction = async (action) => {
    const s = getService();
    if (!s) return;
    clearServiceActionPollTimer();
    state.serviceActionBusy = true;
    updateServiceActionStatus(`${action}: queueing`, "warn");
    try {
      const result = await apiPost(`/services/${s.name}/actions`, { action });
      state.serviceActionActionId = result.action_id || null;
      updateServiceActionStatus(`${action}: queued`, "warn");
      if (state.serviceActionActionId) {
        pollServiceAction(state.serviceActionActionId, s.name, action);
      } else {
        state.serviceActionBusy = false;
        updateServiceActionStatus(`${action}: queued`, "warn");
      }
    } catch (err) {
      console.error(err);
      state.serviceActionBusy = false;
      state.serviceActionActionId = null;
      updateServiceActionStatus(`${action}: failed`, "bad");
    }
  };

  buildBtn.onclick = async () => runServiceAction("build");
  startBtn.onclick = async () => runServiceAction("start");
  stopBtn.onclick = async () => runServiceAction("stop");
}

function renderAll() {
  renderOverviewControls();
  renderServiceSelector();
  renderTradeControls();
  renderLogControls();
  wirePmTradeControls();
  renderOverview();
  renderServiceDetail();
  renderTrades();
  renderPmTrades();
  renderPriceMonitor();
  renderLogs();
}

async function refreshActivePage() {
  if (state.activePage === "overview") await refreshOverviewData();
  if (state.activePage === "services") await refreshServiceDetailData();
  if (state.activePage === "monitor") {
    await Promise.all([refreshMarket(), refreshServiceDetailData()]);
  }
  if (state.activePage === "trades") await refreshTrades();
  if (state.activePage === "pm-trades") await refreshPmTrades();
  if (state.activePage === "logs") await refreshLogs();
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(async () => {
    try {
      await refreshServices();
      await refreshActivePage();
      renderAll();
    } catch (err) {
      console.error("poll failed", err);
    }
  }, POLL_INTERVAL_MS);
}

async function initialLoad() {
  await refreshServices();
  normalizeSelections();
  await refreshTrades();
  await Promise.all([
    refreshOverviewData(),
    refreshServiceDetailData(),
    refreshPmTrades(),
    refreshLogs(),
    refreshMarket(),
  ]);
}

async function init() {
  restorePrefs();
  wireNav();
  wireServiceActions();
  window.addEventListener("scroll", scheduleScrollSave, { passive: true });
  const content = document.querySelector(".content");
  if (content) content.addEventListener("scroll", scheduleScrollSave, { passive: true });
  const logView = document.getElementById("log-view");
  if (logView) {
    logView.addEventListener(
      "scroll",
      () => {
        if (_renderingLogs) return;
        state.logsAutoPinTop = logView.scrollTop <= 8;
      },
      { passive: true },
    );
  }
  window.addEventListener("beforeunload", () => {
    capturePageScroll();
    savePrefs();
  });

  try {
    await initialLoad();
    renderAll();
  } catch (err) {
    console.error("initial load failed", err);
  }
  restorePageScroll(state.activePage);
  startPolling();
}

init();
