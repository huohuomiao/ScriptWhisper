# Demo 与最终检查

## Demo 视频

Demo 视频链接：待上传。

当前仓库中没有可提交的视频文件，也没有外部视频地址可验证。最终发布前建议录制 60-90 秒演示视频，覆盖以下路径：

1. 打开前端工作台。
2. 查看分析结果页的章节列表、人物表、地点表。
3. 切换到剧本预览页，查看场景卡片。
4. 使用单场景润色按钮更新场景内容。
5. 切换到导出页，下载 YAML 和 Markdown。

建议视频命名：`ScriptWhisper_demo.mp4`。

## 主分支检查

检查时间：2026-06-07

当前 `origin/main` 已包含 PR #24 的本地工作区同步内容，以及后续合规说明和 CI 锁文件修复。主分支包含前端、后端、示例、文档、测试、`.github/workflows/ci.yml` 和 UI 验证脚本，可直接安装依赖、运行测试、构建前端并启动本地演示。

PR #24 合并前，原本地目录 `D:\work\21ai文本转剧本` 仍显示 4 个未提交修改：`.gitignore`、`frontend/src/styles.css`、`package.json`、`package-lock.json`。PR #24 已纳入这 4 个文件的本地内容；PR #25 之后，当前 main 又额外修复了 `package-lock.json` 的 CI 锁文件问题，因此原目录现在只有 `package-lock.json` 与最新 main 不同，该差异属于 PR #25，不是未上传遗留改动。原目录仍显示这些文件未提交，是因为该目录停留在旧的 `pr-21-demo-final-check` 工作分支。

```powershell
pip install -r requirements.txt
npm ci
python -m pytest backend/tests
npm run build
uvicorn backend.main:app --host 127.0.0.1 --port 8000
Invoke-WebRequest http://127.0.0.1:5173
```

验证结果：

- 后端测试：32 passed
- 后端 HTTP：`GET /health` 返回 `{"status":"ok"}`
- 后端 HTTP：`POST /api/convert` 可返回 ScriptYAML
- 后端 HTTP：`POST /api/scenes/polish` 可返回润色后的 ScriptYAML
- 前端构建：通过
- 前端开发服务：`200 OK`
- 内置 Browser 验证：首页可打开，预览页可见“剧本工作台”“剧本正文”“查看完整原文”，控制台无错误
- examples：已补齐输入、三章节输入、YAML 输出和 Markdown 输出
- CI 工作流：`.github/workflows/ci.yml` 会在 push 到 `main` 和 pull request 时运行后端测试与前端构建

## examples 完整性

当前 examples 文件：

```text
examples/
├── README.md
├── sample_novel.txt
├── sample_novel_3chapters.txt
├── sample_output.md
└── sample_output.yaml
```

用途：

- `sample_novel.txt`：最小小说输入。
- `sample_novel_3chapters.txt`：用于章节解析和端到端演示。
- `sample_output.yaml`：结构化 ScriptYAML 输出。
- `sample_output.md`：创作者可读的 Markdown 导出。

## 合并记录

已按功能拆分合并 PR #1、#2、#4 到 #24，其中 PR #3 因与后续健康检查实现重复，按要求跳过未合并。PR #24 用于同步本地 `D:\work\21ai文本转剧本` 工作区中尚未进入 GitHub 的收尾代码，并补齐 `.github/` 清单目录和 UI 验证脚本。
