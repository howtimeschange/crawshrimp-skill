---
name: crawshrimp-skill
description: Use when an AI agent needs to explore a live webpage, understand page state, plan safe browser actions, extract data, download files, fill forms without dangerous submission, or complete multi-step web workflows with evidence.
---

# Crawshrimp Skill

## Overview

Crawshrimp Skill has two jobs: use crawshrimp-style CDP browser automation to let an AI agent complete live webpage tasks, then freeze proven workflows into reusable skills, scripts, or CLI commands.

The loop is: observe, model, plan, act, verify, journal, then distill.

## Operating Loop

1. Classify the task as `read`, `operate`, or `flow`.
2. Observe the current page before acting: URL, title, visible text, controls, tables, downloads, network clues, and blocking states.
3. Build a page model that names the user's goal, the relevant objects, safe actions, risks, and success evidence.
4. Plan small steps with stop conditions. Every planned action needs a readback or verification signal.
5. Execute one safe action at a time. Re-observe after page transitions, dialogs, downloads, navigation, or re-render.
6. Verify against evidence, not hope: visible UI state, extracted rows, downloaded files, changed URL, success messages, or stable network results.
7. Journal the work. Record observations, plans, actions, verification evidence, failures, and the final reusable workflow notes.

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

## Supported Task Families

| Family | Use for | Completion evidence |
| --- | --- | --- |
| `read` | table extraction, search results, page summaries, visible data export | extracted records match visible page evidence or cited source areas |
| `operate` | filters, pagination, opening details, downloads, safe form filling | page state, file artifact, or form readback proves the requested state |
| `flow` | multi-page, multi-dialog, repeated detail collection, reusable workflow discovery | journal contains transition evidence and reusable workflow notes |

## Safety Boundary

Default to safe, reversible, or read-only actions. Stop and ask the user before submit, publish, send, delete, pay, purchase, confirm, bulk modify, or any action with external side effects.

Do not treat a filled form as permission to submit it. Filling fields can be safe; sending the form is a separate dangerous action.

## Reference Map

- Read `references/protocol.md` for the protocol objects, task families, action risks, and evidence journal.
- Read `references/page-observation.md` when the page is unknown or dynamic and needs a durable page model.
- Read `references/task-planning.md` when converting a user goal into small web actions.
- Read `references/action-primitives.md` before clicking, typing, selecting, downloading, uploading, waiting, or navigating.
- Read `references/network-intelligence.md` when deciding whether to inspect requests or stay DOM-first.
- Read `references/browser-execution.md` before using direct Chrome/CDP, `observe / act / verify / journal / distill`, or low-level request capture.
- Read `references/verification.md` for structured completion checks.
- Read `references/safety.md` before any caution or dangerous action.
- Read `references/workflow-distillation.md` after a workflow succeeds and should become a reusable skill, script, CLI command, or adapter draft.
- Read `references/workflow-reuse.md` for the generated reusable package contract.
- Read `references/verification-and-journal.md` before claiming the task is complete or distilling a reusable workflow.
- Read `PLAN.md` for the implementation roadmap for this repository.

## Common Mistakes

- Acting before observing the page.
- Running one large script without readback checkpoints.
- Treating a clicked button as success without checking resulting state.
- Submitting, publishing, deleting, sending, paying, or bulk modifying without explicit user confirmation.
- Forgetting to record evidence, which makes the workflow impossible to debug or reuse.
- Stopping at `workflow.md` when the workflow will be repeated; generate a reusable package with `distill --output-dir`.
