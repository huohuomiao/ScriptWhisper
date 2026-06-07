# ScriptWhisper 使用说明手册

## 1. 项目用途

ScriptWhisper 是一个 AI 小说转剧本工具。它把小说文本转换成结构化 `ScriptYAML`：

- `project`：项目基础信息。
- `characters`：人物表。
- `locations`：地点表。
- `scenes`：场景大纲。
- `script`：动作、对白、镜头提示和转场。

前端提供上传、分析结果、剧本预览、单场景润色和导出页面；后端负责上传、章节解析、AI 管线、Schema 校验和润色。

## 2. 当前 AI API

代码支持 OpenAI-compatible Chat Completions 和 Anthropic/Claude-compatible Messages 两种接口。

```text
AI_API_PROTOCOL=openai     -> POST {AI_API_BASE_URL}/chat/completions
AI_API_PROTOCOL=anthropic  -> POST {AI_API_BASE_URL}/v1/messages
```

本地 `.env` 当前已配置为 OpenAI-compatible 网关：

```env
AI_API_KEY=你的本地密钥
AI_API_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
AI_API_PROTOCOL=openai
AI_MODEL=mimo-v2.5-pro
AI_MAX_TOKENS=4096
AI_REQUEST_TIMEOUT_SECONDS=120
```

注意：

- `.env` 已被 `.gitignore` 忽略，不会提交到 GitHub。
- 不要把真实 `AI_API_KEY` 写进 README、示例文件或提交记录。
- 如果需要离线演示，添加 `AI_MOCK_MODE=true` 会强制进入 mock 模式。

## 3. 安装依赖

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

前端：

```powershell
npm install
```

## 4. 启动服务

启动后端：

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

启动前端：

```powershell
npm run dev
```

浏览器访问：

```text
http://127.0.0.1:5173
```

## 5. 使用流程

1. 打开首页。
2. 在首页选择“AI API 模式”或“Mock 演示模式”。
3. 输入项目标题。
4. 上传 `.txt` 小说文件，或直接粘贴小说文本。
5. 点击“上传并生成”。
6. 观察分析进度：章节解析、人物抽取、场景规划、剧本生成、Schema 校验。
7. 进入“分析”页查看原文字数、识别章节、人物数量、地点数量和生成场景。
8. 在“分析”页查看人物表、地点表和故事 Bible。
9. 进入“预览”页查看场景卡片和剧本文本。
10. 在“预览”页选择场景，点击“强化冲突”或“修改对白”。
11. 进入“导出”页下载 YAML 或 Markdown。

## 6. 后端 API

健康检查：

```text
GET /health
```

上传 txt：

```text
POST /api/upload
form-data: file=<novel.txt>
```

小说转剧本：

```text
POST /api/convert
```

请求示例：

```json
{
  "title": "雨夜来信",
  "source": "sample_novel.txt",
  "text": "第一章 雨夜来信\n\n雨停后的长街泛着冷光……"
}
```

单场景润色：

```text
POST /api/scenes/polish
```

请求示例：

```json
{
  "script_yaml": {},
  "scene_id": "scene_1",
  "action": "conflict"
}
```

`action` 可选：

- `conflict`：强化冲突。
- `dialogue`：修改对白。

## 7. 测试和检查

后端测试：

```powershell
pytest backend/tests
```

前端构建：

```powershell
npm run build
```

真实 AI 配置检查：

```powershell
python -c "from backend.services.ai_client import LLMSettings; s=LLMSettings.from_env(); print({'has_key': bool(s.api_key), 'base_url': s.api_base_url, 'protocol': s.api_protocol, 'model': s.model, 'mock_mode': s.mock_mode, 'timeout': s.request_timeout})"
```

如果 `mock_mode` 是 `False`，说明配置齐全，会调用真实 AI API。

## 8. 常见问题

### 一直是 mock 模式

检查 `.env` 必须是多行：

```env
AI_API_KEY=...
AI_API_BASE_URL=...
AI_API_PROTOCOL=openai
AI_MODEL=...
```

不要写成一行。

### 返回 402 insufficient_balance

说明已经调用到 AI 网关，但账户余额不足。需要在网关控制台充值或换可用 key。

### 前端无法生成

确认后端已经运行在：

```text
http://127.0.0.1:8000
```

如果后端地址不同，配置：

```env
VITE_API_BASE_URL=http://你的后端地址
```

### 上传失败

当前只支持 UTF-8 `.txt` 文件，最大 2 MB。
