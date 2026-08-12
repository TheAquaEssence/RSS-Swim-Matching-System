from pathlib import Path


DASHBOARD_JS = Path(__file__).resolve().parents[1] / "static" / "dashboard.js"


def test_dashboard_uses_shared_ui_utils():
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "const escapeHtml = window.AquaUi.escapeHtml;" in source
    assert "const normalizeConfidence = window.AquaUi.normalizeConfidence;" in source
    assert "function escapeHtml(" not in source
    assert "function normalizeConfidence(" not in source


def test_confidence_chart_filters_empty_buckets():
    """buildConfidenceChart must filter out zero-count buckets before rendering."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    # Must zip buckets+counts and filter before passing to Chart.js
    assert "count > 0" in source or "count !== 0" in source or ".filter(" in source


def test_type_chart_has_dropdown_wiring():
    """buildTypeChart must wire the chart-types-dim dropdown to swap datasets."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "chart-types-dim" in source


def test_type_chart_swaps_data_in_place():
    """The dropdown handler must update chart data without destroying/recreating."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    # In-place update pattern: set labels and data, then call chart.update()
    assert "chart.data.labels" in source
    assert "chart.data.datasets[0].data" in source
    assert "chart.update()" in source


def test_type_chart_match_type_view():
    """Match Type view must use only continuity and compatibility."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "breakdown.continuity" in source
    assert "breakdown.compatibility" in source


def test_type_chart_format_view():
    """Format view must use only individual and pair."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "breakdown.individual" in source
    assert "breakdown.pair" in source


# ── Score modal redesign (2026-03-21) ──────────────────────────────────────

def test_modal_has_subtitle_element():
    """Modal header should include an #audit-subtitle span updated by JS."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "audit-subtitle" in source

def test_cell_data_three_line_format():
    """Cell should have cell-label, cell-meta (rank), and cell-pts (points) spans."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "cell-label" in source
    assert "cell-meta" in source
    assert "cell-pts" in source

def test_score_bar_in_normalised_row():
    """Normalised score row should contain a score bar element."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "score-bar-cell" in source

def test_combined_score_pills():
    """Combined score section uses pill layout, not plain table."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "combined-pills" in source
    assert "score-pill" in source

def test_matched_pill_badge():
    """Matched instructor gets a 'Matched' pill badge."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "pill-badge" in source
    assert "Matched" in source

def test_swimmer_pref_card_present():
    """Swimmer preferences collapsible card is generated."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "pref-card" in source

def test_legend_cards_at_bottom():
    """How-scores-work and normalisation legend cards are generated."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "legend-card" in source
    assert "How Scores Work" in source
    assert "How the Score is Normalised" in source

def test_no_best_badge_in_normalised_row():
    """No literal 'Best' text badge on normalised score cells — just highlight class."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "best-badge" not in source

def test_dashboard_uses_shared_product_navigation():
    """XAI retains a clear return route and identifies the active product area."""
    template = (DASHBOARD_JS.parent.parent / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'nav class="product-nav" aria-label="Primary navigation"' in template
    assert 'class="product-nav-link" href="/"' in template
    assert '<span>Matching</span>' in template
    assert 'class="product-nav-link active" href="/xai/" aria-current="page"' in template
    assert '<span>Explainability</span>' in template
    assert 'aria-label="Return to Aqua Essence matching"' in template


def test_dashboard_uses_shared_desktop_workspace_shell():
    template = (DASHBOARD_JS.parent.parent / "templates" / "index.html").read_text(encoding="utf-8")

    assert 'href="/styles/workspace.css' in template
    assert 'class="skip-link" href="#main-content"' in template
    assert 'class="app-shell"' in template
    assert 'class="app-sidebar" aria-label="Application sidebar"' in template
    assert 'class="app-workspace"' in template
    assert 'class="content" id="main-content"' in template


def test_dashboard_icon_buttons_have_accessible_names_and_explicit_types():
    template = (DASHBOARD_JS.parent.parent / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'type="button" title="Table view" aria-label="Table view"' in template
    assert 'type="button" title="Card view" aria-label="Card view"' in template
    assert 'type="button" aria-label="Close match detail"' in template
    assert 'type="button" aria-label="Close score calculation breakdown"' in template


def test_dashboard_derives_flagged_matches_from_loaded_matches():
    """Overview should be able to build flagged rows directly from match data."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    assert "collectFlaggedMatches" in source
    assert "getReviewFlags" in source
    assert "buildFlaggedTable(collectFlaggedMatches(state.matches" in source


def test_dashboard_renders_detail_review_flags():
    """Match detail panel should expose review flags when a match has them."""
    source = DASHBOARD_JS.read_text(encoding="utf-8")
    template = (DASHBOARD_JS.parent.parent / "templates" / "index.html").read_text(encoding="utf-8")
    assert "renderDetailFlags(match)" in source
    assert "detail-flags-list" in template
