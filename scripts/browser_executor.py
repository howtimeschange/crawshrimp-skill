#!/usr/bin/env python3
"""Browser execution backends for the crawshrimp web-agent protocol.

The supported runtime backend is direct Chrome CDP: connect to a Chrome
instance with remote debugging enabled and run observation, action, and
network-capture primitives without depending on the crawshrimp app backend.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

try:
    from scripts.web_agent_protocol import PageState
except ModuleNotFoundError:
    from web_agent_protocol import PageState


JsonPayload = dict[str, Any] | list[Any] | str | int | float | bool | None


@dataclass(frozen=True)
class BrowserAction:
    kind: str
    script: str = ""
    selector: str = ""
    text: str = ""
    value: str | None = None
    files: list[str] = field(default_factory=list)
    url: str = ""
    x: float | None = None
    y: float | None = None
    capture_mode: str = "passive"
    matches: list[dict[str, Any]] = field(default_factory=list)
    timeout_ms: int = 8000
    settle_ms: int = 1000
    user_gesture: bool = False


@dataclass(frozen=True)
class BrowserResult:
    ok: bool
    action: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def snapshot_download_dir(download_dir: Path | str) -> dict[str, dict[str, int]]:
    directory = Path(download_dir).expanduser()
    snapshot: dict[str, dict[str, int]] = {}
    if not directory.exists() or not directory.is_dir():
        return snapshot
    for path in directory.iterdir():
        if not path.is_file() or path.name.endswith(".crdownload"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        snapshot[str(path)] = {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}
    return snapshot


def find_new_download(
    download_dir: Path | str,
    baseline: dict[str, dict[str, int]],
    *,
    expected_file: str = "",
    started_at_ns: int | None = None,
) -> dict[str, Any] | None:
    directory = Path(download_dir).expanduser()
    if not directory.exists() or not directory.is_dir():
        return None
    expected_name = Path(str(expected_file or "")).name
    threshold_ns = max(int(started_at_ns or 0) - 2_000_000_000, 0)
    newest: tuple[int, Path, int] | None = None
    for path in directory.iterdir():
        if not path.is_file() or path.name.endswith(".crdownload"):
            continue
        if expected_name and path.name != expected_name:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        previous = baseline.get(str(path))
        if previous and stat.st_mtime_ns <= int(previous.get("mtime_ns") or 0) and stat.st_size == int(previous.get("size") or 0):
            continue
        if stat.st_mtime_ns < threshold_ns:
            continue
        if newest is None or stat.st_mtime_ns > newest[0]:
            newest = (stat.st_mtime_ns, path, stat.st_size)
    if newest is None:
        return None
    _, path, size = newest
    return {
        "path": str(path),
        "filename": path.name,
        "bytes": size,
        "download_dir": str(directory),
    }


def _json_request(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None, timeout: float = 30) -> JsonPayload:
    request_headers = dict(headers or {})
    data = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers=request_headers, method=method)
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        raise RuntimeError(f"HTTP {exc.code}: {body or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


async def _websocket_send(ws_url: str, message: dict[str, Any], timeout: float = 10) -> dict[str, Any]:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("Chrome CDP WebSocket support requires the 'websockets' package.") from exc

    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024, proxy=None) as ws:
        await ws.send(json.dumps(message))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            payload = json.loads(raw)
            if payload.get("id") == message.get("id"):
                return payload


def _request_matches(entry: dict[str, Any], matches: list[dict[str, Any]] | None) -> bool:
    if not matches:
        return True
    url = str(entry.get("url") or "")
    method = str(entry.get("method") or "").upper()
    for rule in matches:
        if not isinstance(rule, dict):
            continue
        url_contains = str(rule.get("url_contains") or rule.get("contains") or "").strip()
        url_equals = str(rule.get("url") or rule.get("url_equals") or "").strip()
        method_equals = str(rule.get("method") or "").strip().upper()
        if url_contains and url_contains not in url:
            continue
        if url_equals and url_equals != url:
            continue
        if method_equals and method_equals != method:
            continue
        return True
    return False


def _click_messages(x: float, y: float) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for event_type in ("mouseMoved", "mousePressed", "mouseReleased"):
        params: dict[str, Any] = {"type": event_type, "x": x, "y": y, "modifiers": 0}
        if event_type == "mouseMoved":
            params.update({"button": "none", "clickCount": 0})
        elif event_type == "mousePressed":
            params.update({"button": "left", "clickCount": 1, "buttons": 1})
        else:
            params.update({"button": "left", "clickCount": 1, "buttons": 0})
        messages.append({"method": "Input.dispatchMouseEvent", "params": params})
    return messages


async def _websocket_capture(
    ws_url: str,
    setup_messages: list[dict[str, Any]],
    timeout_ms: int,
    trigger: list[dict[str, Any]] | None = None,
    matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("Chrome CDP WebSocket support requires the 'websockets' package.") from exc

    next_id = 0
    matched: list[dict[str, Any]] = []
    seen: set[str] = set()

    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024, proxy=None) as ws:
        async def send(method: str, params: dict[str, Any] | None = None) -> None:
            nonlocal next_id
            next_id += 1
            await ws.send(json.dumps({"id": next_id, "method": method, "params": params or {}}))

        for message in setup_messages:
            await send(str(message.get("method")), message.get("params") or {})
        if trigger:
            for message in trigger:
                await send(str(message.get("method")), message.get("params") or {})

        deadline = asyncio.get_event_loop().time() + max(timeout_ms, 1000) / 1000
        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            payload = json.loads(raw)
            if payload.get("method") != "Network.responseReceived":
                continue
            params = payload.get("params") or {}
            request_id = str(params.get("requestId") or "")
            response = params.get("response") or {}
            entry = {
                "request_id": request_id,
                "url": response.get("url") or "",
                "status": response.get("status"),
                "mime_type": response.get("mimeType") or "",
                "method": (params.get("request") or {}).get("method") or "",
            }
            if request_id and request_id not in seen and _request_matches(entry, matches):
                seen.add(request_id)
                matched.append(entry)
    return {"matches": matched, "total": len(matched)}


def _safe_list(raw: Any) -> list[Any]:
    return raw if isinstance(raw, list) else []


def _control_name(item: dict[str, Any]) -> str:
    for key in ("name", "text", "label", "placeholder", "title", "ariaLabel", "selector"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def normalize_crawshrimp_snapshot(snapshot: dict[str, Any]) -> PageState:
    dom = snapshot.get("dom") or snapshot
    controls: list[dict[str, Any]] = []

    for item in _safe_list(dom.get("buttons")):
        if isinstance(item, dict):
            controls.append({"role": "button", "name": _control_name(item), **item})
    for item in _safe_list(dom.get("inputs")):
        if isinstance(item, dict):
            controls.append({"role": "input", "name": _control_name(item), **item})
    for key, role in (("selects", "select"), ("links", "link"), ("tabs", "tab"), ("menus", "menu")):
        for item in _safe_list(dom.get(key)):
            if isinstance(item, dict):
                controls.append({"role": role, "name": _control_name(item), **item})

    visible_text: list[str] = []
    for key in ("headings", "visible_text", "texts"):
        for value in _safe_list(dom.get(key)):
            if isinstance(value, str) and value.strip():
                visible_text.append(value.strip())

    network: list[dict[str, Any]] = []
    knowledge = snapshot.get("knowledge") or {}
    for card in _safe_list(knowledge.get("cards")):
        if isinstance(card, dict):
            network.append({"kind": "knowledge", **card})
    for item in _safe_list(dom.get("resources")):
        if isinstance(item, dict):
            network.append({"kind": "resource", **item})
    for item in _safe_list(dom.get("network")):
        if isinstance(item, dict):
            network.append(item)

    return PageState(
        url=str(dom.get("url") or ""),
        title=str(dom.get("title") or ""),
        visible_text=visible_text,
        controls=controls,
        tables=[item for item in _safe_list(dom.get("tables")) if isinstance(item, dict)],
        downloads=[item for item in _safe_list(dom.get("downloads")) if isinstance(item, dict)],
        network=network,
        blocking_states=[item for item in _safe_list(dom.get("blocking_states")) if isinstance(item, dict)],
        context=dom.get("context") if isinstance(dom.get("context"), dict) else {},
        active_regions=[item for item in _safe_list(dom.get("active_regions")) if isinstance(item, dict)],
        accessibility=[item for item in _safe_list(dom.get("accessibility")) if isinstance(item, dict)],
    )


class ChromeCDPBackend:
    def __init__(
        self,
        *,
        cdp_url: str = "http://127.0.0.1:9222",
        tab_id: str = "",
        url_prefix: str = "",
        get_json: Callable[[str], JsonPayload] | None = None,
        send_ws: Callable[[str, dict[str, Any], float], Any] | None = None,
        capture_ws: Callable[[str, list[dict[str, Any]], int, list[dict[str, Any]] | None, list[dict[str, Any]] | None], Any] | None = None,
    ) -> None:
        self.cdp_url = cdp_url.rstrip("/")
        self.tab_id = tab_id
        self.url_prefix = url_prefix
        self._get_json = get_json
        self._send_ws = send_ws or _websocket_send
        self._capture_ws = capture_ws or _websocket_capture
        self._message_id = 0

    def _next_id(self) -> int:
        self._message_id += 1
        return self._message_id

    def _get(self, path: str) -> JsonPayload:
        if self._get_json:
            return self._get_json(path)
        return _json_request(self.cdp_url + path)

    def list_tabs(self) -> list[dict[str, Any]]:
        tabs = self._get("/json")
        return [tab for tab in _safe_list(tabs) if isinstance(tab, dict) and tab.get("type") == "page"]

    def select_tab(self) -> dict[str, Any]:
        tabs = self.list_tabs()
        if self.tab_id:
            for tab in tabs:
                if str(tab.get("id")) == self.tab_id:
                    return tab
            raise RuntimeError(f"Chrome tab not found: {self.tab_id}")
        if self.url_prefix:
            candidates = [tab for tab in tabs if str(tab.get("url") or "").startswith(self.url_prefix)]
            if len(candidates) == 1:
                return candidates[0]
            if not candidates:
                raise RuntimeError(f"No Chrome tab matches URL prefix: {self.url_prefix}")
            raise RuntimeError(f"Multiple Chrome tabs match URL prefix: {self.url_prefix}")
        if len(tabs) == 1:
            return tabs[0]
        raise RuntimeError("Specify --tab-id or --url-prefix when multiple Chrome tabs are open.")

    def observe(self) -> PageState:
        tab = self.select_tab()
        return PageState(
            url=str(tab.get("url") or ""),
            title=str(tab.get("title") or ""),
            visible_text=[str(tab.get("title") or "").strip()] if str(tab.get("title") or "").strip() else [],
        )

    async def _send(self, method: str, params: dict[str, Any] | None = None, *, timeout: float = 10) -> dict[str, Any]:
        tab = self.select_tab()
        ws_url = str(tab.get("webSocketDebuggerUrl") or "")
        if not ws_url:
            raise RuntimeError("Selected Chrome tab does not expose webSocketDebuggerUrl.")
        message = {"id": self._next_id(), "method": method, "params": params or {}}
        result = self._send_ws(ws_url, message, timeout)
        if hasattr(result, "__await__"):
            return await result
        return result

    async def execute_async(self, action: BrowserAction) -> BrowserResult:
        kind = action.kind.strip().lower()
        if kind == "eval":
            response = await self._send(
                "Runtime.evaluate",
                {
                    "expression": action.script,
                    "awaitPromise": True,
                    "returnByValue": True,
                    "userGesture": bool(action.user_gesture),
                    "timeout": action.timeout_ms,
                },
                timeout=max(action.timeout_ms / 1000 + 5, 10),
            )
            if response.get("error"):
                return BrowserResult(ok=False, action=kind, error=json.dumps(response["error"], ensure_ascii=False))
            result = ((response.get("result") or {}).get("result") or {})
            exception = (response.get("result") or {}).get("exceptionDetails")
            if exception:
                return BrowserResult(ok=False, action=kind, data=result, error=json.dumps(exception, ensure_ascii=False))
            return BrowserResult(ok=True, action=kind, data=result)
        if kind == "click":
            if action.x is None or action.y is None:
                raise ValueError("CDP click requires x and y coordinates.")
            try:
                await self._send("Page.bringToFront", {})
            except Exception:
                pass
            for message in _click_messages(action.x, action.y):
                await self._send(message["method"], message["params"])
            return BrowserResult(ok=True, action=kind, data={"x": action.x, "y": action.y})
        if kind == "navigate":
            if not action.url:
                raise ValueError("CDP navigate requires url.")
            try:
                await self._send("Page.enable", {})
            except Exception:
                pass
            response = await self._send("Page.navigate", {"url": action.url})
            if response.get("error"):
                return BrowserResult(ok=False, action=kind, error=json.dumps(response["error"], ensure_ascii=False))
            return BrowserResult(ok=True, action=kind, data={"url": action.url})
        if kind == "upload":
            if not action.files:
                raise ValueError("CDP upload requires files.")
            tab = self.select_tab()
            ws_url = str(tab.get("webSocketDebuggerUrl") or "")
            if not ws_url:
                raise RuntimeError("Selected Chrome tab does not expose webSocketDebuggerUrl.")
            selector = action.selector.strip()
            if not selector:
                raise ValueError("CDP upload requires selector.")
            files = [str(Path(path).expanduser().resolve()) for path in action.files]
            expression = f"""
(() => {{
  const input = document.querySelector({json.dumps(selector)});
  if (!input) return {{ ok: false, error: 'file input not found', selector: {json.dumps(selector)} }};
  return {{ ok: true, selector: {json.dumps(selector)} }};
}})()
""".strip()
            locate = await self._send(
                "Runtime.evaluate",
                {"expression": expression, "awaitPromise": True, "returnByValue": True},
            )
            value = (((locate.get("result") or {}).get("result") or {}).get("value") or {})
            if not value.get("ok"):
                return BrowserResult(ok=False, action=kind, error=str(value.get("error") or "file input not found"))
            describe = await self._send("DOM.getDocument", {"depth": -1, "pierce": True})
            root_id = (((describe.get("result") or {}).get("root") or {}).get("nodeId"))
            query = await self._send("DOM.querySelector", {"nodeId": root_id, "selector": selector})
            node_id = (query.get("result") or {}).get("nodeId")
            if not node_id:
                return BrowserResult(ok=False, action=kind, error=f"file input not found: {selector}")
            response = await self._send("DOM.setFileInputFiles", {"nodeId": node_id, "files": files})
            if response.get("error"):
                return BrowserResult(ok=False, action=kind, error=json.dumps(response["error"], ensure_ascii=False))
            return BrowserResult(ok=True, action=kind, data={"selector": selector, "files": files, "fileCount": len(files)})
        if kind == "capture":
            trigger: list[dict[str, Any]] | None = None
            if action.capture_mode == "click":
                if action.x is None or action.y is None:
                    raise ValueError("CDP capture click requires x and y coordinates.")
                trigger = _click_messages(action.x, action.y)
            elif action.capture_mode == "url":
                if not action.url:
                    raise ValueError("CDP capture url mode requires url.")
                trigger = [{"method": "Page.navigate", "params": {"url": action.url}}]
            elif action.capture_mode != "passive":
                raise ValueError(f"Unsupported CDP capture mode: {action.capture_mode}")
            tab = self.select_tab()
            ws_url = str(tab.get("webSocketDebuggerUrl") or "")
            if not ws_url:
                raise RuntimeError("Selected Chrome tab does not expose webSocketDebuggerUrl.")
            setup = [
                {"method": "Network.enable", "params": {}},
                {"method": "Page.enable", "params": {}},
                {"method": "Runtime.enable", "params": {}},
            ]
            capture = self._capture_ws(ws_url, setup, action.timeout_ms, trigger, action.matches)
            if hasattr(capture, "__await__"):
                capture = await capture
            return BrowserResult(ok=True, action=kind, data=capture if isinstance(capture, dict) else {"capture": capture})
        raise ValueError(f"Unsupported CDP action: {action.kind}")

    def execute(self, action: BrowserAction) -> BrowserResult:
        return asyncio.run(self.execute_async(action))


def _print_json(payload: Any) -> None:
    if hasattr(payload, "to_json"):
        print(payload.to_json())
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def _build_action(args: argparse.Namespace) -> BrowserAction:
    matches = json.loads(args.matches_json) if getattr(args, "matches_json", "") else []
    if not isinstance(matches, list):
        raise ValueError("--matches-json must be a JSON array")
    return BrowserAction(
        kind=args.action,
        script=getattr(args, "script", "") or "",
        url=getattr(args, "url", "") or "",
        x=getattr(args, "x", None),
        y=getattr(args, "y", None),
        capture_mode=getattr(args, "capture_mode", "passive"),
        matches=matches,
        timeout_ms=getattr(args, "timeout_ms", 8000),
        settle_ms=getattr(args, "settle_ms", 1000),
    )


def _command_cdp(args: argparse.Namespace) -> int:
    backend = ChromeCDPBackend(cdp_url=args.cdp_url, tab_id=args.tab_id, url_prefix=args.url_prefix)
    if args.action == "observe":
        _print_json(asdict(backend.observe()))
        return 0
    _print_json(backend.execute(_build_action(args)))
    return 0


def _add_action_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("action", choices=["observe", "eval", "click", "navigate", "capture"])
    parser.add_argument("--script", default="", help="JavaScript expression for eval")
    parser.add_argument("--url", default="", help="URL for navigate or capture-url mode")
    parser.add_argument("--x", type=float, default=None, help="X coordinate for CDP click or capture click")
    parser.add_argument("--y", type=float, default=None, help="Y coordinate for CDP click or capture click")
    parser.add_argument("--capture-mode", default="passive", choices=["passive", "click", "url"])
    parser.add_argument("--matches-json", default="", help="JSON array of request matchers")
    parser.add_argument("--timeout-ms", type=int, default=8000)
    parser.add_argument("--settle-ms", type=int, default=1000)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute web-agent protocol actions through direct Chrome CDP.")
    subparsers = parser.add_subparsers(dest="backend", required=True)

    cdp = subparsers.add_parser("cdp", help="Use direct Chrome CDP")
    cdp.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    cdp.add_argument("--tab-id", default="")
    cdp.add_argument("--url-prefix", default="")
    _add_action_arguments(cdp)
    cdp.set_defaults(func=_command_cdp)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
