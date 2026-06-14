#!/usr/bin/env python3
"""Generate reusable workflow assets from a successful web-agent journal."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts.web_operator import distill_workflow
except ModuleNotFoundError:
    from web_operator import distill_workflow


def _slugify(raw: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", raw.strip().lower()).strip("-")
    return slug or "web-workflow"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Journal must be a JSON object: {path}")
    return payload


def _commands_from_journal(journal: dict[str, Any], *, name: str) -> dict[str, Any]:
    observations = journal.get("observations") or []
    first_page = ((observations[0] or {}).get("page") or {}) if observations else {}
    actions = []
    for action in journal.get("actions") or []:
        if not isinstance(action, dict):
            continue
        kind = action.get("kind") or ""
        value = action.get("value")
        files = []
        if kind == "upload" and isinstance(value, str):
            files = [item for item in value.split(",") if item]
        actions.append({
            "kind": kind,
            "selector": action.get("target") or "",
            "value": action.get("value"),
            "url": value if kind == "navigate" else "",
            "files": files,
            "risk": action.get("risk") or "safe",
            "reason": action.get("reason") or "",
        })
    return {
        "name": name,
        "task": journal.get("task") or name,
        "start_url": first_page.get("url") or "",
        "title": first_page.get("title") or "",
        "actions": actions,
        "verifications": journal.get("verifications") or [],
    }


def _runner_source() -> str:
    return '''#!/usr/bin/env python3
"""Run a distilled web workflow through crawshrimp-skill's web_operator.py."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a reusable CDP web workflow.")
    parser.add_argument("--commands", default=str(Path(__file__).with_name("commands.json")))
    parser.add_argument("--operator", required=True, help="Path to crawshrimp-skill/scripts/web_operator.py")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9222")
    parser.add_argument("--tab-id", default="")
    parser.add_argument("--url-prefix", default="")
    parser.add_argument("--journal", default="workflow-run.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    commands = json.loads(Path(args.commands).read_text(encoding="utf-8"))
    base = [args.python, args.operator]
    browser_args = ["--cdp-url", args.cdp_url, "--task", commands.get("task") or commands.get("name") or "web workflow", "--journal", args.journal]
    if args.tab_id:
        browser_args += ["--tab-id", args.tab_id]
    if args.url_prefix:
        browser_args += ["--url-prefix", args.url_prefix]

    steps = [base + ["observe"] + browser_args]
    for action in commands.get("actions") or []:
        step = base + ["act", action.get("kind") or "click"] + browser_args
        if action.get("kind") == "navigate" and action.get("url"):
            step += ["--url", action["url"]]
        elif action.get("selector"):
            step += ["--selector", action["selector"]]
        for file_path in action.get("files") or []:
            step += ["--file", file_path]
        if action.get("value") is not None and action.get("kind") not in {"navigate", "upload"}:
            step += ["--value", str(action["value"])]
        if action.get("reason"):
            step += ["--reason", action["reason"]]
        if action.get("risk"):
            step += ["--risk", action["risk"]]
        steps.append(step)

    for verification in commands.get("verifications") or []:
        check = verification.get("check") if isinstance(verification, dict) else {}
        evidence = str((verification or {}).get("evidence") or "workflow verification")
        if isinstance(check, dict) and check.get("kind"):
            step = base + ["verify"] + browser_args + ["--check", str(check["kind"]), "--target", str(check.get("target") or check.get("path") or ""), "--evidence", evidence]
            if check.get("minimum") is not None:
                step += ["--minimum", str(check["minimum"])]
            steps.append(step)

    for step in steps:
        print(" ".join(step))
        if not args.dry_run:
            subprocess.run(step, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _skill_source(commands: dict[str, Any]) -> str:
    name = _slugify(str(commands.get("name") or "web-workflow"))
    task = str(commands.get("task") or name)
    return f'''---
name: {name}
description: Use when repeating the proven browser workflow for: {task}
---

# {name}

Run this reusable workflow with `run_workflow.py`. It expects Chrome CDP and the parent `crawshrimp-skill/scripts/web_operator.py`.

## Workflow

- Task: {task}
- Start URL: {commands.get("start_url") or ""}
- Actions: {len(commands.get("actions") or [])}

## Safety

Review `commands.json` before running. Dangerous submit, publish, send, delete, pay, purchase, confirm, or bulk-modify actions must still require explicit user confirmation.
'''


def build_reusable_workflow(
    *,
    journal_path: Path,
    output_dir: Path,
    name: str = "",
    include_skill: bool = False,
) -> dict[str, Any]:
    journal = _load_json(journal_path)
    workflow_name = _slugify(name or str(journal.get("task") or "web-workflow"))
    output_dir.mkdir(parents=True, exist_ok=True)

    commands = _commands_from_journal(journal, name=workflow_name)
    (output_dir / "workflow.md").write_text(distill_workflow(journal), encoding="utf-8")
    (output_dir / "commands.json").write_text(json.dumps(commands, ensure_ascii=False, indent=2), encoding="utf-8")
    runner = output_dir / "run_workflow.py"
    runner.write_text(_runner_source(), encoding="utf-8")
    runner.chmod(0o755)
    if include_skill:
        (output_dir / "SKILL.md").write_text(_skill_source(commands), encoding="utf-8")

    return {
        "name": workflow_name,
        "output_dir": str(output_dir),
        "files": sorted(item.name for item in output_dir.iterdir() if item.is_file()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build reusable workflow assets from a web-agent journal.")
    parser.add_argument("--journal", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--name", default="")
    parser.add_argument("--include-skill", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_reusable_workflow(
        journal_path=Path(args.journal),
        output_dir=Path(args.output_dir),
        name=args.name,
        include_skill=args.include_skill,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
