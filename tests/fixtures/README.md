# Test Fixtures

## Provenance

- Observed against Cursor 3.11.13 (`3f21b08f0b436a07be29fbfe00b304fa15553350`)
- Observation date: 2026-07-13
- Source: live renderer class names and settings label map in
  `workbench.desktop.main.js`, plus DevTools-inspected Settings DOM structure

## Files

- `cursor_settings_311.html` — sanitized Cursor Settings sidebar/content fixture
- `vscode_settings.html` — ordinary VS Code settings editor fixture

## Retained structural facts

- Stable classes: `cursor-settings-sidebar-cell-label`,
  `cursor-settings-sidebar-nav-cell`, `cursor-settings-layout-main`,
  `cursor-settings-pane-content`, `cursor-settings-cell-label`
- Settings search control placeholder/accessible name: `Search settings` /
  `Search Settings`
- No Shadow Root / iframe hosting for the Cursor Settings path

## Removed private values

- No account emails, tokens, workspace paths, chat content, or machine-local
  absolute paths
- No application bundle bytes
