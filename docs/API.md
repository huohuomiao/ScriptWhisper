# API

## GET /health

健康检查接口。

响应：

```json
{
  "status": "ok"
}
```

## POST /api/convert

把小说片段转换为剧本草稿。

请求：

```json
{
  "novel_text": "雨停后的长街泛着冷光。",
  "style": "短剧剧本"
}
```

响应：

```json
{
  "script": "场景一  内景  深夜...",
  "provider": "mock"
}
```

`provider` 为 `mock` 表示未配置 API，返回本地示例；为 `api` 表示已调用外部 AI API。
