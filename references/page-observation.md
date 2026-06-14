# Page Observation

## Minimum Page Model

Capture enough state for another agent to understand the page without seeing it:

- URL and title.
- Visible headings and important text.
- Forms, inputs, selects, checkboxes, radios, buttons, tabs, menus, and dialogs.
- Tables, lists, cards, result counts, pagination, and empty/busy/error states.
- Downloads, upload controls, and generated artifacts.
- Network clues only when DOM evidence is insufficient or the page's own API is more reliable.

## Unknown Page Routine

1. Read the visible page before clicking.
2. Identify the user's target object: table, product, order, file, dialog, report, or form.
3. Identify safe controls and dangerous controls separately.
4. Find success signals before acting.
5. Find failure and blocking signals before acting.
6. Act only after the page model explains why the action is safe and useful.

## Dynamic Page Rules

- Re-observe after navigation, re-render, popover open/close, filter changes, pagination, downloads, or errors.
- Scope observations to the active dialog, drawer, tab, frame, or page region.
- Prefer stable labels and roles over brittle CSS selectors when a browser tool provides them.
- Treat stale rows, false loading states, and empty states as evidence problems, not immediate conclusions.

## Useful Evidence

- "The filter chip now says Last 7 days."
- "The results table has 43 rows and the first row changed from X to Y."
- "The detail drawer title matches order 123."
- "A file named report.csv appeared and has nonzero size."
- "The visible warning says this action cannot be undone."
