---
name: crawshrimp-skill
description: Use when an AI agent needs to explore a live webpage, operate authenticated enterprise/internal pages through CDP 9222, understand page state, plan safe browser actions, extract data, download files, fill forms without dangerous submission, or complete multi-step web workflows with evidence.
---

# Crawshrimp Skill

## Overview

Crawshrimp Skill has two jobs: use crawshrimp-style CDP browser automation to let an AI agent complete live webpage tasks, then freeze proven workflows into reusable skills, scripts, or CLI commands.

The loop is: observe, model, plan, act, verify, journal, then distill.

## Operation Surface Ladder

Do not blindly start from APIs. First observe the prepared browser and page state, then choose the fastest reliable surface:

1. Visible UI/DOM for simple controls and human-readable readback.
2. Page-owned application APIs, frontend modules, or observed request wrappers for complex React/Vue/Next flows when they reduce editor, selector, or coordinate brittleness.
3. Low-level CDP primitives only when the UI and app layer are insufficient.

For create/update/publish flows, the page-owned API is usually faster and more stable after the payload shape, auth context, required fields, and disabled-state rules are understood. Verify persisted state through UI refresh plus application/API readback when possible.

## Default Browser Entry

For authenticated, enterprise, or internal pages, start with the user's existing CDP browser on `http://127.0.0.1:9222`. Use `--cdp-url http://127.0.0.1:9222` and observe the requested URL prefix before opening a new browser, using a browser extension, or asking the user to log in again.

If the page looks logged out, first check whether the 9222 browser already has a logged-in tab or session for the same host. Treat a login screen in a fresh browser as an environment mismatch until the 9222 session is ruled out.

## Operating Loop

1. Classify the task as `read`, `operate`, or `flow`.
2. Observe the current page before acting: URL, title, visible text, controls, tables, downloads, network clues, and blocking states.
3. Read business rules before editing: quotas, used/remaining capacity, percentage totals, field validation, permission state, and save semantics.
4. Build a page model that names the user's goal, the relevant objects, safe actions, risks, and success evidence.
5. Choose the least brittle operation surface. Use DOM controls when they are clear; for complex Next/React/Vue enterprise apps, prefer page-owned frontend API/module wrappers already loaded by the page when they are safer than coordinate, editor-state, or fragile selector work.
6. Plan small steps with stop conditions. Every planned action needs a readback or verification signal, and ratio/percentage updates must avoid invalid intermediate totals.
7. Execute one safe action at a time. Re-observe after page transitions, dialogs, downloads, navigation, or re-render.
8. Verify against evidence, not hope: visible UI state, extracted rows, downloaded files, changed URL, success messages, stable network results, or application readback. Use double verification for enterprise form changes: refreshed visible UI plus API/application-state readback when available.
9. Journal the work. Record observations, plans, actions, verification evidence, failures, and the final reusable workflow notes.

Use `scripts/web_agent_protocol.py` for the shared task taxonomy, safety checks, plan template, and evidence journal schema:

```bash
python3 scripts/web_agent_protocol.py classify "抓取这个页面表格并总结"
python3 scripts/web_agent_protocol.py plan "筛选近7天并下载导出文件"
python3 scripts/web_agent_protocol.py journal-template "多页面收集详情证据"
```

Use `scripts/web_operator.py` for the normal five-verb web operation protocol:

```bash
python3 scripts/web_operator.py observe --url-prefix https://example.com --task "summarize the page" --journal run.json
python3 scripts/web_operator.py act click --url-prefix https://example.com --selector "button.export" --reason "open export menu" --journal run.json
python3 scripts/web_operator.py act navigate --url-prefix https://example.com --url "https://example.com/report" --reason "open report page" --journal run.json
python3 scripts/web_operator.py act paginate --url-prefix https://example.com --selector "button.next" --reason "move to next result page" --journal run.json
python3 scripts/web_operator.py act upload --url-prefix https://example.com --selector "input[type=file]" --file ./input.csv --reason "attach import file" --journal run.json
python3 scripts/web_operator.py act upload-chooser --url-prefix https://example.com --clicks-json '[{"x":120,"y":240}]' --file ./input.csv --reason "attach file through native chooser" --journal run.json
python3 scripts/web_operator.py act capture-wheel --url-prefix https://example.com --wheels-json '[{"x":640,"y":520,"delta_y":900}]' --value '[{"url_contains":"/api/"}]' --reason "capture lazy-load requests" --journal run.json
python3 scripts/web_operator.py act download --url-prefix https://example.com --selector "a.export" --expected-file report.csv --download-dir ~/Downloads --reason "download export artifact" --journal run.json
python3 scripts/web_operator.py verify --url-prefix https://example.com --expression "document.body.innerText.includes('Export')" --evidence "export menu visible" --journal run.json
python3 scripts/web_operator.py verify --check file-exists --target report.csv --download-dir ~/Downloads --evidence "report file exists" --journal run.json
python3 scripts/web_operator.py distill --journal run.json --output workflow.md
python3 scripts/web_operator.py distill --journal run.json --output-dir reusable-workflow --name example-export --include-skill
```

Use `scripts/browser_executor.py` only when you need low-level direct CDP primitives:

```bash
python3 scripts/browser_executor.py cdp --url-prefix https://example.com observe
python3 scripts/browser_executor.py cdp --url-prefix https://example.com eval --script "document.title"
python3 scripts/browser_executor.py cdp --url-prefix https://example.com capture --capture-mode passive --matches-json '[{"url_contains":"/api/"}]'
```

Use crawshrimp-compatible execution helpers when reusing or distilling adapter-shaped work:

```bash
python3 scripts/adapter_registry.py --root adapters scan
python3 scripts/knowledge_service.py --adapters-root adapters --probes-root probes --data-root knowledge rebuild
python3 scripts/knowledge_service.py --data-root knowledge search --query "export drawer" --adapter temu --task goods_traffic_detail
python3 scripts/phase_runner.py --url-prefix https://example.com --file adapters/demo/orders.js --params-json '{"keyword":"sku"}' --artifact-dir artifacts
```

## Crawshrimp Runtime Compatibility

This skill mirrors the main crawshrimp execution surfaces in reusable form:

- adapter/task registry and safe manifest path resolution
- auth check script execution
- knowledge cards from notes and probe bundles
- probe bundle artifacts: DOM, framework, network, endpoints, strategy, recommendations, report
- JSRunner-style phase/shared runtime with `window.__CRAWSHRIMP_PAGE__`, `window.__CRAWSHRIMP_PHASE__`, `window.__CRAWSHRIMP_SHARED__`, and `window.__CRAWSHRIMP_PARAMS__`
- runtime actions: `cdp_clicks`, `inject_files`, `file_chooser_upload`, `capture_click_requests`, `capture_url_requests`, `capture_wheel_requests`, `download_urls`, `download_clicks`, `reload_page`, `next_phase`, `complete`, `abort`
- request capture options for URL/click/wheel flows: `matches`, `min_matches`, `settle_ms`, and `include_response_body`
- URL download retries, concurrency, progress, artifact naming, existing-file skip, and data URL support
- browser-session URL downloads through a temporary CDP tab when a file URL depends on logged-in browser state
- click-download artifact detection with hooks for host-level transient tab handling
- navigation retry and timeout reload recovery in the phase runner

## Supported Task Families

| Family | Use for | Completion evidence |
| --- | --- | --- |
| `read` | table extraction, search results, page summaries, visible data export | extracted records match visible page evidence or cited source areas |
| `operate` | filters, pagination, opening details, downloads, safe form filling | page state, file artifact, or form readback proves the requested state |
| `flow` | multi-page, multi-dialog, repeated detail collection, reusable workflow discovery | journal contains transition evidence and reusable workflow notes |

## Safety Boundary

Default to safe, reversible, or read-only actions. Stop and ask the user before submit, publish, send, delete, pay, purchase, confirm, bulk modify, or any action with external side effects.

Do not treat a filled form as permission to submit it. Filling fields can be safe; sending the form is a separate dangerous action.

For enterprise forms, final save or submit is dangerous unless the user explicitly authorizes that exact change. If authorization is already explicit in the conversation, proceed with a journaled action and immediate readback.

## Reference Map

- Read `references/protocol.md` for the protocol objects, task families, action risks, and evidence journal.
- Read `references/page-observation.md` when the page is unknown or dynamic and needs a durable page model.
- Read `references/task-planning.md` when converting a user goal into small web actions.
- Read `references/action-primitives.md` before clicking, typing, selecting, downloading, uploading, waiting, or navigating.
- Read `references/network-intelligence.md` when deciding whether to inspect requests or stay DOM-first.
- Read `references/browser-execution.md` before using direct Chrome/CDP, `observe / act / verify / journal / distill`, or low-level request capture.
- Read `references/enterprise-form-workflows.md` before editing authenticated internal forms, quotas, percentages, allocations, approval flows, or other enterprise workflow settings.
- Read `references/verification.md` for structured completion checks.
- Read `references/safety.md` before any caution or dangerous action.
- Read `references/workflow-distillation.md` after a workflow succeeds and should become a reusable skill, script, CLI command, or adapter draft.
- Read `references/workflow-reuse.md` for the generated reusable package contract.
- Read `references/verification-and-journal.md` before claiming the task is complete or distilling a reusable workflow.
- Read `PLAN.md` for the implementation roadmap for this repository.

## Common Mistakes

- Acting before observing the page.
- Opening a fresh browser or extension first for a logged-in internal page instead of checking `http://127.0.0.1:9222`.
- Asking the user to log in again after seeing a login page without checking the 9222 CDP browser session.
- Editing enterprise form values before reading business rules, quotas, used capacity, or total-percentage constraints.
- Raising percentage items before lowering the oversized item when the form enforces a total cap.
- Brute-forcing a brittle DOM/coordinate path when the page already exposes a safe frontend API wrapper.
- Running one large script without readback checkpoints.
- Treating a clicked button as success without checking resulting state.
- Submitting, publishing, deleting, sending, paying, or bulk modifying without explicit user confirmation.
- Claiming an enterprise form change from only one signal; use double verification with refreshed UI and application/API readback when available.
- Forgetting to record evidence, which makes the workflow impossible to debug or reuse.
- Stopping at `workflow.md` when the workflow will be repeated; generate a reusable package with `distill --output-dir`.
