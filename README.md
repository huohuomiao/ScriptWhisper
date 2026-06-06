# AI 小说转剧本工具

这是一个用于把小说文本转换成剧本草稿的全栈项目初始化模板。后端使用 FastAPI 提供接口，前端使用 React + Vite 提供最小可用页面。

真实 API key 不应写入代码仓库。请复制 `.env.example` 为 `.env`，然后在本机环境变量中配置自己的 key、API 地址和模型名称。

## 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── api.py
│   │   └── config.py
│   ├── services/
│   │   └── ai_client.py
│   ├── schemas/
│   │   └── conversion.py
│   ├── tests/
│   │   └── test_health.py
│   └── main.py
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── styles.css
│   ├── pages/
│   │   └── Home.jsx
│   ├── components/
│   │   ├── ConversionDemo.jsx
│   │   └── ProjectHeader.jsx
│   ├── index.html
│   └── vite.config.js
├── docs/
│   └── API.md
├── examples/
│   └── sample_novel.txt
├── requirements.txt
├── package.json
└── README.md
```

## 后端运行

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

健康检查：

```powershell
curl http://127.0.0.1:8000/health
```

返回：

```json
{"status":"ok"}
```

## 前端运行

```powershell
npm install
npm run dev
```

默认访问：`http://127.0.0.1:5173`

## API 配置

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`：

```env
AI_API_KEY=your_api_key_here
AI_API_BASE_URL=https://api.example.com/v1
AI_MODEL=your-model-name
```

如果没有配置 API key 或 API 地址，`/api/convert` 会返回本地示例结果，便于前后端直接联调。
