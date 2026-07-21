"""
PDF Report Generator for CP-SAT Matching Results.

Generates a printable PDF suitable for deck-side review by staff.
Includes: summary statistics, match table (sorted by confidence ascending),
and unassigned swimmers section.
"""
import os
from datetime import datetime
from typing import List, Dict
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import LETTER, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from core.flags import expand_flag_codes, get_highest_severity


_SEVERITY_RANK = {'none': 0, 'info': 1, 'review': 2, 'urgent': 3}


def _p(text, style):
    return Paragraph(escape('' if text is None else str(text)), style)


def _format_percent(value, digits=1):
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}%"
    return '' if value in (None, '') else str(value)


def _swimmer_names(match: Dict) -> str:
    if match.get('type') == 'pair':
        s1_name = (
            match.get('swimmer_1').name
            if hasattr(match.get('swimmer_1'), 'name')
            else str(match.get('swimmer_1_id', '?'))
        )
        s2_name = (
            match.get('swimmer_2').name
            if hasattr(match.get('swimmer_2'), 'name')
            else str(match.get('swimmer_2_id', '?'))
        )
        return f"{s1_name}, {s2_name}"
    return (
        match.get('swimmer').name
        if hasattr(match.get('swimmer'), 'name')
        else str(match.get('swimmer_id', '?'))
    )


def _flag_titles(flag_codes: List[str]) -> str:
    flags = expand_flag_codes(flag_codes)
    return '; '.join(flag.get('title') or flag.get('code', '') for flag in flags)


def _review_action_label(flag_codes: List[str]) -> str:
    flags = expand_flag_codes(flag_codes)
    if not flags:
        return ''
    severity = get_highest_severity(flag_codes)
    primary = next(
        (flag for flag in flags if flag.get('severity') == severity),
        flags[0],
    )
    return primary.get('review_action_label', '')


def _collect_review_items(
    annotated_matches: List[Dict],
    unassigned_swimmers: list,
    unassigned_diagnostics: Dict | None,
) -> List[Dict]:
    diagnostics = unassigned_diagnostics or {}
    items = []

    for match in annotated_matches:
        flag_codes = list(match.get('flag_codes', []))
        if not flag_codes:
            continue
        items.append({
            'severity': get_highest_severity(flag_codes),
            'swimmers': _swimmer_names(match),
            'instructor': match.get('instructor_name', str(match.get('instructor_id', '?'))),
            'flags': _flag_titles(flag_codes),
            'action': _review_action_label(flag_codes),
        })

    for swimmer in unassigned_swimmers:
        diagnostic = diagnostics.get(getattr(swimmer, 'swimmer_id', None), {})
        flag_codes = list(diagnostic.get('flag_codes', []))
        if not flag_codes:
            continue
        best = diagnostic.get('best_available_instructor_name', 'Manual review')
        score = diagnostic.get('best_available_score')
        if score not in (None, ''):
            best = f"{best} ({_format_percent(score)})"
        items.append({
            'severity': get_highest_severity(flag_codes),
            'swimmers': getattr(swimmer, 'name', str(getattr(swimmer, 'swimmer_id', '?'))),
            'instructor': best,
            'flags': _flag_titles(flag_codes),
            'action': _review_action_label(flag_codes),
        })

    return sorted(
        items,
        key=lambda item: (-_SEVERITY_RANK.get(item['severity'], 0), item['swimmers']),
    )


def generate_pdf_report(
    output_path: str,
    annotated_matches: List[Dict],
    unassigned_swimmers: list,
    continuity_count: int,
    compatibility_count: int,
    classes: Dict,
    disputed_ids: set = None,
    unassigned_diagnostics: Dict | None = None,
) -> str:
    """
    Generate PDF report of matching results.

    Args:
        output_path: Path to write the PDF file
        annotated_matches: List of annotated match dicts from Phase 3
        unassigned_swimmers: List of Swimmer objects not assigned
        continuity_count: Number of continuity matches
        compatibility_count: Number of compatibility matches
        classes: Dict of class objects
        disputed_ids: Set of swimmer IDs with continuity disputes
        unassigned_diagnostics: Optional per-swimmer diagnostics for review flags

    Returns:
        The output_path (for convenience)
    """
    if disputed_ids is None:
        disputed_ids = set()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(LETTER),
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    small_cell = ParagraphStyle(
        'SmallCell',
        parent=styles['Normal'],
        fontSize=7,
        leading=9,
    )
    elements = []

    # --- Title ---
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=18,
        spaceAfter=6,
    )
    elements.append(Paragraph("Aqua Essence — Matching Report", title_style))
    elements.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        styles['Normal']
    ))
    elements.append(Spacer(1, 12))

    # --- Summary Statistics ---
    total_swimmers = sum(
        2 if m['type'] == 'pair' else 1 for m in annotated_matches
    )
    avg_confidence = (
        sum(m.get('confidence', 0) for m in annotated_matches) / len(annotated_matches)
        if annotated_matches else 0
    )

    summary_data = [
        ['Metric', 'Value'],
        ['Total Classes', str(len(classes))],
        ['Assigned Swimmers', str(total_swimmers)],
        ['Unassigned Swimmers', str(len(unassigned_swimmers))],
        ['Continuity Matches', str(continuity_count)],
        ['Compatibility Matches', str(compatibility_count)],
        ['Average Confidence', f'{avg_confidence:.1f}%'],
    ]

    summary_table = Table(summary_data, colWidths=[2.5 * inch, 2 * inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
        ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 18))

    # --- Review Items ---
    review_items = _collect_review_items(
        annotated_matches, unassigned_swimmers, unassigned_diagnostics
    )
    if review_items:
        elements.append(Paragraph("Review Items", styles['Heading2']))
        elements.append(Paragraph(
            "Flagged assignments and unassigned swimmers sorted by severity.",
            styles['Italic']
        ))
        elements.append(Spacer(1, 6))

        review_rows = [['Severity', 'Swimmer(s)', 'Instructor / Best Option', 'Flag', 'Action']]
        for item in review_items:
            review_rows.append([
                item['severity'].title(),
                _p(item['swimmers'], small_cell),
                _p(item['instructor'], small_cell),
                _p(item['flags'], small_cell),
                _p(item['action'], small_cell),
            ])

        review_table = Table(
            review_rows,
            colWidths=[0.75 * inch, 1.65 * inch, 1.75 * inch, 2.0 * inch, 2.25 * inch],
            repeatRows=1,
        )
        review_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8a4b00')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]
        for row_idx, item in enumerate(review_items, start=1):
            if item['severity'] == 'urgent':
                bg = colors.HexColor('#f8d7da')
            elif item['severity'] == 'review':
                bg = colors.HexColor('#fff3cd')
            else:
                bg = colors.HexColor('#dbeafe')
            review_style.append(('BACKGROUND', (0, row_idx), (-1, row_idx), bg))
        review_table.setStyle(TableStyle(review_style))
        elements.append(review_table)
        elements.append(Spacer(1, 18))

    # --- Match Table ---
    elements.append(Paragraph("Match Assignments", styles['Heading2']))
    elements.append(Paragraph(
        "Sorted by confidence (lowest first — review these first)",
        styles['Italic']
    ))
    elements.append(Spacer(1, 6))

    # Sort by confidence ascending
    sorted_matches = sorted(annotated_matches, key=lambda m: m.get('confidence', 0))

    match_header = ['Instructor', 'Swimmer(s)', 'Type', 'Score', 'Confidence', 'Review', 'Reason']
    match_rows = [match_header]

    for m in sorted_matches:
        instructor_name = m.get('instructor_name', str(m.get('instructor_id', '?')))

        if m['type'] == 'pair':
            is_disputed = (
                m.get('swimmer_1_id') in disputed_ids or
                m.get('swimmer_2_id') in disputed_ids
            )
        else:
            is_disputed = m.get('swimmer_id') in disputed_ids

        swimmer_names = _swimmer_names(m)
        match_type = m.get('match_type', '?')
        score = f"{m.get('compatibility_score', 0):.1f}%" if m.get('match_type') == 'compatibility' else '\u2014'
        confidence = f"{m.get('confidence', 0):.0f}%"
        reason = m.get('reason_summary', '')
        flag_codes = list(m.get('flag_codes', []))
        review = _flag_titles(flag_codes)
        if is_disputed and not review:
            review = 'Continuity dispute'

        match_rows.append([
            _p(instructor_name, small_cell),
            _p(swimmer_names, small_cell),
            match_type,
            score,
            confidence,
            _p(review or '', small_cell),
            _p(reason, small_cell),
        ])

    # Calculate column widths for landscape
    match_table = Table(
        match_rows,
        colWidths=[1.35 * inch, 1.75 * inch, 0.85 * inch, 0.75 * inch, 0.85 * inch, 1.45 * inch, 2.15 * inch],
        repeatRows=1,
    )

    # Style the match table
    table_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ALIGN', (3, 0), (4, -1), 'CENTER'),
        ('ALIGN', (5, 0), (5, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]

    # Color-code confidence cells
    for i, m in enumerate(sorted_matches, start=1):
        conf = m.get('confidence', 0)
        if conf >= 85:
            bg = colors.HexColor('#d4edda')  # green
        elif conf >= 70:
            bg = colors.HexColor('#cce5ff')  # blue
        elif conf >= 50:
            bg = colors.HexColor('#fff3cd')  # yellow
        else:
            bg = colors.HexColor('#f8d7da')  # red
        table_style.append(('BACKGROUND', (4, i), (4, i), bg))

        # Highlight dispute rows
        swimmer_id = m.get('swimmer_id') or m.get('swimmer_1_id')
        if swimmer_id and swimmer_id in disputed_ids:
            table_style.append(('BACKGROUND', (5, i), (5, i), colors.HexColor('#fff3cd')))

        severity = get_highest_severity(list(m.get('flag_codes', [])))
        if severity == 'urgent':
            table_style.append(('BACKGROUND', (5, i), (5, i), colors.HexColor('#f8d7da')))
        elif severity == 'review':
            table_style.append(('BACKGROUND', (5, i), (5, i), colors.HexColor('#fff3cd')))
        elif severity == 'info':
            table_style.append(('BACKGROUND', (5, i), (5, i), colors.HexColor('#dbeafe')))

    match_table.setStyle(TableStyle(table_style))
    elements.append(match_table)

    # --- Unassigned Swimmers ---
    if unassigned_swimmers:
        elements.append(Spacer(1, 18))
        elements.append(Paragraph("Unassigned Swimmers", styles['Heading2']))
        elements.append(Paragraph(
            "These swimmers could not be matched and require manual assignment.",
            styles['Italic']
        ))
        elements.append(Spacer(1, 6))

        diagnostics = unassigned_diagnostics or {}
        unassigned_header = ['Name', 'Skill', 'Age', 'Special Needs', 'Reason / Review', 'Best Legal Match']
        unassigned_rows = [unassigned_header]

        for s in unassigned_swimmers:
            diagnostic = diagnostics.get(getattr(s, 'swimmer_id', None), {})
            flag_codes = list(diagnostic.get('flag_codes', []))
            reason = (
                'Below auto-assignment threshold'
                if flag_codes
                else 'Manual assignment required'
            )
            review = _flag_titles(flag_codes)
            if review:
                reason = f"{reason}: {review}"
            best = diagnostic.get('best_available_instructor_name', '')
            best_score = diagnostic.get('best_available_score')
            if best and best_score not in (None, ''):
                best = f"{best} ({_format_percent(best_score)})"
            unassigned_rows.append([
                _p(s.name if hasattr(s, 'name') else str(getattr(s, 'swimmer_id', '?')), small_cell),
                str(getattr(s, 'skill_level', '?')),
                f"{s.age:.1f}" if hasattr(s, 'age') else '?',
                'Yes' if getattr(s, 'has_special_needs', False) else 'No',
                _p(reason, small_cell),
                _p(best, small_cell),
            ])

        unassigned_table = Table(
            unassigned_rows,
            colWidths=[1.7 * inch, 0.7 * inch, 0.55 * inch, 0.9 * inch, 2.4 * inch, 1.8 * inch],
            repeatRows=1,
        )
        unassigned_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c0392b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fadbd8')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(unassigned_table)

    # --- Footer ---
    elements.append(Spacer(1, 24))
    elements.append(Paragraph(
        "Generated by Aqua Essence Matching System — Ready, Set, Swim!",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey)
    ))

    doc.build(elements)
    return output_path
