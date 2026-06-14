# Safety

## Default Boundary

Safe actions are reversible, local, or read-only: observe, click harmless controls, type into fields, select filters, paginate, download, and wait.

Caution actions need extra context: upload, cross-account navigation, long-running batch actions, and ambiguous confirmation dialogs.

Dangerous actions require explicit user confirmation naming the target and consequence:

- submit
- publish
- send
- delete
- pay
- purchase
- confirm
- bulk modify
- any irreversible external effect

## Context Checks

Before operating, identify account, store, workspace, or environment when it is visible. If the context is unclear and the task could affect real state, stop.

Do not turn a filled form into a submitted form without a separate confirmation.
