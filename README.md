# Crawshrimp Skill

面向 AI agent 的网页操作协议与 CDP 自动化 skill。它的目标不是先写一个固定脚本，而是让 agent 把网页当成一个可以观察、建模、执行、验证和复用的环境。

This is a web-operation protocol and CDP automation skill for AI agents. Instead of starting from a fixed script, it lets an agent treat a webpage as an environment that can be observed, modeled, acted on, verified, journaled, and distilled into reusable automation.

## 中文说明

### 这个项目是什么

`crawshrimp-skill` 借鉴抓虾项目的网页自动化经验，为 Codex/AI agent 提供一套通用的网页任务执行协议：

```text
用户目标 -> observe -> 建立页面模型 -> plan -> act -> verify -> journal -> distill
```

它有两个明确目的：

1. 复用抓虾式 CDP 浏览器自动化能力，让 AI agent 可以通过 Chrome DevTools Protocol 操控页面、读取状态、执行安全动作并完成网页任务。
2. 把已经跑通的自动化路线固化下来，生成 workflow、脚本、CLI 命令或新的 skill 草稿，方便下次复用。

### 已实现能力

- `observe`：读取 URL、标题、可见文本、按钮/输入框/选择器/链接、表格、下载目录、弹窗/抽屉/浮层、危险按钮线索、资源请求线索和 accessibility-ish 控件列表。
- `act`：小步执行 `click`、`type`、`select`、`upload`、`download`、`wait`、`navigate`、`paginate`。
- 抓虾执行态兼容：adapter/task registry、auth check、knowledge service、probe bundle、framework/network snapshot、JSRunner 式 phase/shared runtime、file chooser 上传、wheel capture、请求捕获 `min_matches`/响应体选项、并发 URL 下载、browser-session URL 下载、点击下载 transient tab 处理和刷新恢复。
- `verify`：支持手写 JS expression，也支持结构化断言：`text`、`url`、`selector-exists`、`table-rows-min`、`file-exists`。
- `journal`：跨命令读取并追加同一个 JSON journal，记录 observation、action、verification、failure 和 recovery。
- `distill`：从 journal 生成 workflow 草稿，也可以生成可复用目录：`workflow.md`、`commands.json`、`run_workflow.py`，可选生成新的 `SKILL.md`。
- 安全边界：默认阻止 `submit`、`publish`、`send`、`delete`、`pay`、`purchase`、`confirm`、`bulk_modify` 等危险动作，除非用户明确确认。
- 测试与校验：包含 `unittest` 测试和 `quick_validate.py` 仓库结构检查。

### 适合的任务

- 读取型：抓表格、搜索信息、导出页面数据、总结页面内容。
- 操作型：筛选、翻页、打开详情、下载文件、填写表单但不提交危险动作。
- 流程型：多页面、多弹窗、多步骤任务，完成后输出证据链并沉淀为可复用流程。

### 快速开始

安装依赖：

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

启动一个带远程调试端口的 Chrome，例如：

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/crawshrimp-skill-chrome
```

打开目标网页后，使用高层操作协议：

```bash
python3 scripts/web_operator.py observe \
  --url-prefix https://example.com \
  --task "总结页面内容" \
  --journal run.json

python3 scripts/web_operator.py act click \
  --url-prefix https://example.com \
  --selector "button.export" \
  --reason "打开导出菜单" \
  --journal run.json

python3 scripts/web_operator.py act upload-chooser \
  --url-prefix https://example.com \
  --clicks-json '[{"x":120,"y":240}]' \
  --file ./input.csv \
  --reason "通过原生文件选择器上传" \
  --journal run.json

python3 scripts/web_operator.py act capture-wheel \
  --url-prefix https://example.com \
  --wheels-json '[{"x":640,"y":520,"delta_y":900}]' \
  --value '[{"url_contains":"/api/"}]' \
  --reason "捕获滚动懒加载请求" \
  --journal run.json

python3 scripts/web_operator.py verify \
  --url-prefix https://example.com \
  --check text \
  --target "Export" \
  --evidence "导出菜单已出现" \
  --journal run.json

python3 scripts/web_operator.py distill \
  --journal run.json \
  --output-dir reusable-workflow \
  --name example-export \
  --include-skill
```

也可以使用底层 CDP 工具：

```bash
python3 scripts/browser_executor.py cdp \
  --url-prefix https://example.com \
  observe

python3 scripts/browser_executor.py cdp \
  --url-prefix https://example.com \
  eval \
  --script "document.title"

python3 scripts/browser_executor.py cdp \
  --url-prefix https://example.com \
  capture \
  --capture-mode url \
  --url https://example.com/report \
  --matches-json '[{"url_contains":"/api/report","method":"GET"}]' \
  --min-matches 1 \
  --include-response-body
```

抓虾式 adapter/knowledge/probe/phase 工具：

```bash
python3 scripts/adapter_registry.py --root adapters scan
python3 scripts/knowledge_service.py --adapters-root adapters --probes-root probes --data-root knowledge rebuild
python3 scripts/knowledge_service.py --data-root knowledge search --query "export drawer" --adapter temu --task goods_traffic_detail
python3 scripts/phase_runner.py --url-prefix https://example.com --file adapters/demo/orders.js --params-json '{"keyword":"sku"}' --artifact-dir artifacts
```

`phase_runner.py` 支持抓虾脚本返回这些 `meta.action`：`cdp_clicks`、`inject_files`、`file_chooser_upload`、`capture_click_requests`、`capture_url_requests`、`capture_wheel_requests`、`download_urls`、`download_clicks`、`reload_page`、`next_phase`、`complete`、`abort`。`download_urls` 可通过 `browser_session`/`browserSession` 走临时浏览器标签页下载，适合需要登录态或浏览器下载行为的导出链接。

任务分类和计划模板：

```bash
python3 scripts/web_agent_protocol.py classify "筛选近7天并下载导出文件"
python3 scripts/web_agent_protocol.py plan "筛选近7天并下载导出文件"
python3 scripts/web_agent_protocol.py journal-template "多页面收集详情证据"
```

### 验证

```bash
python3 -m unittest
python3 -m unittest discover -s tests
python3 quick_validate.py .
python3 -m compileall scripts tests quick_validate.py
```

### 项目结构

```text
crawshrimp-skill/
  SKILL.md                      # Codex skill 入口
  PLAN.md                       # 项目目标、范围和路线
  agents/openai.yaml            # agent 展示元数据
  references/                   # 协议、观察、动作、安全、验证、沉淀文档
  scripts/
    web_agent_protocol.py       # 任务分类、计划、数据结构、安全检查、journal
    adapter_registry.py         # 抓虾式 adapter/task manifest registry
    browser_executor.py         # 直接 Chrome/CDP 后端
    knowledge_service.py        # notes/probe bundle 知识卡片索引与搜索
    probe_bundle.py             # probe bundle 生成、endpoint 分析、敏感信息脱敏
    phase_runner.py             # JSRunner 式 phase/shared 多阶段运行时
    runtime_downloads.py        # 并发 URL 下载、点击下载、artifact 管理
    web_operator.py             # observe/act/verify/journal/distill 高层 CLI
    workflow_builder.py         # 从成功 journal 生成可复用 workflow 包
  tests/                        # unittest 测试
  quick_validate.py             # skill 结构校验
```

### 当前边界

这个仓库已经复刻并抽象了抓虾的主要执行态能力，但它仍不是完整的抓虾桌面应用：没有 GUI、任务队列、账号管理、数据导出 UI、平台内置 adapter 集合或桌面发布流程。真实平台任务仍应坚持小步执行、读回校验、证据 journal 和高风险动作人工确认。

## English

### What This Project Is

`crawshrimp-skill` turns crawshrimp-style browser automation into a general web-operation protocol for Codex and AI agents:

```text
user goal -> observe -> build page model -> plan -> act -> verify -> journal -> distill
```

It has two goals:

1. Reuse crawshrimp-inspired CDP browser automation so an AI agent can inspect pages, operate Chrome, execute safe actions, and complete live web tasks.
2. Freeze proven automation paths into reusable workflows, scripts, CLI commands, or new skill drafts for the next run.

### Implemented Capabilities

- `observe`: captures URL, title, visible text, controls, tables, download directory evidence, dialogs/drawers/popovers, blocking states, resource clues, and accessibility-ish controls.
- `act`: executes small-step `click`, `type`, `select`, `upload`, `download`, `wait`, `navigate`, and `paginate` actions.
- Crawshrimp runtime compatibility: adapter/task registry, auth check, knowledge service, probe bundle, framework/network snapshot, JSRunner-style phase/shared runtime, file chooser upload, wheel capture, request-capture `min_matches`/response-body options, concurrent URL downloads, browser-session URL downloads, click-download transient-tab handling, and refresh recovery.
- `verify`: supports custom JavaScript expressions and structured checks: `text`, `url`, `selector-exists`, `table-rows-min`, and `file-exists`.
- `journal`: loads and appends the same JSON journal across commands, preserving observations, actions, verifications, failures, and recovery notes.
- `distill`: turns a journal into workflow notes or a reusable package with `workflow.md`, `commands.json`, `run_workflow.py`, and optionally a generated `SKILL.md`.
- Safety guardrails: dangerous actions such as submit, publish, send, delete, pay, purchase, confirm, and bulk modify require explicit confirmation.
- Validation: includes `unittest` coverage and a `quick_validate.py` skill-structure validator.

### Supported Task Families

- Read tasks: scrape tables, search information, export page data, summarize page content.
- Operate tasks: filter, paginate, open details, download files, fill forms without dangerous submission.
- Flow tasks: multi-page, multi-dialog, multi-step workflows with evidence and reusable workflow output.

### Quick Start

Install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Start Chrome with a remote debugging port:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/crawshrimp-skill-chrome
```

Open the target page, then use the high-level operator:

```bash
python3 scripts/web_operator.py observe \
  --url-prefix https://example.com \
  --task "summarize this page" \
  --journal run.json

python3 scripts/web_operator.py act click \
  --url-prefix https://example.com \
  --selector "button.export" \
  --reason "open export menu" \
  --journal run.json

python3 scripts/web_operator.py act upload-chooser \
  --url-prefix https://example.com \
  --clicks-json '[{"x":120,"y":240}]' \
  --file ./input.csv \
  --reason "attach file through native chooser" \
  --journal run.json

python3 scripts/web_operator.py act capture-wheel \
  --url-prefix https://example.com \
  --wheels-json '[{"x":640,"y":520,"delta_y":900}]' \
  --value '[{"url_contains":"/api/"}]' \
  --reason "capture lazy-load requests" \
  --journal run.json

python3 scripts/web_operator.py verify \
  --url-prefix https://example.com \
  --check text \
  --target "Export" \
  --evidence "export menu is visible" \
  --journal run.json

python3 scripts/web_operator.py distill \
  --journal run.json \
  --output-dir reusable-workflow \
  --name example-export \
  --include-skill
```

Low-level CDP commands are also available:

```bash
python3 scripts/browser_executor.py cdp \
  --url-prefix https://example.com \
  observe

python3 scripts/browser_executor.py cdp \
  --url-prefix https://example.com \
  eval \
  --script "document.title"

python3 scripts/browser_executor.py cdp \
  --url-prefix https://example.com \
  capture \
  --capture-mode url \
  --url https://example.com/report \
  --matches-json '[{"url_contains":"/api/report","method":"GET"}]' \
  --min-matches 1 \
  --include-response-body
```

Crawshrimp-style adapter, knowledge, probe, and phase helpers:

```bash
python3 scripts/adapter_registry.py --root adapters scan
python3 scripts/knowledge_service.py --adapters-root adapters --probes-root probes --data-root knowledge rebuild
python3 scripts/knowledge_service.py --data-root knowledge search --query "export drawer" --adapter temu --task goods_traffic_detail
python3 scripts/phase_runner.py --url-prefix https://example.com --file adapters/demo/orders.js --params-json '{"keyword":"sku"}' --artifact-dir artifacts
```

`phase_runner.py` accepts crawshrimp-style `meta.action` values: `cdp_clicks`, `inject_files`, `file_chooser_upload`, `capture_click_requests`, `capture_url_requests`, `capture_wheel_requests`, `download_urls`, `download_clicks`, `reload_page`, `next_phase`, `complete`, and `abort`. `download_urls` can set `browser_session`/`browserSession` to download through a temporary browser tab when the URL needs login cookies or native browser download behavior.

Task classification and planning helpers:

```bash
python3 scripts/web_agent_protocol.py classify "filter last 7 days and download export"
python3 scripts/web_agent_protocol.py plan "filter last 7 days and download export"
python3 scripts/web_agent_protocol.py journal-template "collect details across multiple pages"
```

### Validation

```bash
python3 -m unittest
python3 -m unittest discover -s tests
python3 quick_validate.py .
python3 -m compileall scripts tests quick_validate.py
```

### Repository Layout

```text
crawshrimp-skill/
  SKILL.md                      # Codex skill entrypoint
  PLAN.md                       # goals, scope, and roadmap
  agents/openai.yaml            # agent-facing metadata
  references/                   # protocol, observation, actions, safety, verification, distillation docs
  scripts/
    web_agent_protocol.py       # task taxonomy, planning, data structures, safety, journal
    adapter_registry.py         # crawshrimp-style adapter/task manifest registry
    browser_executor.py         # direct Chrome/CDP backend
    knowledge_service.py        # knowledge card indexing/search from notes and probe bundles
    probe_bundle.py             # probe bundle generation, endpoint analysis, redaction
    phase_runner.py             # JSRunner-style phase/shared runtime
    runtime_downloads.py        # concurrent URL downloads, click downloads, artifact management
    web_operator.py             # high-level observe/act/verify/journal/distill CLI
    workflow_builder.py         # reusable workflow package generator
  tests/                        # unittest suite
  quick_validate.py             # skill structure validator
```

### Current Limits

This repository now mirrors and abstracts the main crawshrimp runtime execution surfaces, but it is still not the full crawshrimp desktop application. It does not include the GUI, task queue, account model, data export UI, bundled platform adapters, or desktop release pipeline. Real platform work should still use small actions, readback checks, evidence journals, and explicit human confirmation before high-risk side effects.
