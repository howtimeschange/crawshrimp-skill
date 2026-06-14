# Task Planning

## Goal First

Start from the user's requested outcome, not from a script shape.

Plan each webpage task as:

1. current page evidence
2. next safe question to answer
3. one action or read
4. expected readback
5. fallback if the readback fails

## Task Families

- `read`: collect visible data or page-owned API evidence without changing state.
- `operate`: change local page state such as filters, tabs, pagination, form fields, or downloads.
- `flow`: move through multiple pages, drawers, dialogs, or repeated detail states.

## Replanning

Replan when:

- the page URL, active dialog, or result region changes unexpectedly
- a selector no longer exists after re-render
- a table signature or row count does not change after a filter or page turn
- a file, request, or success message does not appear

The next step after failed readback is normally `observe`, not another larger script.
