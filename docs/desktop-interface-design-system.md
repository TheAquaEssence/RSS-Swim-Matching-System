# Desktop Interface And Design System

This document records the production interface introduced by the staged desktop
redesign. Aqua Essence is a Windows desktop application; the interface targets
desktop widths of 980 pixels and above and does not define a mobile product
experience.

## Information Architecture

The persistent left navigation separates the operator workflow into four clear
areas:

1. **Matching** — confirm source data, review safeguards, and start a run.
2. **Results** — inspect the latest assignments, filter review items, open
   profiles, and export the completed schedule and report.
3. **Explainability** — review decision quality, flags, alternatives, and
   individual match evidence.
4. **Data & settings** — maintain historical sessions, reference tables,
   rankings, instructor records, and fallback defaults.

Results and Explainability remain unavailable until a result exists. This keeps
the initial workflow focused without suggesting that the application can review
data it has not generated.

## Visual Foundations

The redesign preserves the existing dark and light theme colors. Both themes
share the same spacing, typography, shape, elevation, and interaction rules:

- Outfit is the interface typeface; JetBrains Mono is reserved for identifiers
  and structured technical values.
- A compact fixed sidebar and sticky workspace header provide orientation.
- Cards group one decision or task; nested borders and decoration are kept
  minimal so content hierarchy does the work.
- Primary buttons advance the current workflow. Secondary buttons support it;
  ghost buttons are reserved for low-emphasis or reversible actions.
- Success, warning, review, danger, disabled, loading, empty, and error states
  use the same semantic treatment in both themes.

The shared shell and tokens live in `frontend/styles/workspace.css`. Matching
and results composition lives in `frontend/styles/matching-workspace.css`;
drawers, editors, and historical-session interactions are unified in
`frontend/styles/interaction-workspace.css`. Feature styles load after the
legacy base layers so the redesign can remain incremental and reviewable.

## Interaction Rules

- Changing a workspace updates the active navigation item, window title, URL
  fragment, header context, scroll position, and keyboard focus.
- Starting a run disables and marks the Generate button busy until the request
  finishes, preventing accidental duplicate jobs.
- Result rows support pointer, Enter, and Space activation. Profile drawers and
  editor dialogs move focus inside when opened and restore it when closed.
- Historical-session groups expose their expanded state and support Enter and
  Space. Searches and result filters announce changing counts without stealing
  focus.
- Theme choice and operator name persist locally. No operational data or theme
  asset is fetched from the internet.

## Accessibility Baseline

The interface provides a skip link, semantic headings and landmarks, labelled
controls, visible keyboard focus, live status regions, dialog names, expansion
state, reduced-motion support, and focus management across workspace and overlay
transitions. Text and semantic state colors are defined independently for the
dark and light themes to retain readable contrast.

Accessibility is a release requirement, not a one-time audit. Changes to the
shell, navigation, generation flow, overlays, or theme tokens should include a
keyboard pass in both themes and update the focused frontend regression tests.

## Desktop Review Checklist

Before merging an interface change:

- verify Matching, Results, Data & settings, and Explainability at 1440×900 and
  at the 980-pixel minimum supported width;
- test dark and light themes, keyboard-only navigation, reduced motion, loading,
  success, validation-error, empty-result, disabled, and dialog states;
- confirm that no horizontal page overflow is introduced;
- run the frontend, backend asset/security, XAI, Electron, and packaged-renderer
  checks described in the development and packaging guides;
- use only synthetic content in screenshots, fixtures, and review artifacts.
