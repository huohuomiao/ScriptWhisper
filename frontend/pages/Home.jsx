import { BadgeCheck, FileText, GitBranch, WandSparkles } from "lucide-react";
import { useState } from "react";

import { convertNovel, uploadNovelFile } from "../src/api.js";

const sampleText = `第一章 雨夜来信

雨停后的长街泛着冷光。林澈握着那封没有署名的信，终于在旧影院门口看见了等候多时的沈微。她没有开口，只把一张泛黄的电影票递给他。`;

export default function Home({ onAnalysisComplete }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("雨夜来信");
  const [text, setText] = useState(sampleText);
  const [status, setStatus] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  async function handleAnalyze(event) {
    event.preventDefault();
    setIsBusy(true);
    setStatus("分析中");

    try {
      let source = "manual_input.txt";
      let novelText = text;

      if (file) {
        const uploaded = await uploadNovelFile(file);
        source = uploaded.filename;
        novelText = uploaded.content;
        setText(uploaded.content);
      }

      const result = await convertNovel({ text: novelText, title, source });
      onAnalysisComplete(result);
      setStatus(result.mock_mode ? "已使用 mock 模式生成" : "已调用 AI API 生成");
    } catch (error) {
      setStatus(error.message);
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <section className="workspace">
      <section className="section-block intro-block">
        <div>
          <p className="eyebrow">AI 小说转剧本工具</p>
          <h2>ScriptWhisper</h2>
          <p>
            将小说文本拆解为章节、人物、地点、场景和剧本正文，输出可校验、可编辑、可导出的
          ScriptYAML 数据。
          </p>
        </div>
        <div className="intro-points" aria-label="核心流程">
          <IntroPoint icon={<FileText size={18} />} label="章节解析" />
          <IntroPoint icon={<WandSparkles size={18} />} label="AI 抽取与生成" />
          <IntroPoint icon={<BadgeCheck size={18} />} label="Schema 校验修复" />
          <IntroPoint icon={<GitBranch size={18} />} label="YAML / Markdown 导出" />
        </div>
      </section>

      <div className="metric-grid" aria-label="项目能力">
        <Metric label="上传接口" value="/api/upload" />
        <Metric label="健康检查" value="/health" />
        <Metric label="示例章节" value="3" />
        <Metric label="输出格式" value="YAML" />
      </div>

      <form className="section-block upload-workbench" onSubmit={handleAnalyze}>
        <div className="field-row">
          <label>
            项目标题
            <input value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label>
            TXT 文件
            <input accept=".txt,text/plain" type="file" onChange={(event) => setFile(event.target.files[0] || null)} />
          </label>
        </div>
        <label>
          小说文本
          <textarea value={text} onChange={(event) => setText(event.target.value)} rows={8} />
        </label>
        <div className="submit-row">
          <button disabled={isBusy || (!file && !text.trim())} type="submit">
            {isBusy ? "分析中" : "上传并生成"}
          </button>
          {status && <span>{status}</span>}
        </div>
      </form>
    </section>
  );
}

function IntroPoint({ icon, label }) {
  return (
    <div className="intro-point">
      <span className="heading-icon">{icon}</span>
      <span>{label}</span>
    </div>
  );
}

function Metric({ label, value }) {
  const isCompact = String(value).length > 4;

  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={isCompact ? "metric-compact" : undefined}>{value}</strong>
    </div>
  );
}
