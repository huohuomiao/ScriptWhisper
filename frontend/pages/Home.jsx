import { BadgeCheck, BookOpenCheck, Boxes, Clapperboard, UploadCloud, WandSparkles } from "lucide-react";
import { useState } from "react";

import { convertNovel, uploadNovelFile } from "../src/api.js";

const sampleText = `第一章 雨夜来信

雨停后的长街泛着冷光。林澈握着那封没有署名的信，终于在旧影院门口看见了等候多时的沈微。她没有开口，只把一张泛黄的电影票递给他。`;

const productSteps = [
  { icon: UploadCloud, title: "上传小说", detail: "选择 txt 文件，或直接粘贴章节文本。" },
  { icon: BookOpenCheck, title: "章节解析", detail: "识别中文章节和英文 Chapter 标题。" },
  { icon: Clapperboard, title: "剧本生成", detail: "抽取人物地点，规划场景并生成对白。" },
  { icon: Boxes, title: "结构化导出", detail: "校验 ScriptYAML，导出 YAML / Markdown。" },
];

const progressSteps = ["章节解析", "人物抽取", "场景规划", "剧本生成", "Schema 校验"];

export default function Home({ onAnalysisComplete }) {
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("雨夜来信");
  const [text, setText] = useState(sampleText);
  const [status, setStatus] = useState("");
  const [statusType, setStatusType] = useState(""); // "success" | "error" | ""
  const [isBusy, setIsBusy] = useState(false);
  const [analysisMode, setAnalysisMode] = useState("api");
  const [progressIndex, setProgressIndex] = useState(-1);

  async function handleAnalyze(event) {
    event.preventDefault();
    setIsBusy(true);
    setStatus("分析中");
    setStatusType("");
    setProgressIndex(0);
    const progressTimer = window.setInterval(() => {
      setProgressIndex((current) => (current >= 0 && current < progressSteps.length - 2 ? current + 1 : current));
    }, 900);

    try {
      let source = "manual_input.txt";
      let novelText = text;

      if (file) {
        setStatus("正在读取上传文本");
        const uploaded = await uploadNovelFile(file);
        source = uploaded.filename;
        novelText = uploaded.content;
        setText(uploaded.content);
      }

      setStatus(analysisMode === "mock" ? "正在生成演示结果" : "正在调用 AI API");
      setProgressIndex(2);
      const result = await convertNovel({ text: novelText, title, source, mock: analysisMode === "mock" });
      setProgressIndex(progressSteps.length - 1);
      onAnalysisComplete(result);
      setStatus(result.mock_mode ? "已使用 mock 模式生成" : "已调用 AI API 生成");
      setStatusType("success");
    } catch (error) {
      setStatus(error.message);
      setStatusType("error");
    } finally {
      window.clearInterval(progressTimer);
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
        <div className="mode-switch" aria-label="生成模式">
          <button
            className={analysisMode === "api" ? "active" : ""}
            type="button"
            onClick={() => setAnalysisMode("api")}
          >
            <WandSparkles size={17} />
            AI API 模式
          </button>
          <button
            className={analysisMode === "mock" ? "active" : ""}
            type="button"
            onClick={() => setAnalysisMode("mock")}
          >
            <BadgeCheck size={17} />
            Mock 演示模式
          </button>
          <p>{analysisMode === "api" ? "调用已配置的小米 MiMo API。" : "使用本地模拟结果，适合无余额或离线演示。"}</p>
        </div>
      </section>

      <div className="process-grid" aria-label="产品流程">
        {productSteps.map((step, index) => (
          <ProcessStep key={step.title} index={index + 1} {...step} />
        ))}
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
          {status && <span className={statusType === "error" ? "status-error" : ""}>{status}</span>}
        </div>
        <div className="progress-panel" aria-label="分析进度">
          {progressSteps.map((step, index) => (
            <div className={progressClass(index, progressIndex, statusType)} key={step}>
              <span>{index + 1}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </div>
      </form>
    </section>
  );
}

function ProcessStep({ detail, icon: Icon, index, title }) {
  return (
    <article className="process-step">
      <span className="process-number">{index}</span>
      <Icon size={22} />
      <h3>{title}</h3>
      <p>{detail}</p>
    </article>
  );
}

function progressClass(index, progressIndex, statusType) {
  if (statusType === "error" && index === progressIndex) {
    return "progress-step error";
  }
  if (progressIndex === progressSteps.length - 1 && statusType === "success") {
    return "progress-step done";
  }
  if (index < progressIndex) {
    return "progress-step done";
  }
  if (index === progressIndex) {
    return "progress-step active";
  }
  return "progress-step";
}
