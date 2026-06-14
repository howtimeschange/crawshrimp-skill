import asyncio
import unittest
from pathlib import Path

from scripts.browser_executor import (
    BrowserAction,
    ChromeCDPBackend,
    normalize_crawshrimp_snapshot,
)


class BrowserExecutorTest(unittest.TestCase):
    def test_normalizes_crawshrimp_snapshot_to_page_state(self):
        snapshot = {
            "dom": {
                "url": "https://example.test/orders",
                "title": "Orders",
                "headings": ["Orders"],
                "buttons": [{"text": "Export", "selector": "button.export"}],
                "inputs": [{"placeholder": "Search", "selector": "input"}],
                "tables": [{"caption": "Order table", "rows": 2}],
            },
            "knowledge": {"cards": [{"title": "existing note"}]},
        }

        page = normalize_crawshrimp_snapshot(snapshot)

        self.assertEqual(page.url, "https://example.test/orders")
        self.assertEqual(page.title, "Orders")
        self.assertIn("Orders", page.visible_text)
        self.assertEqual(page.controls[0]["name"], "Export")
        self.assertEqual(page.controls[1]["role"], "input")
        self.assertEqual(page.tables[0]["rows"], 2)
        self.assertEqual(page.network[0]["kind"], "knowledge")

    def test_chrome_cdp_backend_lists_tabs_and_sends_runtime_evaluate(self):
        sent_messages = []
        tabs = [
            {
                "id": "tab-1",
                "type": "page",
                "url": "https://example.test",
                "title": "Example",
                "webSocketDebuggerUrl": "ws://example.test/devtools/page/tab-1",
            }
        ]

        async def fake_ws_send(ws_url, message, timeout):
            sent_messages.append((ws_url, message))
            self.assertEqual(ws_url, "ws://example.test/devtools/page/tab-1")
            if message["method"] == "Runtime.evaluate":
                return {"id": message["id"], "result": {"result": {"value": {"answer": 42}}}}
            return {"id": message["id"], "result": {}}

        backend = ChromeCDPBackend(
            cdp_url="http://127.0.0.1:9222",
            tab_id="tab-1",
            get_json=lambda path: tabs if path == "/json" else None,
            send_ws=fake_ws_send,
        )

        result = asyncio.run(backend.execute_async(BrowserAction(kind="eval", script="({ answer: 42 })")))

        self.assertTrue(result.ok)
        self.assertEqual(result.data["value"], {"answer": 42})
        self.assertEqual(sent_messages[0][1]["method"], "Runtime.evaluate")
        self.assertTrue(sent_messages[0][1]["params"]["awaitPromise"])

    def test_chrome_cdp_backend_sends_click_and_navigate_actions(self):
        sent_methods = []
        tabs = [
            {
                "id": "tab-1",
                "type": "page",
                "url": "https://example.test",
                "title": "Example",
                "webSocketDebuggerUrl": "ws://example.test/devtools/page/tab-1",
            }
        ]

        async def fake_ws_send(ws_url, message, timeout):
            sent_methods.append((message["method"], message.get("params") or {}))
            return {"id": message["id"], "result": {}}

        backend = ChromeCDPBackend(
            tab_id="tab-1",
            get_json=lambda path: tabs if path == "/json" else None,
            send_ws=fake_ws_send,
        )

        click_result = asyncio.run(backend.execute_async(BrowserAction(kind="click", x=12, y=34)))
        nav_result = asyncio.run(
            backend.execute_async(BrowserAction(kind="navigate", url="https://example.test/next"))
        )

        self.assertTrue(click_result.ok)
        self.assertTrue(nav_result.ok)
        methods = [method for method, _ in sent_methods]
        self.assertIn("Page.bringToFront", methods)
        self.assertEqual(methods.count("Input.dispatchMouseEvent"), 3)
        self.assertIn("Page.navigate", methods)

    def test_chrome_cdp_backend_sets_file_input_files_for_upload(self):
        sent = []
        tabs = [
            {
                "id": "tab-1",
                "type": "page",
                "url": "https://example.test",
                "title": "Example",
                "webSocketDebuggerUrl": "ws://example.test/devtools/page/tab-1",
            }
        ]

        async def fake_ws_send(ws_url, message, timeout):
            sent.append((message["method"], message.get("params") or {}))
            method = message["method"]
            if method == "Runtime.evaluate":
                return {"id": message["id"], "result": {"result": {"value": {"ok": True, "selector": "input[type=file]"}}}}
            if method == "DOM.getDocument":
                return {"id": message["id"], "result": {"root": {"nodeId": 1}}}
            if method == "DOM.querySelector":
                return {"id": message["id"], "result": {"nodeId": 7}}
            return {"id": message["id"], "result": {}}

        backend = ChromeCDPBackend(
            tab_id="tab-1",
            get_json=lambda path: tabs if path == "/json" else None,
            send_ws=fake_ws_send,
        )

        result = asyncio.run(
            backend.execute_async(
                BrowserAction(kind="upload", selector="input[type=file]", files=["/tmp/report.csv"])
            )
        )

        self.assertTrue(result.ok)
        methods = [method for method, _ in sent]
        self.assertIn("DOM.setFileInputFiles", methods)
        upload_params = [params for method, params in sent if method == "DOM.setFileInputFiles"][0]
        self.assertEqual(upload_params["nodeId"], 7)
        self.assertEqual(upload_params["files"], [str(Path("/tmp/report.csv").resolve())])

    def test_chrome_cdp_backend_captures_network_requests(self):
        tabs = [
            {
                "id": "tab-1",
                "type": "page",
                "url": "https://example.test",
                "title": "Example",
                "webSocketDebuggerUrl": "ws://example.test/devtools/page/tab-1",
            }
        ]

        async def fake_capture(ws_url, setup_messages, timeout_ms, trigger=None, matches=None):
            self.assertEqual(ws_url, "ws://example.test/devtools/page/tab-1")
            self.assertIn("Network.enable", [item["method"] for item in setup_messages])
            if trigger:
                self.assertEqual(trigger[0]["method"], "Input.dispatchMouseEvent")
            return {
                "matches": [
                    {"url": "https://example.test/api/orders", "method": "GET", "status": 200},
                ],
                "total": 1,
            }

        backend = ChromeCDPBackend(
            tab_id="tab-1",
            get_json=lambda path: tabs if path == "/json" else None,
            capture_ws=fake_capture,
        )

        passive = asyncio.run(
            backend.execute_async(
                BrowserAction(kind="capture", capture_mode="passive", matches=[{"url_contains": "/api/"}])
            )
        )
        click = asyncio.run(
            backend.execute_async(BrowserAction(kind="capture", capture_mode="click", x=12, y=34))
        )

        self.assertTrue(passive.ok)
        self.assertEqual(passive.data["matches"][0]["url"], "https://example.test/api/orders")
        self.assertTrue(click.ok)


if __name__ == "__main__":
    unittest.main()
