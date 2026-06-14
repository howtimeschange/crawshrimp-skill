# Network Intelligence

## When To Inspect Requests

Use network capture when DOM evidence is missing, stale, or less reliable than the page's own request path.

Good candidates:

- export buttons that call an API before downloading
- detail drawers backed by JSON payloads
- false empty or false busy states
- pagination where the UI hides total count
- file URLs that can be downloaded more safely than clicked

## When To Stay DOM-First

Stay DOM-first when:

- user-visible page state is the source of truth
- the task is about form state or active account context
- the request contains sensitive or unstable auth payloads
- replaying the request would bypass business UI checks

## Capture Rules

Redact tokens, cookies, signatures, passwords, and session fields before writing request evidence into reusable notes.

Treat a captured endpoint as a clue. It becomes an adapter strategy only after it supports recovery, pagination, auth reality, and verification.
