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

const PM_POSITION_COLUMNS = [
  { key: "title", label: "Market" },
  { key: "outcome", label: "Outcome" },
  { key: "status", label: "Status" },
  { key: "size", label: "Size" },
  { key: "avg_price", label: "Avg Price" },
  { key: "initial_value", label: "Cost" },
  { key: "current_value", label: "Value" },
  { key: "realized_pnl", label: "Realized PnL" },
  { key: "unrealized_pnl", label: "Unrealized PnL" },
  { key: "pnl_pct", label: "PnL %" },
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
  liveRowsByService: {},
  latestRuntimeByService: {},
  serviceHealthByKey: {},
  serviceControlsByKey: {},
  trades: [],
  pmTrades: [],
  pmTradeSort: { key: "timestamp", dir: "desc" },
  pmTradeSlugFilter: "",
  pmTradeSideFilter: "",
  pmTradeOutcomeFilter: "",
  pmPositions: [],
  pmPositionSort: { key: "current_value", dir: "desc" },
  pmPositionStatusFilter: "all",
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
  orderbook: null,
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

function formatFixedOrDash(value, decimals = 4) {
  if (value == null || value === "") return "-";
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(decimals) : "-";
}

function formatNumberOrDash(value, decimals = 2) {
  if (value == null || value === "") return "-";
  const num = Number(value);
  return Number.isFinite(num) ? formatNumber(num, decimals) : "-";
}

function isContractPrice(value) {
  const num = Number(value);
  return Number.isFinite(num) && num > 0 && num <= 1;
}

function pickRuntimeUpPrice(row) {
  if (!row) return null;
  if (isContractPrice(row.pmMid)) return Number(row.pmMid);
  if (isContractPrice(row.pmAsk)) return Number(row.pmAsk);
  if (isContractPrice(row.pmBid)) return Number(row.pmBid);
  return null;
}

function pickDecisionUpPrice(decision) {
  if (!decision) return null;
  return isContractPrice(decision.marketPrice) ? Number(decision.marketPrice) : null;
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
    pmPositionSort: state.pmPositionSort,
    pmPositionStatusFilter: state.pmPositionStatusFilter,
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
    if (
      parsed.pmPositionSort &&
      typeof parsed.pmPositionSort === "object" &&
      typeof parsed.pmPositionSort.key === "string" &&
      (parsed.pmPositionSort.dir === "asc" || parsed.pmPositionSort.dir === "desc") &&
      PM_POSITION_COLUMNS.some((c) => c.key === parsed.pmPositionSort.key)
    ) {
      state.pmPositionSort = { key: parsed.pmPositionSort.key, dir: parsed.pmPositionSort.dir };
    }
    if (typeof parsed.pmPositionStatusFilter === "string") state.pmPositionStatusFilter = parsed.pmPositionStatusFilter;
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
  const orderbook = state.orderbook;

  const liveRows = state.liveRowsByService[s.name] || [];
  const currentUpOrderbookPrice =
    orderbook && orderbook.yes
      ? (
          isContractPrice(orderbook.yes.mid)
            ? Number(orderbook.yes.mid)
            : isContractPrice(orderbook.yes.best_ask)
              ? Number(orderbook.yes.best_ask)
              : isContractPrice(orderbook.yes.best_bid)
                ? Number(orderbook.yes.best_bid)
                : null
        )
      : null;
  const chartEl = document.getElementById("service-signal-chart");
  const chartMetaEl = document.getElementById("service-signal-chart-meta");
  if (chartEl && chartMetaEl) {
    const decisions = state.decisionsByService[s.name] || [];
    const hasMeaningfulRuntime = liveRows.some(
      (r) => Number.isFinite(r.pUp) && r.pUp !== 0,
    );
    const orderedRuntime = [...liveRows].reverse();
    const runtimePriceSeries = orderedRuntime.map((r, idx) => ({
      label: r.ts,
      value:
        idx === orderedRuntime.length - 1 && isContractPrice(currentUpOrderbookPrice)
          ? Number(currentUpOrderbookPrice)
          : pickRuntimeUpPrice(r),
    }));
    const hasMeaningfulRuntimeUpPx = runtimePriceSeries.some(
      (row) => Number.isFinite(row.value),
    );
    const decisionPriceSeries = [...decisions].reverse().map((d) => ({
      label: d.time,
      value: pickDecisionUpPrice(d),
    }));
    let pSeries, priceSeries;
    if (hasMeaningfulRuntime && hasMeaningfulRuntimeUpPx) {
      pSeries = orderedRuntime.map((r) => ({
        label: r.ts,
        value: Number.isFinite(r.pUp) ? r.pUp : null,
      }));
      priceSeries = runtimePriceSeries;
    } else if (hasMeaningfulRuntime) {
      pSeries = orderedRuntime.map((r) => ({
        label: r.ts,
        value: Number.isFinite(r.pUp) ? r.pUp : null,
      }));
      priceSeries = decisionPriceSeries;
    } else if (decisions.length > 0) {
      const decOrdered = [...decisions].reverse();
      pSeries = decOrdered.map((d) => ({
        label: d.time,
        value: Number.isFinite(d.pUp) ? d.pUp : null,
      }));
      priceSeries = decisionPriceSeries;
    } else {
      pSeries = [];
      priceSeries = [];
    }
    const hasData =
      pSeries.some((row) => Number.isFinite(row.value)) ||
      priceSeries.some((row) => Number.isFinite(row.value));
    // Show latest p_up and UP px numbers next to chart meta label
    const lastPUp = [...pSeries].reverse().find((r) => Number.isFinite(r.value));
    const lastUpPx = [...priceSeries].reverse().find((r) => Number.isFinite(r.value));
    const lastDiff = (lastPUp && lastUpPx) ? lastPUp.value - lastUpPx.value : null;
    const diffStr = lastDiff != null ? `${lastDiff >= 0 ? "+" : ""}${lastDiff.toFixed(3)}` : "-";
    const diffColor = lastDiff != null ? (lastDiff >= 0 ? "#3ddc97" : "#ffd166") : "#8b949e";
    chartMetaEl.innerHTML =
      `<span style="color:#7cc6fe">p_up: <b>${lastPUp ? Number(lastPUp.value).toFixed(3) : "-"}</b></span>` +
      ` &nbsp; ` +
      `<span style="color:#3ddc97">UP px: <b>${lastUpPx ? Number(lastUpPx.value).toFixed(3) : "-"}</b></span>` +
      ` &nbsp; ` +
      `<span style="color:${diffColor}">diff: <b>${diffStr}</b></span>`;
    chartEl.innerHTML = hasData
      ? dualSparklineSvg(pSeries, priceSeries, {
          min: 0,
          max: 1,
          colorA: "#7cc6fe",
          colorB: "#3ddc97",
        })
      : '<div style="height:100%;display:flex;align-items:center;justify-content:center;color:var(--text-dim);font-size:0.7rem">no live signal data</div>';
  }

  const decisions = state.decisionsByService[s.name] || [];
  const dtbody = document.querySelector("#service-decisions tbody");
  if (!dtbody) return;
  if (decisions.length === 0) {
    dtbody.innerHTML =
      '<tr><td colspan="13" style="text-align:center;color:var(--text-dim)">no decisions</td></tr>';
  } else {
    dtbody.innerHTML = decisions
      .map(
        (d) => {
          const diff = (Number.isFinite(d.pUp) && Number.isFinite(d.upPrice))
            ? d.pUp - d.upPrice
            : null;
          const diffStr = diff != null ? `${diff >= 0 ? "+" : ""}${diff.toFixed(3)}` : "-";
          const diffCls = diff != null ? (diff >= 0 ? "pos" : "warn") : "";
          return `
          <tr>
            <td>${d.time}</td>
            <td>${d.market || "-"}</td>
            <td>${d.side}</td>
            <td>${Number(d.pUp || 0).toFixed(3)}</td>
            <td>${formatFixedOrDash(d.upPrice, 3)}</td>
            <td>${formatNumberOrDash(d.binancePrice, 2)}</td>
            <td>${d.binanceChange5m == null ? "-" : `${Number(d.binanceChange5m) >= 0 ? "+" : ""}${formatNumber(d.binanceChange5m, 2)}`}</td>
            <td>${Number(d.th || 0).toFixed(2)}</td>
            <td>${Number(d.edge || 0).toFixed(3)}</td>
            <td class="${diffCls}">${diffStr}</td>
            <td>${d.streak}</td>
            <td>${d.traded}</td>
            <td>${d.reason || "-"}</td>
          </tr>
        `;
        },
      )
      .join("");
  }

  renderOrderbook();

  renderServiceControls();
}

function renderOrderbook() {
  const ob = state.orderbook;
  const slugEl = document.getElementById("ob-slug");
  const yesQuote = document.getElementById("ob-yes-quote");
  const noQuote = document.getElementById("ob-no-quote");
  const yesTbody = document.querySelector("#ob-yes-table tbody");
  const noTbody = document.querySelector("#ob-no-table tbody");

  if (!ob || ob.error || !ob.yes || !ob.no) {
    if (slugEl) slugEl.textContent = ob ? (ob.slug || "") : "";
    if (yesQuote) yesQuote.textContent = "--";
    if (noQuote) noQuote.textContent = "--";
    if (yesTbody) yesTbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-dim)">no data</td></tr>';
    if (noTbody) noTbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--text-dim)">no data</td></tr>';
    return;
  }

  if (slugEl) slugEl.textContent = ob.slug || "";

  const fmtPx = (v) => v != null ? Number(v).toFixed(2) : "--";
  const fmtSz = (v) => v != null ? formatNumber(v, 0) : "--";

  if (yesQuote) {
    const bid = ob.yes.best_bid;
    const ask = ob.yes.best_ask;
    const spread = ob.yes.spread;
    yesQuote.innerHTML = `<span style="color:var(--ok)">${fmtPx(bid)}</span> / <span style="color:var(--bad)">${fmtPx(ask)}</span> <span style="font-size:0.62rem;color:var(--text-dim)">spd ${fmtPx(spread)}</span>`;
  }
  if (noQuote) {
    const bid = ob.no.best_bid;
    const ask = ob.no.best_ask;
    const spread = ob.no.spread;
    noQuote.innerHTML = `<span style="color:var(--ok)">${fmtPx(bid)}</span> / <span style="color:var(--bad)">${fmtPx(ask)}</span> <span style="font-size:0.62rem;color:var(--text-dim)">spd ${fmtPx(spread)}</span>`;
  }

  const renderBook = (tbody, book) => {
    const bids = book.bids || [];
    const asks = book.asks || [];
    const rows = Math.max(bids.length, asks.length, 1);
    let html = "";
    for (let i = 0; i < rows; i++) {
      const b = bids[i];
      const a = asks[i];
      html += `<tr>
        <td class="bid-cell mono">${b ? fmtPx(b.price) : ""}</td>
        <td class="mono">${b ? fmtSz(b.size) : ""}</td>
        <td class="ask-cell mono">${a ? fmtPx(a.price) : ""}</td>
        <td class="mono">${a ? fmtSz(a.size) : ""}</td>
      </tr>`;
    }
    tbody.innerHTML = html;
  };

  if (yesTbody) renderBook(yesTbody, ob.yes);
  if (noTbody) renderBook(noTbody, ob.no);
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

function getPmPositionSortValue(pos, key) {
  if (key === "title") return pos.title || "";
  if (key === "outcome") return pos.outcome || "";
  if (key === "status") return pos.status || "";
  if (key === "pnl_pct") {
    const init = Number(pos.initial_value || 0);
    const pnl = Number(pos.realized_pnl || 0) + Number(pos.unrealized_pnl || 0);
    return init > 0 ? pnl / init : 0;
  }
  return Number(pos[key] || 0);
}

function pmPositionCell(pos, key) {
  if (key === "title") return `<td>${pos.title || "-"}</td>`;
  if (key === "outcome") return `<td>${pos.outcome || "-"}</td>`;
  if (key === "status") {
    const cls = pos.status === "open" ? "pos" : pos.status === "closed" ? "neg" : "";
    return `<td class="${cls}">${pos.status || "-"}</td>`;
  }
  if (key === "size") return `<td>${Number(pos.size || 0).toFixed(2)}</td>`;
  if (key === "avg_price") return `<td>${Number(pos.avg_price || 0).toFixed(4)}</td>`;
  if (key === "initial_value") return `<td>$${formatNumber(pos.initial_value || 0)}</td>`;
  if (key === "current_value") return `<td>$${formatNumber(pos.current_value || 0)}</td>`;
  if (key === "realized_pnl") {
    const v = Number(pos.realized_pnl || 0);
    const cls = v > 0 ? "pos" : v < 0 ? "neg" : "";
    const sign = v >= 0 ? "+" : "-";
    return `<td class="${cls}">${sign}$${formatNumber(Math.abs(v))}</td>`;
  }
  if (key === "unrealized_pnl") {
    const v = Number(pos.unrealized_pnl || 0);
    const cls = v > 0 ? "pos" : v < 0 ? "neg" : "";
    const sign = v >= 0 ? "+" : "-";
    return `<td class="${cls}">${sign}$${formatNumber(Math.abs(v))}</td>`;
  }
  if (key === "pnl_pct") {
    const init = Number(pos.initial_value || 0);
    const pnl = Number(pos.realized_pnl || 0) + Number(pos.unrealized_pnl || 0);
    const pct = init > 0 ? (pnl / init) * 100 : 0;
    const cls = pct > 0 ? "pos" : pct < 0 ? "neg" : "";
    return `<td class="${cls}">${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%</td>`;
  }
  return "<td>-</td>";
}

function renderPmPositions() {
  const table = document.getElementById("pm-position-table");
  console.log("[renderPmPositions] table element:", table, "pmPositions count:", state.pmPositions.length, "statusFilter:", state.pmPositionStatusFilter);
  if (!table) return;
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");

  thead.innerHTML = `<tr>${PM_POSITION_COLUMNS
    .map((c) => {
      const active = state.pmPositionSort.key === c.key;
      const arrow = active ? (state.pmPositionSort.dir === "asc" ? "▲" : "▼") : "";
      return `<th class="sortable ${active ? "active" : ""}" data-pm-pos-sort-key="${c.key}">${c.label} <span class="sort-arrow">${arrow}</span></th>`;
    })
    .join("")}</tr>`;

  let filtered = [...state.pmPositions];
  if (state.pmPositionStatusFilter && state.pmPositionStatusFilter !== "all") {
    filtered = filtered.filter((p) => p.status === state.pmPositionStatusFilter);
  }

  const { key, dir } = state.pmPositionSort;
  filtered.sort((a, b) => {
    const va = getPmPositionSortValue(a, key);
    const vb = getPmPositionSortValue(b, key);
    const cmp = typeof va === "string" ? va.localeCompare(vb) : va - vb;
    return dir === "asc" ? cmp : -cmp;
  });

  tbody.innerHTML = filtered
    .map((p) => `<tr>${PM_POSITION_COLUMNS.map((c) => pmPositionCell(p, c.key)).join("")}</tr>`)
    .join("");

  thead.querySelectorAll("[data-pm-pos-sort-key]").forEach((th) => {
    th.addEventListener("click", () => {
      const k = th.dataset.pmPosSortKey;
      if (!k) return;
      if (state.pmPositionSort.key === k) state.pmPositionSort.dir = state.pmPositionSort.dir === "asc" ? "desc" : "asc";
      else {
        state.pmPositionSort.key = k;
        state.pmPositionSort.dir = "desc";
      }
      savePrefs();
      renderPmPositions();
    });
  });
}

function wirePmPositionControls() {
  const statusSelect = document.getElementById("pm-position-status-filter");
  if (statusSelect) {
    statusSelect.value = state.pmPositionStatusFilter;
    statusSelect.onchange = () => {
      state.pmPositionStatusFilter = statusSelect.value;
      savePrefs();
      renderPmPositions();
    };
  }
}

async function refreshPmPositions() {
  try {
    const data = await apiGet("/polymarket-positions", { status: "all", limit: 500, sort_by: "current_value", sort_dir: "desc" });
    state.pmPositions = data.items || [];
    renderPmPositions();
  } catch (err) {
    console.error("[refreshPmPositions] failed", err);
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
  const binEl = document.getElementById("binance-price");
  const clEl = document.getElementById("chainlink-price");
  const spreadEl = document.getElementById("spread-price");
  const slugEl = document.getElementById("market-slug");
  if (binEl) binEl.textContent = formatNumber(state.marketSummary.binance_price || 0);
  if (clEl) clEl.textContent = formatNumber(state.marketSummary.chainlink_price || 0);
  if (spreadEl) spreadEl.textContent = Number(state.marketSummary.spread || 0).toFixed(2);
  if (slugEl) slugEl.textContent = state.marketSummary.market_slug || "-";

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

function dualSparklineSvg(seriesA, seriesB, opts = {}) {
  const rows = [];
  for (let i = 0; i < Math.max(seriesA.length, seriesB.length); i += 1) {
    const a = seriesA[i];
    const b = seriesB[i];
    if (!a && !b) continue;
    rows.push({
      label: a?.label || b?.label || `point ${i + 1}`,
      a: a?.value,
      b: b?.value,
    });
  }
  if (!rows.length) return "";

  const padL = 32;  // left axis
  const padR = 4;
  const padT = 4;
  const padB = 2;
  const totalW = 420;
  const totalH = 84;
  const w = totalW - padL - padR;
  const h = totalH - padT - padB;
  const min = typeof opts.min === "number" ? opts.min : 0;
  const max = typeof opts.max === "number" ? opts.max : 1;
  const range = Math.max(max - min, 0.0001);
  const colorA = opts.colorA || "#7cc6fe";
  const colorB = opts.colorB || "#3ddc97";
  const toPoint = (value, idx) => {
    const x = padL + (idx / Math.max(rows.length - 1, 1)) * w;
    const y = padT + h - ((Math.min(max, Math.max(min, Number(value))) - min) / range) * h;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  };
  const polylineA = rows
    .map((row, idx) => (Number.isFinite(row.a) ? toPoint(row.a, idx) : null))
    .filter(Boolean)
    .join(" ");
  const polylineB = rows
    .map((row, idx) => (Number.isFinite(row.b) ? toPoint(row.b, idx) : null))
    .filter(Boolean)
    .join(" ");
  const circlesA = rows
    .map((row, idx) => {
      if (!Number.isFinite(row.a)) return "";
      const [cx, cy] = toPoint(row.a, idx).split(",");
      const tip = escapeXml(`${row.label}: p_up ${Number(row.a).toFixed(3)}`);
      return `<circle cx="${cx}" cy="${cy}" r="2.9" fill="${colorA}" fill-opacity="0.45"><title>${tip}</title></circle>`;
    })
    .join("");
  const circlesB = rows
    .map((row, idx) => {
      if (!Number.isFinite(row.b)) return "";
      const [cx, cy] = toPoint(row.b, idx).split(",");
      const tip = escapeXml(`${row.label}: up_px ${Number(row.b).toFixed(3)}`);
      return `<circle cx="${cx}" cy="${cy}" r="2.9" fill="${colorB}" fill-opacity="0.45"><title>${tip}</title></circle>`;
    })
    .join("");
  // Diff bars (p_up - UP price) drawn from the 0.5 baseline
  const barW = Math.max(2, (w / Math.max(rows.length, 1)) * 0.5);
  const midY = padT + h - ((0.5 - min) / range) * h;
  const diffBars = rows
    .map((row, idx) => {
      if (!Number.isFinite(row.a) || !Number.isFinite(row.b)) return "";
      const diff = row.a - row.b;
      const x = padL + (idx / Math.max(rows.length - 1, 1)) * w - barW / 2;
      const diffY = padT + h - ((Math.min(max, Math.max(min, 0.5 + diff)) - min) / range) * h;
      const barTop = Math.min(midY, diffY);
      const barH = Math.max(Math.abs(midY - diffY), 0.5);
      const barColor = diff >= 0 ? "#3ddc97" : "#ffd166";
      const tip = escapeXml(`${row.label}: diff ${diff >= 0 ? "+" : ""}${diff.toFixed(3)}`);
      return `<rect x="${x.toFixed(2)}" y="${barTop.toFixed(2)}" width="${barW.toFixed(2)}" height="${barH.toFixed(2)}" fill="${barColor}" fill-opacity="0.35"><title>${tip}</title></rect>`;
    })
    .join("");
  // Grid lines (0.25, 0.50, 0.75)
  const grid = [0.25, 0.5, 0.75]
    .map((ratio) => {
      const y = padT + h - ratio * h;
      return `<line x1="${padL}" y1="${y.toFixed(2)}" x2="${padL + w}" y2="${y.toFixed(2)}" stroke="#3f4a53" stroke-width="1" stroke-dasharray="4 4" />`;
    })
    .join("");
  // Shared axis labels (0-1 scale for both prob and price)
  const axisLabels = [0, 0.25, 0.5, 0.75, 1.0]
    .map((v) => {
      const y = padT + h - ((v - min) / range) * h;
      return `<text x="${padL - 3}" y="${y.toFixed(2)}" fill="#8b949e" font-size="7" text-anchor="end" dominant-baseline="middle">${v.toFixed(2)}</text>`;
    })
    .join("");
  return `
    <svg viewBox="0 0 ${totalW} ${totalH}" preserveAspectRatio="xMidYMid meet" width="100%" height="100%">
      ${grid}
      ${axisLabels}
      ${diffBars}
      <polyline fill="none" stroke="${colorA}" stroke-width="2.2" points="${polylineA}" />
      <polyline fill="none" stroke="${colorB}" stroke-width="2.2" points="${polylineB}" />
      ${circlesA}
      ${circlesB}
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
  const svc = state.services.find((s) => s.name === key);
  const obAsset = (svc && svc.asset) ? svc.asset : (key.startsWith("eth") ? "ETH" : "BTC");
  const [detail, decisions, runtime, orderbook] = await Promise.all([
    apiGet(`/services/${key}`).catch(() => null),
    apiGet(`/services/${key}/decisions`, { limit: 50 }).catch(() => ({ items: [] })),
    apiGet(`/services/${key}/runtime-signals`, { limit: 50 }).catch(() => ({ items: [] })),
    apiGet("/market/orderbook", { asset: obAsset }).catch(() => null),
  ]);
  state.orderbook = orderbook;

  if (detail && detail.service) {
    const s = asUiService(detail.service);
    const idx = state.services.findIndex((x) => x.name === key);
    if (idx >= 0) state.services[idx] = { ...state.services[idx], ...s };
    state.serviceHealthByKey[key] = detail.health || {};
    state.serviceControlsByKey[key] = detail.controls || {};
  }
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
    marketPrice: d.market_price == null ? null : Number(d.market_price),
    upPrice: isContractPrice(d.market_price) ? Number(d.market_price) : null,
    binancePrice: d.binance_price == null ? null : Number(d.binance_price),
    binanceChange5m: d.binance_price_change_5m == null ? null : Number(d.binance_price_change_5m),
    dangerAdx: d.danger_f_adx_3m == null ? null : Number(d.danger_f_adx_3m),
    dangerSpread: d.danger_f_spread_3m == null ? null : Number(d.danger_f_spread_3m),
    dangerEr: d.danger_f_er_3m == null ? null : Number(d.danger_f_er_3m),
  }));
  const runtimeRows = (runtime.items || []).map((r) => ({
    ts: formatEtDateTime(r.ts),
    pUp: r.p_up == null ? null : Number(r.p_up),
    binance: Number(r.binance_price || 0),
    chainlink: Number(r.chainlink_price || 0),
    pmMid: (r.pm_mid == null || r.pm_mid === 0) ? null : Number(r.pm_mid),
    pmBid: (r.pm_bid == null || r.pm_bid === 0) ? null : Number(r.pm_bid),
    pmAsk: (r.pm_ask == null || r.pm_ask === 0) ? null : Number(r.pm_ask),
    clBinSpread: Number(r.cl_bin_spread || 0),
    bucketLeft: Number(r.bucket_seconds_left || 0),
    ingestLag: Number(r.ingest_lag_ms || 0),
    streak: `${r.streak_hits || 0}/${r.streak_target || 0}`,
    binanceChange5m: r.binance_price_change_5m == null ? null : Number(r.binance_price_change_5m),
    dangerAdx: r.danger_f_adx_3m == null ? null : Number(r.danger_f_adx_3m),
    dangerSpread: r.danger_f_spread_3m == null ? null : Number(r.danger_f_spread_3m),
    dangerEr: r.danger_f_er_3m == null ? null : Number(r.danger_f_er_3m),
  }));
  state.liveRowsByService[key] = runtimeRows;
  state.latestRuntimeByService[key] = runtimeRows[0] || {};
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

// ---------------------------------------------------------------------------
// Market Interaction
// ---------------------------------------------------------------------------

state.miPositions = [];
state.miTradingEnabled = false;
state.miPlaceBusy = false;

async function refreshMiTradingStatus() {
  try {
    const data = await apiGet("/trading/status").catch(() => ({ enabled: false }));
    state.miTradingEnabled = Boolean(data.enabled);
  } catch (_err) {
    state.miTradingEnabled = false;
  }
}

async function refreshMiPositions() {
  try {
    const data = await apiGet("/polymarket-positions", { status: "open", limit: 200, sort_by: "current_value", sort_dir: "desc" }).catch(() => ({ items: [] }));
    state.miPositions = data.items || [];
  } catch (_err) {
    state.miPositions = [];
  }
}

function renderMiPositions() {
  const tbody = document.querySelector("#mi-positions-table tbody");
  if (!tbody) return;
  if (state.miPositions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-dim)">no open positions</td></tr>';
    return;
  }
  tbody.innerHTML = state.miPositions
    .map((p) => {
      const pnl = Number(p.unrealized_pnl || 0);
      const pnlCls = pnl >= 0 ? "pos" : "warn";
      const tokenId = p.token_id || p.condition_id || "";
      const canClose = state.miTradingEnabled && tokenId && Number(p.size || 0) > 0;
      return `
        <tr>
          <td title="${p.slug || ""}">${p.title || p.slug || "-"}</td>
          <td>${p.outcome || "-"}</td>
          <td>${Number(p.size || 0).toFixed(2)}</td>
          <td>${Number(p.avg_price || 0).toFixed(4)}</td>
          <td>$${formatNumber(p.current_value || 0)}</td>
          <td class="${pnlCls}">${pnl >= 0 ? "+" : ""}$${formatNumber(pnl)}</td>
          <td>${canClose ? `<button class="tiny-btn mi-close-btn" data-token="${tokenId}" data-size="${p.size}" data-price="${p.avg_price}">Close</button>` : ""}</td>
        </tr>`;
    })
    .join("");

  tbody.querySelectorAll(".mi-close-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const tokenId = btn.dataset.token;
      const size = Number(btn.dataset.size);
      const price = Number(btn.dataset.price);
      if (!tokenId || !size) return;
      btn.disabled = true;
      btn.textContent = "Closing...";
      try {
        await apiPost("/trading/close-position", { token_id: tokenId, size, price });
        btn.textContent = "Sent";
        setTimeout(() => refreshMiPositions().then(renderMiPositions), 2000);
      } catch (err) {
        btn.textContent = "Failed";
        console.error("close position failed", err);
      }
    });
  });
}

function wireMiPlaceOrder() {
  const placeBtn = document.getElementById("mi-place-btn");
  const statusEl = document.getElementById("mi-place-status");
  if (!placeBtn) return;

  placeBtn.onclick = async () => {
    const tokenId = (document.getElementById("mi-token-id")?.value || "").trim();
    const side = document.getElementById("mi-side")?.value || "BUY";
    const price = parseFloat(document.getElementById("mi-price")?.value);
    const size = parseFloat(document.getElementById("mi-size")?.value);

    if (!tokenId) { statusEl.textContent = "need token ID"; statusEl.className = "chip bad"; return; }
    if (!Number.isFinite(price) || price <= 0 || price >= 1) { statusEl.textContent = "price 0-1"; statusEl.className = "chip bad"; return; }
    if (!Number.isFinite(size) || size <= 0) { statusEl.textContent = "need size"; statusEl.className = "chip bad"; return; }

    state.miPlaceBusy = true;
    placeBtn.disabled = true;
    statusEl.textContent = "placing...";
    statusEl.className = "chip warn";

    try {
      const result = await apiPost("/trading/place-order", { token_id: tokenId, side, price, size });
      statusEl.textContent = "order placed";
      statusEl.className = "chip ok";
    } catch (err) {
      statusEl.textContent = `failed: ${err.message}`;
      statusEl.className = "chip bad";
      console.error("place order failed", err);
    } finally {
      state.miPlaceBusy = false;
      placeBtn.disabled = false;
    }
  };
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
  wirePmPositionControls();
  renderOverview();
  renderServiceDetail();
  renderMiPositions();
  renderTrades();
  renderPmTrades();
  renderPmPositions();
  renderPriceMonitor();
  renderLogs();
}

async function refreshActivePage() {
  if (state.activePage === "overview") await refreshOverviewData();
  if (state.activePage === "services") {
    await refreshServiceDetailData();
    await refreshMiPositions();
  }
  if (state.activePage === "monitor") {
    await Promise.all([refreshMarket(), refreshServiceDetailData()]);
  }
  if (state.activePage === "trades") await refreshTrades();
  if (state.activePage === "pm-trades") {
    await refreshPmTrades();
    await refreshPmPositions();
  }
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
    refreshPmPositions(),
    refreshLogs(),
    refreshMarket(),
  ]);
  // Non-critical — don't let these block or break initial load
  refreshMiTradingStatus().catch(() => {});
  refreshMiPositions().catch(() => {});
}

async function init() {
  restorePrefs();
  wireNav();
  wireServiceActions();
  wireMiPlaceOrder();
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
