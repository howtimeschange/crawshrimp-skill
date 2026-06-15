# Browser Execution Layer

## Default Entry

Use `scripts/web_operator.py` for agent-facing work. It exposes the five protocol verbs:

- `observe`: get a normalized page model
- `act`: run one safe browser action
- `verify`: evaluate completion evidence
- `journal`: create or write an evidence journal
- `distill`: turn the journal into workflow or adapter draft notes

For every webpage task, default to the user's already-open Chrome CDP endpoint:

```bash
python3 scripts/web_operator.py observe --cdp-url http://127.0.0.1:9222 --url-prefix https://example.com --task "inspect current page" --journal run.json
python3 scripts/browser_executor.py cdp --cdp-url http://127.0.0.1:9222 --url-prefix https://example.com observe
python3 scripts/browser_executor.py cdp --cdp-url http://127.0.0.1:9222 --url-prefix https://example.com eval --script "document.title"
```

If this lands on a login page or unexpected host, check the 9222 tab list and target host before asking the user to authenticate. A fresh browser, in-app browser, or extension path often lacks the cookies, runtime state, and active page context that the user already prepared.

## API-First Operation

After observation, prefer the page's own API or request path over manual clicking:

- frontend modules, stores, route actions, or request wrappers already loaded by the page
- observed API endpoints and payload shapes from capture output
- in-page `fetch` that runs inside the current page context
- direct file/export/download URLs that can be verified without brittle UI steps

DOM clicks and coordinate actions are fallback surfaces. Use them when the API path is unavailable, unsafe, unverifiable, or when a visible interaction is the user's actual target. UI is still valuable for readback and verification after an API-first action.

## High-Level Operator

Start from the 9222 browser, then use:

```bash
python3 scripts/web_operator.py observe --cdp-url http://127.0.0.1:9222 --url-prefix https://example.com --task "read report" --journal run.json
python3 scripts/browser_executor.py cdp --cdp-url http://127.0.0.1:9222 --url-prefix https://example.com capture --capture-mode passive --matches-json '[{"url_contains":"/api/"}]' --include-response-body
python3 scripts/browser_executor.py cdp --cdp-url http://127.0.0.1:9222 --url-prefix https://example.com eval --script "document.title"
python3 scripts/web_operator.py verify --url-prefix https://example.com --expression "document.body.innerText.includes('sku123')" --evidence "SKU filter is visible" --journal run.json
python3 scripts/web_operator.py verify --check table-rows-min --target table --minimum 1 --evidence "table has rows" --journal run.json
python3 scripts/web_operator.py verify --check file-exists --target report.csv --download-dir ~/Downloads --evidence "report file exists" --journal run.json
python3 scripts/web_operator.py distill --journal run.json --output workflow.md
python3 scripts/web_operator.py distill --journal run.json --output-dir reusable-workflow --name sku-report --include-skill
```

If the API path cannot solve the task safely, use fallback UI actions one at a time:

```bash
python3 scripts/web_operator.py act click --url-prefix https://example.com --selector "button.export" --reason "fallback: open export menu after API path was unavailable" --journal run.json
python3 scripts/web_operator.py act type --url-prefix https://example.com --selector "input.search" --value "sku123" --reason "fallback: visible search is the available control" --journal run.json
python3 scripts/web_operator.py act download --url-prefix https://example.com --selector "a.export" --expected-file report.csv --download-dir ~/Downloads --reason "fallback: download URL was not exposed" --journal run.json
```

The operator uses `Runtime.evaluate` for DOM snapshots, page-context API calls, DOM actions, and verification checks. It intentionally runs one small action at a time so the agent can re-observe or verify before continuing.

When `--journal` points to an existing file, `observe`, `act`, and `verify` load it and append the next evidence item instead of replacing the route.

Download actions snapshot the download directory before clicking and then wait for a new nonempty file. Upload actions use the backend's CDP file-input primitive.

## Low-Level CDP

Use `scripts/browser_executor.py` for primitive access:

```bash
python3 scripts/browser_executor.py cdp --cdp-url http://127.0.0.1:9222 --url-prefix https://example.com observe
python3 scripts/browser_executor.py cdp --tab-id <tab-id> eval --script "document.title"
python3 scripts/browser_executor.py cdp --tab-id <tab-id> click --x 120 --y 240
python3 scripts/browser_executor.py cdp --tab-id <tab-id> navigate --url https://example.com/report
python3 scripts/browser_executor.py cdp --tab-id <tab-id> capture --capture-mode passive --matches-json '[{"url_contains":"/api/"}]'
```

Low-level CDP actions map to:

- `Runtime.evaluate` for `eval`
- `Input.dispatchMouseEvent` for `click`
- `Page.navigate` for `navigate`
- `DOM.setFileInputFiles` for `upload`
- `Network.responseReceived` for `capture`

Direct CDP observe currently returns tab-level metadata. Use `eval` with page-model snippets when you need deeper DOM or accessibility structure.

The higher-level `web_operator.py observe` runs a DOM snapshot and is usually better for page modeling. Use low-level direct CDP observe when choosing a tab or debugging the endpoint itself.

## Safety Rules

- Browser execution is not permission to perform dangerous actions.
- Prefer the page-owned API/request path before manual page clicking, while keeping credentials inside page context.
- Coordinate clicks are less self-explanatory than selector or role clicks; journal why the coordinate is safe.
- For submit, publish, send, delete, pay, purchase, confirm, or bulk modify, stop and request explicit user confirmation before calling the backend.
- For enterprise form save/submit, require explicit authorization naming the change unless the user's instruction already gives that authorization.
- Do not read cookies, localStorage, sessionStorage, auth headers, tokens, or secrets just because CDP makes them accessible.
- When an explicitly authorized task uses the page's own API or in-page `fetch`, keep session credentials inside page context and never print, persist, journal, or reuse them outside the current browser session. Log sanitized endpoint, payload shape, and response status instead.
- After each backend action, re-observe or run a verification eval before continuing.

## Failure Handling

- If CDP reports multiple matching tabs, ask for `--tab-id`.
- If CDP cannot connect to `http://127.0.0.1:9222`, ask the user to start or expose the prepared Chrome session with remote debugging before falling back to a non-authenticated browser.
- If a page re-renders after an action, discard stale control assumptions and observe again.
