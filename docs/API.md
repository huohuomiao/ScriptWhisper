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

## POST /api/upload

上传 UTF-8 编码的 `.txt` 小说文本，后端会保存文件并返回文本内容。

请求：`multipart/form-data`

字段：

```text
file: sample_novel_3chapters.txt
```

响应：

```json
{
  "filename": "sample_novel_3chapters.txt",
  "stored_filename": "uuid_sample_novel_3chapters.txt",
  "saved_path": "backend/uploads/uuid_sample_novel_3chapters.txt",
  "size_bytes": 512,
  "content": "第一章 雨夜来信..."
}
```
