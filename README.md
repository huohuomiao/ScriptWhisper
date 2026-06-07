# ScriptWhisper

ScriptWhisper 是一个面向小说改编的 AI 剧本创作工具。它把小说章节转化为可校验、可编辑、可导出的结构化剧本数据，核心输出格式为自定义的 `ScriptYAML`。

项目目标不是简单“续写文本”，而是把小说改编流程拆成稳定步骤：章节解析、人物/地点抽取、场景规划、剧本正文生成、Schema 校验、自动修复和导出展示。

## 功能列表

- FastAPI 健康检查：`GET /health` 返回 `{"status":"ok"}`。
- TXT 上传：`POST /api/upload` 接收小说文本并保存到后端上传目录。
- AI 转换接口：`POST /api/convert` 串联章节解析、人物/地点抽取、场景规划、剧本生成和 Schema 校验。
- 单场景润色接口：`POST /api/scenes/polish` 更新选中场景并返回校验后的 ScriptYAML。
- 小说章节解析：识别中文章节标题和英文 `Chapter` 标题。
- 人物/地点抽取：从章节文本生成角色表和地点表。
- 场景规划：把章节拆为场景，每个场景包含标题、人物、地点和摘要。
- 剧本正文生成：根据场景大纲生成动作、对白、镜头提示和转场。
- ScriptYAML Schema：用 Pydantic 校验 `project`、`characters`、`locations`、`scenes`、`script`。
- YAML 校验与自动修复：修复缺失字段、非法 ID、错误引用和缺失正文。
- 前端分析页：展示章节列表、人物表和地点表。
- 剧本预览页：以场景卡片展示动作、对白、镜头和转场。
- 单场景润色：支持“强化冲突”和“修改对白”的局部更新。
- 导出页：支持 YAML / Markdown 下载。
- AI mock 模式：未配置 `.env` 时仍可本地跑通完整流程。

## 技术架构

```text
backend/
  main.py                       # FastAPI 应用入口
  app/
    api.py                      # /health、/api/upload、/api/convert 和润色路由
    config.py                   # 应用配置
  schemas/
    conversion.py               # AI 转换和场景润色接口模型
    upload.py                   # 上传接口响应模型
    script_yaml.py              # ScriptYAML Pydantic 模型
  services/
    ai_client.py                # LLMClient，读取 .env，支持 mock
    chapter_parser.py           # 中英文章节标题解析
    conversion_pipeline.py      # 小说到 ScriptYAML 的后端管线
    entity_extractor.py         # 人物/地点抽取
    scene_polisher.py           # 单场景润色
    scene_planner.py            # 场景规划
    script_generator.py         # 剧本正文生成
    script_yaml_validator.py    # YAML 校验与自动修复
    upload_storage.py           # TXT 上传保存
    yaml_exporter.py            # YAML 导出
  tests/
    test_ai_pipeline.py         # 错误处理与集成测试
    test_api_pipeline.py        # API 管线和润色测试
    test_chapter_parser.py      # 章节解析测试
    test_health.py              # 健康检查测试
    test_upload.py              # 上传接口测试
frontend/
  pages/
    Home.jsx                    # 项目首页
    Analysis.jsx                # 分析结果展示
    ScriptPreview.jsx           # 剧本预览
    Export.jsx                  # YAML / Markdown 下载
  components/
    SceneEditor.jsx             # 单场景润色
  src/
    sampleData.js               # 前端示例数据
examples/
  sample_output.yaml            # ScriptYAML 示例输出
docs/
  script_yaml_schema.md         # Schema 字段说明
```

## 安装运行

### 后端测试

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest backend/tests
```

### 后端运行

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```text
http://127.0.0.1:8000/health
```

上传接口：

```text
POST http://127.0.0.1:8000/api/upload
form-data: file=<novel.txt>
```

AI 转换接口：

```text
POST http://127.0.0.1:8000/api/convert
JSON: {"text":"小说正文","title":"项目标题","source":"novel.txt"}
```

场景润色接口：

```text
POST http://127.0.0.1:8000/api/scenes/polish
JSON: {"script_yaml": {...}, "scene_id": "scene_1", "action": "conflict"}
```

### 前端运行

```powershell
npm install
npm run dev
```

默认访问：

```text
http://127.0.0.1:5173
```

生产构建：

```powershell
npm run build
```

前端默认连接 `http://127.0.0.1:8000`。如需改后端地址，可配置：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## AI 配置

项目通过 `.env` 读取 AI API 配置，支持 OpenAI-compatible 和 Anthropic/Claude-compatible 两种协议：

```env
AI_API_KEY=your_api_key_here
AI_API_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
AI_API_PROTOCOL=openai
AI_MODEL=mimo-v2.5-pro
AI_MAX_TOKENS=4096
AI_REQUEST_TIMEOUT_SECONDS=120
AI_MOCK_MODE=false
```

如果使用 OpenAI-compatible 接口，把 `AI_API_PROTOCOL` 改为 `openai`，并将 `AI_API_BASE_URL` 设置为类似 `https://api.example.com/v1` 的地址。

如果缺少 `AI_API_KEY`、`AI_API_BASE_URL` 或 `AI_MODEL`，系统会自动进入 mock 模式，便于本地开发和测试。

## 第三方依赖说明

后端：

- `fastapi`：提供 HTTP API、上传接口和健康检查。
- `starlette`：FastAPI 的 ASGI 基础组件，显式约束版本以保持测试稳定。
- `uvicorn`：本地 ASGI 开发服务器。
- `python-multipart`：解析前端上传的 `multipart/form-data`。
- `httpx`：支撑 FastAPI 测试客户端和异步 LLM HTTP 调用。
- `pydantic`：定义和校验 `ScriptYAML` 数据模型。
- `pytest`：运行错误处理和集成测试。

前端：

- `react` / `react-dom`：构建交互式 UI。
- `vite`：开发服务器和构建工具。
- `@vitejs/plugin-react`：React Vite 插件。
- `lucide-react`：图标库。
- `@playwright/test`：UI 验证脚本依赖，用于运行 `tools/verify-ui.mjs` 检查本地页面。

## 原创功能说明

ScriptWhisper 的核心原创点在于把“AI 生成剧本”拆成可验证的流水线，而不是只输出一段不可控文本：

- `ScriptYAML` 将项目、人物、地点、场景和剧本文本拆为可追踪字段。
- 自动修复器会修复非法 ID、错误引用、缺失对白角色和缺失场景正文。
- 单场景润色通过后端接口只更新选中场景，降低全篇重写带来的不稳定。
- 导出页同时支持机器可读的 YAML 和创作者可读的 Markdown。

## 示例输入输出

示例输入：

```text
第一章 雨夜来信

雨停后的长街泛着冷光。林澈握着那封没有署名的信，终于在旧影院门口看见了等候多时的沈微。
```

示例输出：

```yaml
project:
  title: 雨夜来信
  version: "1.0"
characters:
  - id: lin_che
    name: 林澈
locations:
  - id: old_cinema
    name: 旧影院门口
scenes:
  - id: scene_1
    title: 雨夜重逢
    location_id: old_cinema
    characters:
      - lin_che
script:
  - scene_id: scene_1
    type: action
    content: 雨停后的长街泛着冷光。
```

完整示例见：

- `examples/sample_output.yaml`
- `docs/script_yaml_schema.md`

## Demo 视频

Demo 视频链接和最终检查记录见 `docs/final_check.md`。

## 使用手册

完整使用说明见 `docs/user_manual.md`，包括启动方式、AI API 配置、前端操作、后端接口和常见问题。

## PR 记录

| PR | 主题 |
| --- | --- |
| PR-01 | 初始化项目结构 |
| PR-02 | FastAPI 健康检查接口 |
| PR-03 | React 前端首页 |
| PR-04 | 小说文本上传 |
| PR-05 | 章节解析器 |
| PR-06 | 章节解析测试 |
| PR-07 | ScriptYAML Pydantic 模型 |
| PR-08 | YAML 导出功能 |
| PR-09 | ScriptYAML Schema 文档 |
| PR-10 | LLMClient 调用封装 |
| PR-11 | 人物/地点抽取 |
| PR-12 | 场景规划生成 |
| PR-13 | 剧本正文生成 |
| PR-14 | YAML 校验与自动修复 |
| PR-15 | 分析结果展示 |
| PR-16 | 剧本预览页面 |
| PR-17 | 单场景润色功能 |
| PR-18 | 导出页面 |
| PR-19 | 错误处理和集成测试 |
| PR-20 | README 完善 |
| PR-21 | Demo 视频与最终检查 |
| PR-22 | 最终演示集成检查 |
| PR-23 | 上传文本换行兼容修复 |
| PR-24 | 同步本地工作区收尾代码、CI 和 UI 验证脚本 |

说明：GitHub PR #3 的健康检查分支因与后续 main 实现重复，按要求跳过未合并；健康检查功能已保留在当前主分支。PR #24 同步前，本地目录 `D:\work\21ai文本转剧本` 仍显示 `.gitignore`、`frontend/src/styles.css`、`package.json`、`package-lock.json` 4 个未提交修改。PR #24 已纳入这 4 个文件的本地内容；PR #25 之后，当前 main 又额外修复了 `package-lock.json` 的 CI 锁文件问题，因此原目录现在只有 `package-lock.json` 与最新 main 不同，该差异属于 PR #25，不是未上传遗留改动。
