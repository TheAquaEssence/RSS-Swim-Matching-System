/* === XAI Dashboard v2 === */

// ==================== STATE ====================
const state = {
  view: 'overview',         // 'overview' | 'explorer'
  matches: [],               // all matches from API
  unassigned: [],             // unassigned swimmers
  summary: {},                // summary stats
  explorerMode: 'table',     // 'table' | 'cards'
  filters: { search: '', type: '', format: '', flaggedOnly: false },
  sortCol: 'idx',
  sortAsc: true,
  selectedMatchIdx: null,     // index of match shown in detail panel
};

const charts = {};  // Chart.js instances keyed by name
let _currentMatchData = null;  // stored for audit modal
let _lastFocusedElement = null;
let _lastAuditFocusedElement = null;

const cache = {
  overview: null,        // cached overview API response
  overviewAt: 0,         // timestamp (ms) when overview was cached
  alternatives: {},      // keyed by match idx → cached alternatives response
};
const OVERVIEW_TTL_MS = 30_000;  // 30 seconds
const THEME_KEY = 'aqua_theme';

function applyDashboardTheme(theme) {
  const resolved = theme === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = resolved;
  const button = document.getElementById('xai-theme-toggle');
  if (button) {
    const nextTheme = resolved === 'dark' ? 'light' : 'dark';
    button.textContent = `${nextTheme[0].toUpperCase()}${nextTheme.slice(1)} mode`;
    button.setAttribute('aria-label', `Switch to ${nextTheme} mode`);
  }
  updateChartTheme(resolved);
}

function loadDashboardTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === 'light' || saved === 'dark') return saved;
  return window.matchMedia?.('(prefers-color-scheme: light)')?.matches ? 'light' : 'dark';
}

function updateChartTheme(theme) {
  const isLight = theme === 'light';
  Chart.defaults.color = isLight ? '#556070' : '#a6b0c3';
  Chart.defaults.borderColor = isLight ? 'rgba(20, 24, 33, 0.12)' : 'rgba(255, 255, 255, 0.1)';
  Object.values(charts).forEach(chart => chart.update('none'));
}

applyDashboardTheme(loadDashboardTheme());

// ==================== CHART DEFAULTS ====================
const escapeHtml = window.AquaUi.escapeHtml;
const normalizeConfidence = window.AquaUi.normalizeConfidence;
const FLAG_TITLE_OVERRIDES = {
  non_response_swimmer_type: 'Default swimmer type used',
  default_instructor_profile: 'Default instructor profile used',
};

function resolveFlagTitle(code, fallbackTitle) {
  if (code && FLAG_TITLE_OVERRIDES[code]) return FLAG_TITLE_OVERRIDES[code];
  return fallbackTitle || code || 'Review flag';
}

// ==================== ERROR DISPLAY ====================
function showError(message) {
  let banner = document.getElementById('error-banner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'error-banner';
    banner.style.cssText = 'position:fixed;top:0;left:0;right:0;padding:12px 20px;background:#dc2626;color:#fff;z-index:9999;text-align:center;font-weight:500;cursor:pointer;';
    banner.title = 'Click to dismiss';
    banner.onclick = () => banner.remove();
    document.body.prepend(banner);
  }
  banner.textContent = message;
  setTimeout(() => { if (banner.parentNode) banner.remove(); }, 8000);
}

function showLoading(container) {
  if (!container) return;
  const overlay = document.createElement('div');
  overlay.className = 'loading-overlay';
  overlay.innerHTML = '<div class="loading-spinner"></div>';
  container.style.position = 'relative';
  container.appendChild(overlay);
}

function hideLoading(container) {
  if (!container) return;
  container.querySelectorAll('.loading-overlay').forEach(el => el.remove());
}

function invalidateOverviewState() {
  cache.overview = null;
  cache.overviewAt = 0;
  cache.alternatives = {};
}

// ==================== API HELPERS ====================
async function api(path) {
  const resp = await fetch(path, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`API ${path} returned ${resp.status}`);
  return resp.json();
}

async function apiPost(path, body) {
  const resp = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`API ${path} returned ${resp.status}`);
  return resp.json();
}

// ==================== CHART HELPERS ====================
function destroyChart(key) {
  if (charts[key]) { charts[key].destroy(); delete charts[key]; }
}

function confidenceColor(conf) {
  if (conf >= 75) return '#4ade80';
  if (conf >= 50) return '#fbbf24';
  return '#ef4444';
}

function personName(obj) {
  if (!obj) return null;
  if (obj.first_name || obj.last_name) return `${obj.first_name || ''} ${obj.last_name || ''}`.trim();
  return obj.name || null;
}

function getSwimmerLabel(match) {
  if (match.type === 'pair') {
    const s1 = match.swimmer_1_name || personName(match.swimmer_1) || match.swimmer_1_id;
    const s2 = match.swimmer_2_name || personName(match.swimmer_2) || match.swimmer_2_id;
    return `${s1} & ${s2}`;
  }
  return match.swimmer_name || personName(match.swimmer) || match.swimmer_id || '—';
}

function hasReviewFlags(match) {
  if (!match) return false;
  if (Array.isArray(match.flags) && match.flags.length > 0) return true;
  if (Array.isArray(match.flag_codes) && match.flag_codes.length > 0) return true;
  const severity = String(match.review_severity || '').toLowerCase();
  if (severity && severity !== 'none') return true;
  const conf = normalizeConfidence(match.confidence);
  return (conf != null && conf < 50) || Boolean(match.continuity_dispute);
}

function getReviewFlags(match) {
  if (!match) return [];
  if (Array.isArray(match.flags) && match.flags.length > 0) {
    return match.flags.map(flag => ({
      code: flag.code || '',
      title: resolveFlagTitle(flag.code || '', flag.title || ''),
      description: flag.description || '',
      severity: String(flag.severity || match.review_severity || 'review').toLowerCase(),
      reviewAction: flag.review_action_label || flag.review_action || match.review_action || '',
    }));
  }
  if (Array.isArray(match.flag_codes) && match.flag_codes.length > 0) {
    return match.flag_codes.map(code => ({
      code,
      title: resolveFlagTitle(
        code,
        String(code || 'Review flag')
          .replace(/_/g, ' ')
          .replace(/\b\w/g, c => c.toUpperCase())
      ),
      description: match.flag_summary || '',
      severity: String(match.review_severity || 'review').toLowerCase(),
      reviewAction: match.review_action || '',
    }));
  }
  return [];
}

function getFlagReasonText(match) {
  const reasons = [];
  const conf = normalizeConfidence(match?.confidence);
  if (conf != null && conf < 50) reasons.push('Low confidence');
  if (match?.continuity_dispute) reasons.push('Continuity dispute');
  getReviewFlags(match).forEach(flag => {
    if (flag.title && !reasons.includes(flag.title)) reasons.push(flag.title);
  });
  if (reasons.length === 0 && match?.flag_summary) reasons.push(match.flag_summary);
  return reasons.join(', ');
}

function collectFlaggedMatches(matches, fallbackFlagged = []) {
  const byIdx = new Map();

  fallbackFlagged.forEach(item => {
    if (item && Number.isInteger(item.idx)) byIdx.set(item.idx, item);
  });

  matches.forEach((match, idx) => {
    if (!hasReviewFlags(match)) return;
    const conf = normalizeConfidence(match.confidence);
    byIdx.set(idx, {
      idx,
      swimmer_name: getSwimmerLabel(match),
      instructor_name: match.instructor_name || match.instructor_id || '—',
      confidence: conf != null ? Number(conf.toFixed(1)) : 0,
      flag_reason: getFlagReasonText(match) || 'Review flag',
      review_severity: String(match.review_severity || '').toLowerCase() || 'review',
    });
  });

  return [...byIdx.values()].sort((a, b) => a.idx - b.idx);
}

function renderDetailFlags(match) {
  const flagsSection = document.getElementById('detail-flags');
  const flagsList = document.getElementById('detail-flags-list');
  if (!flagsSection || !flagsList) return;

  const flags = getReviewFlags(match);
  flagsList.innerHTML = '';
  if (flags.length === 0) {
    flagsSection.classList.add('hidden');
    return;
  }

  flags.forEach(flag => {
    const severity = flag.severity || 'review';
    const card = document.createElement('div');
    card.className = `detail-flag-card flag-${severity}`;
    card.innerHTML = `
      <div class="detail-flag-header">
        <div class="detail-flag-title">${escapeHtml(flag.title || 'Review flag')}</div>
        <div class="detail-flag-severity">${escapeHtml(severity)}</div>
      </div>
      ${flag.description ? `<div class="detail-flag-description">${escapeHtml(flag.description)}</div>` : ''}
      ${flag.reviewAction ? `<div class="detail-flag-action">Action: ${escapeHtml(flag.reviewAction)}</div>` : ''}
      ${flag.code ? `<div class="detail-flag-code">${escapeHtml(flag.code)}</div>` : ''}
    `;
    flagsList.appendChild(card);
  });

  flagsSection.classList.remove('hidden');
}

// ==================== NAVIGATION ====================
function showView(viewId) {
  document.querySelectorAll('main > section').forEach(s => s.classList.add('hidden'));
  const target = document.getElementById('view-' + viewId);
  if (target) target.classList.remove('hidden');

  document.querySelectorAll('.tab').forEach(t => {
    t.classList.remove('active');
    t.setAttribute('aria-selected', 'false');
  });
  const tab = document.querySelector(`.tab[data-view="${viewId}"]`);
  if (tab) {
    tab.classList.add('active');
    tab.setAttribute('aria-selected', 'true');
  }

  state.view = viewId;
  history.replaceState(null, '', `#${viewId}`);

  if (viewId === 'overview') void loadOverview();
  if (viewId === 'explorer') {
    if (state.matches.length === 0) void loadOverview().then(() => renderExplorer());
    else renderExplorer();
  }
}

function openDetailPanel(idx) {
  _lastFocusedElement = document.activeElement;
  state.selectedMatchIdx = idx;
  document.getElementById('detail-panel').classList.remove('hidden');
  document.getElementById('panel-backdrop').classList.remove('hidden');
  document.getElementById('btn-close-panel').focus();
  loadMatchDetail(idx);
}

function closeDetailPanel() {
  state.selectedMatchIdx = null;
  document.getElementById('detail-panel').classList.add('hidden');
  document.getElementById('panel-backdrop').classList.add('hidden');
  destroyChart('breakdown');
  destroyChart('alternatives');
  if (_lastFocusedElement instanceof HTMLElement) _lastFocusedElement.focus();
  _lastFocusedElement = null;
}

// ==================== HEARTBEAT ====================
// Keep the FastAPI server alive while the XAI dashboard is open.
// Without this, the server's 120-second watchdog kills the process because
// heartbeats only came from app.js (which is not loaded on /xai/ pages).
async function sendXaiHeartbeat() {
  try {
    await fetch('/api/heartbeat', { method: 'POST', cache: 'no-store' });
  } catch {
    // ignore — server may not be up yet
  }
}

// ==================== INIT ====================
document.addEventListener('DOMContentLoaded', () => {
  applyDashboardTheme(loadDashboardTheme());
  document.getElementById('xai-theme-toggle').onclick = () => {
    const current = document.documentElement.dataset.theme || 'dark';
    const next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem(THEME_KEY, next);
    applyDashboardTheme(next);
  };

  // Heartbeat: fire immediately then every 10 s
  void sendXaiHeartbeat();
  setInterval(() => void sendXaiHeartbeat(), 10000);

  // Tab navigation
  document.querySelectorAll('.tab').forEach(tab => {
    tab.onclick = () => showView(tab.dataset.view);
  });

  document.getElementById('btn-review-all').onclick = () => {
    clearExplorerFilters();
    showView('explorer');
  };
  document.getElementById('btn-review-flagged').onclick = () => {
    clearExplorerFilters();
    state.filters.flaggedOnly = true;
    syncExplorerControls();
    showView('explorer');
  };

  // Close detail panel
  document.getElementById('btn-close-panel').onclick = closeDetailPanel;
  document.getElementById('panel-backdrop').onclick = closeDetailPanel;

  // Close audit modal
  document.getElementById('btn-close-audit').onclick = closeAuditModal;
  document.getElementById('audit-backdrop').onclick = closeAuditModal;

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      const auditIsOpen = !document.getElementById('audit-modal').classList.contains('hidden');
      if (auditIsOpen) closeAuditModal();
      else closeDetailPanel();
    }
  });

  // Reload button
  document.getElementById('btn-reload').onclick = async () => {
    await apiPost('/xai/api/reload', {});
    invalidateOverviewState();
    await loadOverview();
    if (state.view === 'explorer') renderExplorer();
  };

  // Filter inputs (wired in explorer section)
  wireExplorerFilters();

  // Load the requested review surface while keeping data fresh.
  showView(location.hash === '#explorer' ? 'explorer' : 'overview');
});

window.addEventListener('pageshow', () => {
  invalidateOverviewState();
  void loadOverview();
});

document.addEventListener('visibilitychange', () => {
  if (document.hidden) return;
  invalidateOverviewState();
  void loadOverview();
});

// ==================== OVERVIEW ====================
async function loadOverview() {
  const container = document.getElementById('view-overview');
  showLoading(container);
  try {
    const data = await api('/xai/api/overview');
    if (!data.ok) return;
    cache.overview = data;
    cache.overviewAt = Date.now();
    // Also load matches (not cached — fresh on every overview load)
    const matchData = await api('/xai/api/matches');
    if (matchData.ok) {
      state.matches = matchData.matches || [];
      state.unassigned = matchData.unassigned || [];
    }
    _renderOverview(data);
    buildFlaggedTable(collectFlaggedMatches(state.matches, data.flagged || []));
  } catch (err) {
    console.error('Failed to load overview:', err);
    showError('Failed to load overview data — is the server running?');
  } finally {
    hideLoading(container);
  }
}

function _renderOverview(data) {
  state.summary = data.summary || {};

  // Summary cards
  const s = data.summary || {};
  document.getElementById('stat-assigned').textContent = s.assigned_swimmers ?? '—';
  document.getElementById('stat-unassigned').textContent = s.unassigned_swimmers ?? '—';
  document.getElementById('stat-confidence').textContent =
    s.avg_confidence != null ? Number(s.avg_confidence).toFixed(1) + '%' : '—';
  document.getElementById('stat-classes').textContent = s.classes ?? '—';

  // Confidence histogram
  buildConfidenceChart(data.confidence_distribution);

  // Type breakdown doughnut
  buildTypeChart(data.type_breakdown);
}

function buildConfidenceChart(dist) {
  if (!dist) return;
  const ctx = document.getElementById('chart-confidence');
  destroyChart('confidence');

  // Filter to non-empty buckets only — avoids ghost zero-bars
  const filtered = dist.buckets
    .map((label, i) => ({ label, count: dist.counts[i] }))
    .filter(b => b.count > 0);

  const bucketColor = (label) => {
    const lower = parseInt(label.split('-')[0], 10);
    if (lower < 50) return '#ef4444';   // 0-49: red
    if (lower < 70) return '#fbbf24';   // 50-69: yellow
    return '#4ade80';                    // 70-100: green
  };

  charts.confidence = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: filtered.map(b => b.label),
      datasets: [{
        label: 'Matches',
        data: filtered.map(b => b.count),
        backgroundColor: filtered.map(b => bucketColor(b.label)),
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { title: { display: true, text: 'Confidence Range' } },
        y: { title: { display: true, text: 'Count' }, beginAtZero: true, ticks: { precision: 0 } }
      }
    }
  });
}

function buildTypeChart(breakdown) {
  if (!breakdown) return;
  const ctx = document.getElementById('chart-types');
  destroyChart('types');

  const VIEWS = {
    match_type: {
      labels: ['Pre-assigned', 'Continuity', 'Compatibility'],
      data: [breakdown['pre-assigned'] || 0, breakdown.continuity, breakdown.compatibility],
      colors: ['#f59e0b', '#3b82f6', '#a855f7'],
    },
    format: {
      labels: ['Individual', 'Pair'],
      data: [breakdown.individual, breakdown.pair],
      colors: ['#06b6d4', '#f97316'],
    },
  };

  const activeView = () => {
    const sel = document.getElementById('chart-types-dim');
    return VIEWS[sel ? sel.value : 'match_type'];
  };

  const initial = activeView();
  charts.types = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: initial.labels,
      datasets: [{ data: initial.data, backgroundColor: initial.colors }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' } },
    },
  });

  // Wire dropdown — swap data in-place, no chart rebuild
  const chart = charts.types;
  const sel = document.getElementById('chart-types-dim');
  if (sel) {
    sel.onchange = () => {
      const v = activeView();
      chart.data.labels = v.labels;
      chart.data.datasets[0].data = v.data;
      chart.data.datasets[0].backgroundColor = v.colors;
      chart.update();
    };
  }
}

function buildFlaggedTable(flagged) {
  const tbody = document.querySelector('#flagged-table tbody');
  const emptyMsg = document.getElementById('flagged-empty');
  const badge = document.getElementById('flagged-count');
  const reviewButton = document.getElementById('btn-review-flagged');

  tbody.innerHTML = '';
  badge.textContent = flagged.length;
  reviewButton.disabled = flagged.length === 0;
  reviewButton.setAttribute('aria-disabled', flagged.length === 0 ? 'true' : 'false');

  if (flagged.length === 0) {
    emptyMsg.style.display = '';
    document.getElementById('flagged-table').style.display = 'none';
    return;
  }
  emptyMsg.style.display = 'none';
  document.getElementById('flagged-table').style.display = '';

  flagged.forEach(f => {
    const tr = document.createElement('tr');
    tr.className = 'clickable-row';
    tr.onclick = () => openDetailPanel(f.idx);
    tr.tabIndex = 0;
    tr.setAttribute('role', 'button');
    tr.setAttribute('aria-label', `Review ${f.swimmer_name} matched with ${f.instructor_name}`);
    tr.onkeydown = event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openDetailPanel(f.idx);
      }
    };
    const conf = f.confidence;
    tr.innerHTML = `
      <td>${escapeHtml(f.swimmer_name)}</td>
      <td>${escapeHtml(f.instructor_name)}</td>
      <td><span class="conf-pill" style="background:${confidenceColor(conf)}">${conf.toFixed(1)}</span></td>
      <td>${escapeHtml(f.flag_reason)}</td>
    `;
    tbody.appendChild(tr);
  });
}

// ==================== MATCH EXPLORER ====================
function syncExplorerControls() {
  document.getElementById('filter-search').value = state.filters.search;
  document.getElementById('filter-type').value = state.filters.type;
  document.getElementById('filter-format').value = state.filters.format;
  document.getElementById('filter-flagged').checked = state.filters.flaggedOnly;
}

function clearExplorerFilters() {
  state.filters = { search: '', type: '', format: '', flaggedOnly: false };
  syncExplorerControls();
}

function wireExplorerFilters() {
  const search = document.getElementById('filter-search');
  const type = document.getElementById('filter-type');
  const format = document.getElementById('filter-format');
  const flagged = document.getElementById('filter-flagged');

  const update = () => {
    state.filters.search = search.value.toLowerCase();
    state.filters.type = type.value;
    state.filters.format = format.value;
    state.filters.flaggedOnly = flagged.checked;
    renderExplorer();
  };

  search.oninput = update;
  type.onchange = update;
  format.onchange = update;
  flagged.onchange = update;
  document.getElementById('btn-clear-filters').onclick = () => {
    clearExplorerFilters();
    renderExplorer();
    search.focus();
  };

  // View toggle
  document.querySelectorAll('.toggle-btn').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('.toggle-btn').forEach(b => {
        b.classList.remove('active');
        b.setAttribute('aria-pressed', 'false');
      });
      btn.classList.add('active');
      btn.setAttribute('aria-pressed', 'true');
      state.explorerMode = btn.dataset.mode;
      renderExplorer();
    };
  });

  // Sortable columns
  document.querySelectorAll('.sortable').forEach(th => {
    th.tabIndex = 0;
    const changeSort = () => {
      const col = th.dataset.sort;
      if (state.sortCol === col) {
        state.sortAsc = !state.sortAsc;
      } else {
        state.sortCol = col;
        state.sortAsc = true;
      }
      renderExplorer();
    };
    th.onclick = changeSort;
    th.onkeydown = event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        changeSort();
      }
    };
  });
}

function getFilteredMatches() {
  let matches = state.matches.map((m, i) => ({ ...m, _idx: i }));
  const f = state.filters;

  if (f.search) {
    matches = matches.filter(m => {
      const label = getSwimmerLabel(m).toLowerCase();
      const instr = (m.instructor_name || '').toLowerCase();
      return label.includes(f.search) || instr.includes(f.search);
    });
  }

  if (f.type) {
    matches = matches.filter(m => (m.match_type || 'compatibility') === f.type);
  }

  if (f.format) {
    matches = matches.filter(m => (m.type || 'individual') === f.format);
  }

  if (f.flaggedOnly) {
    matches = matches.filter(m => hasReviewFlags(m));
  }

  // Sort
  matches.sort((a, b) => {
    let va, vb;
    switch (state.sortCol) {
      case 'idx': va = a._idx; vb = b._idx; break;
      case 'swimmer': va = getSwimmerLabel(a); vb = getSwimmerLabel(b); break;
      case 'instructor': va = a.instructor_name || ''; vb = b.instructor_name || ''; break;
      case 'type': va = a.match_type || ''; vb = b.match_type || ''; break;
      case 'confidence': va = normalizeConfidence(a.confidence) || 0; vb = normalizeConfidence(b.confidence) || 0; break;
      default: va = a._idx; vb = b._idx;
    }
    if (typeof va === 'string') { va = va.toLowerCase(); vb = vb.toLowerCase(); }
    if (va < vb) return state.sortAsc ? -1 : 1;
    if (va > vb) return state.sortAsc ? 1 : -1;
    return 0;
  });

  return matches;
}

function renderExplorer() {
  const matches = getFilteredMatches();
  const tableView = document.getElementById('explorer-table-view');
  const cardView = document.getElementById('explorer-card-view');
  const emptyMsg = document.getElementById('explorer-empty');
  const count = document.getElementById('explorer-result-count');
  count.textContent = matches.length === state.matches.length
    ? `${matches.length} decision${matches.length === 1 ? '' : 's'}`
    : `${matches.length} of ${state.matches.length} decisions`;

  if (matches.length === 0) {
    tableView.classList.add('hidden');
    cardView.classList.add('hidden');
    emptyMsg.classList.remove('hidden');
    return;
  }
  emptyMsg.classList.add('hidden');

  if (state.explorerMode === 'table') {
    tableView.classList.remove('hidden');
    cardView.classList.add('hidden');
    renderExplorerTable(matches);
  } else {
    tableView.classList.add('hidden');
    cardView.classList.remove('hidden');
    renderExplorerCards(matches);
  }

  // Update sort indicators
  document.querySelectorAll('.sortable').forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    th.setAttribute('aria-sort', 'none');
    if (th.dataset.sort === state.sortCol) {
      th.classList.add(state.sortAsc ? 'sort-asc' : 'sort-desc');
      th.setAttribute('aria-sort', state.sortAsc ? 'ascending' : 'descending');
    }
  });
}

function renderExplorerTable(matches) {
  const tbody = document.querySelector('#explorer-table tbody');
  tbody.innerHTML = '';

  matches.forEach(m => {
    const tr = document.createElement('tr');
    tr.className = 'clickable-row';
    tr.onclick = () => openDetailPanel(m._idx);
    tr.tabIndex = 0;
    tr.setAttribute('role', 'button');
    tr.setAttribute('aria-label', `Inspect ${getSwimmerLabel(m)} matched with ${m.instructor_name || m.instructor_id || 'instructor'}`);
    tr.onkeydown = event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openDetailPanel(m._idx);
      }
    };

    const conf = normalizeConfidence(m.confidence);
    const matchType = m.match_type || 'compatibility';
    const typeBadgeClass = matchType === 'continuity'
      ? 'badge-continuity'
      : (matchType === 'pre-assigned' ? 'badge-pre-assigned' : 'badge-compatibility');

    tr.innerHTML = `
      <td>${m._idx}</td>
      <td>${escapeHtml(getSwimmerLabel(m))}</td>
      <td>${escapeHtml(m.instructor_name || m.instructor_id || '—')}</td>
      <td><span class="type-badge ${escapeHtml(typeBadgeClass)}">${escapeHtml(matchType)}</span></td>
      <td><span class="conf-pill" style="background:${confidenceColor(conf || 0)}">${conf != null ? conf.toFixed(1) : '—'}</span></td>
      <td class="reason-cell">${escapeHtml(m.reason_summary || m.reason || '—')}</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderExplorerCards(matches) {
  const container = document.getElementById('explorer-card-view');
  container.innerHTML = '';

  matches.forEach(m => {
    const conf = normalizeConfidence(m.confidence) || 0;
    const matchType = m.match_type || 'compatibility';
    const borderColor = confidenceColor(conf);

    const card = document.createElement('div');
    card.className = 'match-card';
    card.style.borderLeftColor = borderColor;
    card.onclick = () => openDetailPanel(m._idx);
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    card.setAttribute('aria-label', `Inspect ${getSwimmerLabel(m)} matched with ${m.instructor_name || 'instructor'}`);
    card.onkeydown = event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openDetailPanel(m._idx);
      }
    };

    card.innerHTML = `
      <div class="card-header">
        <span class="conf-pill" style="background:${borderColor}">${conf.toFixed(1)}</span>
        <span class="type-badge badge-${escapeHtml(matchType)}">${escapeHtml(matchType)}</span>
      </div>
      <div class="card-body">
        <div class="card-swimmer">${escapeHtml(getSwimmerLabel(m))}</div>
        <div class="card-arrow">↓</div>
        <div class="card-instructor">${escapeHtml(m.instructor_name || '—')}</div>
      </div>
      <div class="card-footer">${escapeHtml(m.reason_summary || m.reason || '')}</div>
    `;
    container.appendChild(card);
  });
}

// ==================== MATCH DETAIL ====================
async function loadMatchDetail(idx) {
  try {
    // Fetch match detail + alternatives in parallel (alternatives are cached by idx)
    const detailPromise = api(`/xai/api/match/${idx}`);
    const altPromise = cache.alternatives[idx]
      ? Promise.resolve(cache.alternatives[idx])
      : api(`/xai/api/match/${idx}/alternatives`).then(r => {
          if (r.ok) cache.alternatives[idx] = r;
          return r;
        }).catch(() => ({ ok: false, alternatives: [] }));
    const [detailData, altData] = await Promise.all([detailPromise, altPromise]);

    if (!detailData.ok) return;

    const match = detailData.match;
    const breakdown = detailData.breakdown;
    const conf = normalizeConfidence(match.confidence) || 0;
    const matchType = match.match_type || 'compatibility';

    // Layer 1: Summary
    const badge = document.getElementById('detail-confidence');
    badge.textContent = conf.toFixed(1);
    badge.style.background = confidenceColor(conf);

    const typeBadge = document.getElementById('detail-type-badge');
    typeBadge.textContent = matchType;
    typeBadge.className = 'match-type-badge badge-' + matchType;

    document.getElementById('detail-swimmer-name').textContent = getSwimmerLabel(match);
    document.getElementById('detail-instructor-name').textContent =
      match.instructor_name || match.instructor_id || '—';
    document.getElementById('detail-reason').textContent =
      match.reason_summary || match.reason || '—';

    // Explanation
    const explanationEl = document.getElementById('detail-explanation');
    const explanationText = document.getElementById('detail-explanation-text');
    const explanation = match.explanation || '';
    if (explanation) {
      explanationText.textContent = explanation;
      explanationEl.style.display = '';
    } else {
      explanationEl.style.display = 'none';
    }
    renderDetailFlags(match);

    // Layer 2: Scoring breakdown
    const breakdownCanvas = document.getElementById('chart-breakdown');
    if (breakdown) {
      breakdownCanvas.style.display = '';
      buildBreakdownChart(breakdown);
      buildBreakdownTable(breakdown);
    } else {
      destroyChart('breakdown');
      breakdownCanvas.style.display = 'none';
      document.querySelector('#breakdown-table tbody').innerHTML =
        '<tr><td class="detail-unavailable">Score components are unavailable because the saved profile data for this run is incomplete.</td></tr>';
    }

    // Store data for audit modal
    _currentMatchData = {
      breakdown: {
        ...breakdown,
        instructor_name: match.instructor_name || match.instructor_id || '—'
      },
      alternatives: altData.ok ? (altData.alternatives || []) : [],
      swimmer_label: (() => {
        const s1 = match.swimmer_1_name || match.swimmer_name || match.swimmer_id || '';
        const s2 = match.swimmer_2_name || match.swimmer_id_2 || '';
        return s2 ? `${s1} & ${s2}` : String(s1);
      })()
    };

    // Layer 3: Alternatives
    const alternativesCanvas = document.getElementById('chart-alternatives');
    if (altData.ok) {
      alternativesCanvas.style.display = '';
      buildAlternativesChart(altData.current, altData.alternatives || []);
      buildAlternativesList(altData.current, altData.alternatives || []);
    } else {
      destroyChart('alternatives');
      alternativesCanvas.style.display = 'none';
      document.getElementById('alternatives-list').innerHTML =
        '<p class="empty-msg">Alternative instructors are unavailable because the saved profile data for this run is incomplete.</p>';
    }

  } catch (err) {
    console.error('Failed to load match detail:', err);
    showError('Failed to load match details.');
  }
}

function buildBreakdownChart(breakdown) {
  const ctx = document.getElementById('chart-breakdown');
  destroyChart('breakdown');

  const colorVal = breakdown.color_score || 0;
  const styleVal = breakdown.style_score || 0;

  charts.breakdown = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Color Score', 'Style Score'],
      datasets: [{
        data: [colorVal, styleVal],
        backgroundColor: ['#3b82f6', '#a855f7'],
        borderRadius: 4,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, max: 100, title: { display: true, text: 'Score (0-100)' } }
      }
    }
  });
}

function qualitativeLabel(score) {
  if (score < 34) return { text: 'Low', cls: 'q-low' };
  if (score < 67) return { text: 'Medium', cls: 'q-med' };
  return { text: 'High', cls: 'q-high' };
}

function buildBreakdownTable(breakdown) {
  const tbody = document.querySelector('#breakdown-table tbody');
  tbody.innerHTML = '';

  const colorQ = qualitativeLabel(breakdown.color_score || 0);
  const styleQ = qualitativeLabel(breakdown.style_score || 0);

  const rows = [
    ['Combined Score', `${(breakdown.score || 0).toFixed(1)}`],
    ['Color Compatibility', `<span class="q-badge ${colorQ.cls}">${colorQ.text}</span> <span class="q-val">${(breakdown.color_score || 0).toFixed(1)}</span>`],
    ['Style Compatibility', `<span class="q-badge ${styleQ.cls}">${styleQ.text}</span> <span class="q-val">${(breakdown.style_score || 0).toFixed(1)}</span>`],
    ['DIA Instructor', breakdown.is_dia ? 'Yes' : 'No'],
  ];

  rows.forEach(([label, value]) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${label}</td><td>${value}</td>`;
    tbody.appendChild(tr);
  });

  // Add "Show Calculation" button
  const btnRow = document.createElement('tr');
  btnRow.innerHTML = `<td colspan="2" style="text-align:center; padding-top: 12px;">
    <button class="btn btn-outline btn-sm" id="btn-show-calc">Show Calculation</button>
  </td>`;
  tbody.appendChild(btnRow);

  document.getElementById('btn-show-calc').addEventListener('click', () => {
    openAuditModal();
  });
}

function openAuditModal() {
  if (!_currentMatchData) return;
  _lastAuditFocusedElement = document.activeElement;
  const modal = document.getElementById('audit-modal');
  const backdrop = document.getElementById('audit-backdrop');
  // Set subtitle
  const subtitle = document.getElementById('audit-subtitle');
  if (subtitle) {
    const instr = escapeHtml(_currentMatchData.breakdown.instructor_name || '—');
    const swimmer = _currentMatchData.swimmer_label || '';
    subtitle.textContent = swimmer ? `${swimmer} → ${instr}` : instr;
  }
  buildAuditTables(_currentMatchData.breakdown, _currentMatchData.alternatives);
  modal.classList.remove('hidden');
  backdrop.classList.remove('hidden');
  document.getElementById('btn-close-audit').focus();
}

function closeAuditModal() {
  document.getElementById('audit-modal').classList.add('hidden');
  document.getElementById('audit-backdrop').classList.add('hidden');
  if (_lastAuditFocusedElement instanceof HTMLElement) _lastAuditFocusedElement.focus();
  _lastAuditFocusedElement = null;
}

function buildAuditTables(current, alternatives) {
  const container = document.getElementById('audit-tables');
  const top3 = (alternatives || []).slice(0, 3);
  const allScores = [current, ...top3];
  const headers = [
    current.instructor_name || 'Current',
    ...top3.map(a => a.instructor_name || '?')
  ];

  let html = '';

  // Swimmer preferences card (collapsible)
  html += buildSwimmerPrefsCard(current);

  // Colour Compatibility
  html += '<div class="audit-section-title">Colour Compatibility</div>';
  html += buildAuditTable(allScores, headers, 'color');

  // Style Compatibility
  html += '<div class="audit-section-title">Teaching Style Compatibility</div>';
  html += buildAuditTable(allScores, headers, 'style');

  // Divider
  html += '<hr style="border-color:#2d2d4e; margin: 12px 0;">';

  // Combined score pills
  html += '<div class="audit-section-title">Combined Score</div>';
  html += buildCombinedPills(allScores);

  // Legend cards (collapsible, at bottom)
  html += buildLegendCards();

  container.innerHTML = html;

  // Wire up all collapsible cards
  wireCollapsibles();
}

function buildAuditTable(allScores, headers, type) {
  const priKey  = type === 'color' ? 'primary_color'    : 'primary_style';
  const secKey  = type === 'color' ? 'secondary_color'  : 'secondary_style';
  const rawKey  = type === 'color' ? 'color_raw_total'  : 'style_raw_total';
  const normKey = type === 'color' ? 'color_score'      : 'style_score';
  const priLabel = type === 'color' ? 'Primary Colour'  : 'Primary Style';
  const secLabel = type === 'color' ? 'Secondary Colour': 'Secondary Style';

  let html = '<table class="audit-table"><thead><tr>';
  html += '<th class="component-col">Component</th>';
  allScores.forEach((s, i) => {
    const isCurrent = i === 0;
    const badge = isCurrent ? '<br><span class="current-badge">✓ Matched</span>' : '';
    html += `<th${isCurrent ? ' class="col-current"' : ''}>${escapeHtml(headers[i])}${badge}</th>`;
  });
  html += '</tr></thead><tbody>';

  // Row builder helper
  function makeRow(label, isDouble, cellFn) {
    const weightDots = isDouble
      ? '<span class="weight-dot">●●</span> <span class="weight-label">counts double</span>'
      : '<span class="weight-dot dim">●</span> <span class="weight-label">standard weight</span>';
    html += `<tr><td><div class="row-label"><span class="row-label-main">${label}</span><span class="row-label-weight">${weightDots}</span></div></td>`;
    allScores.forEach(cellFn);
    html += '</tr>';
  }

  // Primary row
  makeRow(priLabel, true, s => {
    const d = s.detail && s.detail[priKey];
    if (!d) { html += '<td>—</td>'; return; }
    const rankLine = (d.rank != null) ? `Rank ${d.rank} of ${d.of}` : 'Universal';
    const pts = (d.weighted != null) ? `${Math.round(d.weighted)} pts` : '—';
    html += `<td><div class="cell-data"><span class="cell-label">${escapeHtml(d.label)}</span><span class="cell-meta">${rankLine}</span><span class="cell-pts">${pts}</span></div></td>`;
  });

  // Secondary row
  makeRow(secLabel, false, s => {
    const d = s.detail && s.detail[secKey];
    if (!d) { html += '<td>—</td>'; return; }
    const rankLine = (d.rank != null) ? `Rank ${d.rank} of ${d.of}` : 'Universal';
    const pts = (d.weighted != null) ? `${Math.round(d.weighted)} pts` : '—';
    html += `<td><div class="cell-data"><span class="cell-label">${escapeHtml(d.label)}</span><span class="cell-meta">${rankLine}</span><span class="cell-pts">${pts}</span></div></td>`;
  });

  // Raw Total row
  html += '<tr class="row-total-bg"><td><div class="row-label"><span class="row-label-main">Raw Total</span></div></td>';
  allScores.forEach(s => {
    const raw = s.detail ? s.detail[rawKey] : null;
    html += `<td><strong>${raw != null ? Math.round(raw) + ' pts' : '—'}</strong></td>`;
  });
  html += '</tr>';

  // Normalised Score row
  const normValues = allScores.map(s => s[normKey] || 0);
  const bestNorm   = Math.max(...normValues);
  html += '<tr class="row-total-bg"><td><div class="row-label"><span class="row-label-main">Normalised Score</span><span class="row-label-weight dim">scaled 0–100</span></div></td>';
  allScores.forEach((s, i) => {
    const val = normValues[i];
    const isTop = val === bestNorm;
    const cls = val >= 70 ? 'sb-green' : val >= 40 ? 'sb-amber' : 'sb-red';
    const barCls = isTop ? 'sb-green' : cls;
    html += `<td><div class="score-bar-cell">` +
      `<span class="score-bar-val ${barCls}">${val.toFixed(1)}</span>` +
      `<div class="score-bar-track"><div class="score-bar-fill ${barCls}" style="width:${val.toFixed(1)}%"></div></div>` +
      `</div></td>`;
  });
  html += '</tr>';

  html += '</tbody></table>';
  return html;
}

function buildSwimmerPrefsCard(current) {
  const d = current.detail || {};
  const isPair = !!(current.swimmer_name_2 || current.swimmer_id_2);

  function swimmerCol(avatarLabel, name, priColour, secColour, priStyle, secStyle) {
    if (!name) return '';
    return `<div class="swimmer-pref-col">
      <div class="swimmer-pref-name"><span class="swimmer-avatar">${escapeHtml(avatarLabel)}</span>${escapeHtml(name)}</div>
      <table class="pref-table">
        <thead><tr><th class="pt-rank">#</th><th>Colour</th><th class="pt-pts">Pts</th><td class="pt-div"></td><th>Style</th><th class="pt-pts">Pts</th></tr></thead>
        <tbody>
          <tr><td class="pt-rank">1</td><td class="pt-val">${escapeHtml(priColour.label||'—')}</td><td class="pt-pts">${priColour.weighted!=null?Math.round(priColour.weighted):'—'}</td><td class="pt-div"></td><td class="pt-val">${escapeHtml(priStyle.label||'—')}</td><td class="pt-pts">${priStyle.weighted!=null?Math.round(priStyle.weighted):'—'}</td></tr>
          <tr><td class="pt-rank">2</td><td class="pt-val">${escapeHtml(secColour.label||'—')}</td><td class="pt-pts">${secColour.weighted!=null?Math.round(secColour.weighted):'—'}</td><td class="pt-div"></td><td class="pt-val">${escapeHtml(secStyle.label||'—')}</td><td class="pt-pts">${secStyle.weighted!=null?Math.round(secStyle.weighted):'—'}</td></tr>
        </tbody>
      </table>
    </div>`;
  }

  const col1 = swimmerCol(
    (current.swimmer_name||'S1').slice(0,2).toUpperCase(),
    current.swimmer_name || current.swimmer_id || 'Swimmer',
    d.primary_color   || {}, d.secondary_color || {},
    d.primary_style   || {}, d.secondary_style || {}
  );

  const pairNote = isPair
    ? `<div class="pref-pair-note">For a pair match, each swimmer is scored individually then combined using a <strong>harmonic mean</strong>.</div>`
    : '';

  return `<div class="pref-card">
    <div class="pref-card-header" data-toggle="pref-body">
      <span class="pref-card-title">🏊 Swimmer Preferences Used in This Match</span>
      <span class="pref-toggle">▼</span>
    </div>
    <div class="pref-card-body" id="pref-body">
      ${col1}
      ${pairNote}
    </div>
  </div>`;
}

function buildCombinedPills(allScores) {
  const best = Math.max(...allScores.map(s => s.score || 0));
  let html = '<div class="combined-pills">';
  allScores.forEach((s, i) => {
    const val  = (s.score || 0).toFixed(1);
    const isCurrent = i === 0;
    const cls  = s.score >= 70 ? 'ps-green' : s.score >= 40 ? 'ps-amber' : 'ps-red';
    const badge = isCurrent
      ? '<span class="pill-badge pb-matched">Matched</span>'
      : (i === 1 ? '<span class="pill-badge pb-alt">alternative</span>' : '');
    html += `<div class="score-pill${isCurrent ? ' current' : ''}">
      <span class="pill-instructor">${escapeHtml(s.instructor_name || '?')}</span>
      <span class="pill-score ${cls}">${val}</span>
      <span class="pill-label">out of 100</span>
      ${badge}
    </div>`;
  });
  html += '</div>';
  return html;
}

function buildLegendCards() {
  return `
  <div class="legend-card lc-blue" style="margin-top:20px">
    <div class="legend-card-header" data-toggle="legend-scores-body">
      <span class="legend-card-title">💡 How Scores Work</span>
      <span class="legend-card-toggle">▼</span>
    </div>
    <div class="legend-card-body" id="legend-scores-body">
      Each preference is ranked across all candidate instructors — <strong>Rank 1 = best fit</strong> and earns the most points.
      Primary preferences <strong>count twice as much</strong> as secondary ones.
      <div class="legend-pills">
        <span class="legend-pill">Rank 1 = top match, most points</span>
        <span class="legend-pill">Primary pref × 2 weight (counts double)</span>
        <span class="legend-pill">Secondary pref × 1 weight</span>
      </div>
    </div>
  </div>
  <div class="legend-card lc-purple">
    <div class="legend-card-header" data-toggle="legend-norm-body">
      <span class="legend-card-title">📐 How the Score is Normalised (0–100)</span>
      <span class="legend-card-toggle">▼</span>
    </div>
    <div class="legend-card-body" id="legend-norm-body">
      Raw points differ between sections (colour has fewer options than style).
      Normalising puts every section on the same 0–100 scale so they can be fairly compared and averaged.
      The green bar and value show the highest-scoring instructor for each section.
    </div>
  </div>`;
}

function wireCollapsibles() {
  document.querySelectorAll('[data-toggle]').forEach(btn => {
    const bodyId = btn.getAttribute('data-toggle');
    const body   = document.getElementById(bodyId);
    const icon   = btn.querySelector('.pref-toggle, .legend-card-toggle');
    if (!body) return;
    btn.addEventListener('click', () => {
      const open = body.classList.toggle('open');
      btn.classList.toggle('open', open);
      if (icon) icon.classList.toggle('open', open);
    });
  });
}

function buildAlternativesChart(current, alternatives) {
  const ctx = document.getElementById('chart-alternatives');
  destroyChart('alternatives');

  const all = [
    { name: current.instructor_name + ' (current)', score: current.score, isCurrent: true },
    ...alternatives.map(a => ({ name: a.instructor_name, score: a.score, isCurrent: false }))
  ];

  charts.alternatives = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: all.map(a => a.name),
      datasets: [{
        data: all.map(a => a.score),
        backgroundColor: all.map(a => a.isCurrent ? '#4ade80' : '#64748b'),
        borderRadius: 4,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, max: 100, title: { display: true, text: 'Compatibility Score' } }
      }
    }
  });
}

function buildAlternativesList(current, alternatives) {
  const container = document.getElementById('alternatives-list');
  container.innerHTML = '';

  if (alternatives.length === 0) {
    container.innerHTML = '<p class="empty-msg">No alternative instructors available.</p>';
    return;
  }

  alternatives.forEach(alt => {
    const delta = alt.score - current.score;
    const deltaClass = delta >= 0 ? 'delta-positive' : 'delta-negative';
    const deltaStr = delta >= 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1);

    const div = document.createElement('div');
    div.className = 'alt-card';
    div.innerHTML = `
      <div class="alt-header">
        <strong>${escapeHtml(alt.instructor_name)}</strong>
        <span class="conf-pill" style="background:${confidenceColor(alt.score)}">${alt.score.toFixed(1)}</span>
        <span class="${deltaClass}">${deltaStr}</span>
      </div>
      <div class="alt-reason">${escapeHtml(alt.why_not || '')}</div>
    `;
    container.appendChild(div);
  });
}
