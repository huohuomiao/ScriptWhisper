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

检查时间：2026-06-05

当前 `origin/main` 仍处于初始提交状态，只包含 `README.md`，尚未合并 PR-01 到 PR-21。因此严格意义上，`origin/main` 当前不能直接运行完整应用。

可运行性验证已在当前堆叠分支 `pr-21-demo-final-check` 上完成。该分支已经补齐最终集成所需的 FastAPI 入口、健康检查、TXT 上传、章节解析器、pytest 路径配置和仓库级 `.gitignore`。

```powershell
pip install -r requirements.txt
pytest backend/tests
npm run build
uvicorn backend.main:app --host 127.0.0.1 --port 8000
Invoke-WebRequest http://127.0.0.1:5173
```

验证结果：

- 后端测试：13 passed
- 后端 HTTP：`GET /health` 返回 `{"status":"ok"}`
- 前端构建：通过
- 前端开发服务：`200 OK`
- examples：已补齐输入、三章节输入、YAML 输出和 Markdown 输出

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

## 合并建议

PR-15 到 PR-21 是顺序堆叠关系，建议按编号合并。当前 `pr-21-demo-final-check` 分支已经做过最终集成补齐；如需让 `main` 直接可运行，应将 PR 链合并到 `main` 后再执行同样的检查命令。
