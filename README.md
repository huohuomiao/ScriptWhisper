# ScriptWhisper

ScriptWhisper 是一个面向小说改编的 AI 剧本创作工具。它把小说章节转化为可校验、可编辑、可导出的结构化剧本数据，核心输出格式为自定义的 `ScriptYAML`。

项目目标不是简单“续写文本”，而是把小说改编流程拆成稳定步骤：章节解析、人物/地点抽取、场景规划、剧本正文生成、Schema 校验、自动修复和导出展示。

## 功能列表

- FastAPI 健康检查：`GET /health` 返回 `{"status":"ok"}`。
- TXT 上传：`POST /api/upload` 接收小说文本并保存到后端上传目录。
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
    api.py                      # /health 和 /api/upload 路由
    config.py                   # 应用配置
  schemas/
    upload.py                   # 上传接口响应模型
    script_yaml.py              # ScriptYAML Pydantic 模型
  services/
    ai_client.py                # LLMClient，读取 .env，支持 mock
    chapter_parser.py           # 中英文章节标题解析
    entity_extractor.py         # 人物/地点抽取
    scene_planner.py            # 场景规划
    script_generator.py         # 剧本正文生成
    script_yaml_validator.py    # YAML 校验与自动修复
    upload_storage.py           # TXT 上传保存
    yaml_exporter.py            # YAML 导出
  tests/
    test_ai_pipeline.py         # 错误处理与集成测试
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

## AI 配置

项目通过 `.env` 读取 OpenAI-compatible API 配置：

```env
AI_API_KEY=your_api_key_here
AI_API_BASE_URL=https://api.example.com/v1
AI_MODEL=your-model-name
AI_MOCK_MODE=false
```

如果缺少 `AI_API_KEY`、`AI_API_BASE_URL` 或 `AI_MODEL`，系统会自动进入 mock 模式，便于本地开发和测试。

## 第三方依赖说明

后端：

- `fastapi`：提供 HTTP API、上传接口和健康检查。
- `starlette`：FastAPI 的 ASGI 基础组件，显式约束版本以保持测试稳定。
- `uvicorn`：本地 ASGI 开发服务器。
- `python-multipart`：解析前端上传的 `multipart/form-data`。
- `httpx`：支撑 FastAPI 测试客户端。
- `pydantic`：定义和校验 `ScriptYAML` 数据模型。
- `pytest`：运行错误处理和集成测试。

前端：

- `react` / `react-dom`：构建交互式 UI。
- `vite`：开发服务器和构建工具。
- `@vitejs/plugin-react`：React Vite 插件。
- `lucide-react`：图标库。

## 原创功能说明

ScriptWhisper 的核心原创点在于把“AI 生成剧本”拆成可验证的流水线，而不是只输出一段不可控文本：

- `ScriptYAML` 将项目、人物、地点、场景和剧本文本拆为可追踪字段。
- 自动修复器会修复非法 ID、错误引用、缺失对白角色和缺失场景正文。
- 单场景润色只更新选中场景，降低全篇重写带来的不稳定。
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
