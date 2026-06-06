import {
  BadgeCheck,
  BookOpenCheck,
  Boxes,
  Clapperboard,
  Layers3,
  LoaderCircle,
  Play,
  UploadCloud,
  WandSparkles,
} from "lucide-react";
import { useState } from "react";

import { convertNovel, uploadNovelFile } from "../src/api.js";

const sampleText = `第一章 雨夜来信

雨停后的长街泛着冷光。林澈握着那封没有署名的信，终于在旧影院门口看见了等候多时的沈微。她没有开口，只把一张泛黄的电影票递给他。`;

const productSteps = [
  { icon: UploadCloud, title: "Chapter Parsing", detail: "识别章节标题、正文边界和原文来源。" },
  { icon: BookOpenCheck, title: "Entity Extraction", detail: "抽取人物、地点、动机与对白风格。" },
  { icon: Clapperboard, title: "Scene Generation", detail: "按场景生成目标、冲突、转折和剧本行。" },
  { icon: Boxes, title: "Structured Export", detail: "校验 ScriptYAML，并导出 YAML / Markdown。" },
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
    <section className="workspace home-workspace">
      <section className="home-hero">
        <div className="hero-copy">
          <p className="eyebrow">AI Creative Workflow</p>
          <h2>把小说章节转成可编辑的结构化剧本</h2>
          <p>
            ScriptWhisper 将原文拆解为章节、人物、地点、场景与剧本行，并保留来源证据，方便后续润色和导出。
          </p>
          <div className="hero-metrics" aria-label="产品能力概览">
            <span>Scene-first</span>
            <span>ScriptYAML</span>
            <span>AI assisted edit</span>
          </div>
        </div>

        <div className="hero-preview" aria-label="工作流示意">
          <div className="hero-preview-header">
            <span className="status-dot" aria-hidden="true" />
            <strong>Pipeline Preview</strong>
          </div>
          <div className="pipeline-card">
            <span>01</span>
            <div>
              <strong>章节文本</strong>
              <p>雨夜、旧影院、电影票</p>
            </div>
          </div>
          <div className="pipeline-card">
            <span>02</span>
            <div>
              <strong>Story Bible</strong>
              <p>人物动机、核心悬念、改编建议</p>
            </div>
          </div>
          <div className="pipeline-card active">
            <span>03</span>
            <div>
              <strong>Scene Workspace</strong>
              <p>目标、冲突、转折、对白与镜头备注</p>
            </div>
          </div>
        </div>
      </section>

      <div className="feature-grid" aria-label="产品流程">
        {productSteps.map((step) => (
          <FeatureCard key={step.title} {...step} />
        ))}
      </div>

      <form className="workbench-card" onSubmit={handleAnalyze} aria-busy={isBusy}>
        <div className="workbench-header">
          <div>
            <p className="eyebrow">Create Project</p>
            <h2>创建分析任务</h2>
            <p>上传 TXT 或粘贴章节正文，选择生成模式后进入分析工作台。</p>
          </div>
          <div className="mode-switch" aria-label="生成模式">
            <button
              className={analysisMode === "api" ? "active" : ""}
              type="button"
              onClick={() => setAnalysisMode("api")}
            >
              <WandSparkles size={17} />
              AI API
            </button>
            <button
              className={analysisMode === "mock" ? "active" : ""}
              type="button"
              onClick={() => setAnalysisMode("mock")}
            >
              <BadgeCheck size={17} />
              Mock
            </button>
          </div>
        </div>

        <div className="workbench-grid">
          <section className="input-panel" aria-label="小说输入">
            <div className="field-row">
              <label className="field-group">
                <span>项目标题</span>
                <input value={title} onChange={(event) => setTitle(event.target.value)} />
              </label>
              <label className="field-group file-field">
                <span>TXT 文件</span>
                <input accept=".txt,text/plain" type="file" onChange={(event) => setFile(event.target.files[0] || null)} />
              </label>
            </div>
            <label className="field-group">
              <span>小说文本</span>
              <textarea value={text} onChange={(event) => setText(event.target.value)} rows={12} />
            </label>
          </section>

          <aside className="run-panel" aria-label="分析状态">
            <div className="run-panel-top">
              <span className="run-icon">
                <Layers3 size={20} />
              </span>
              <div>
                <strong>{analysisMode === "api" ? "AI API 模式" : "Mock 演示模式"}</strong>
                <p>{analysisMode === "api" ? "调用已配置的小米 MiMo API。" : "使用本地模拟结果，适合离线演示。"}</p>
              </div>
            </div>

            <div className="progress-panel" aria-label="分析进度">
              {progressSteps.map((step, index) => (
                <div className={progressClass(index, progressIndex, statusType)} key={step}>
                  <span>{index + 1}</span>
                  <strong>{step}</strong>
                </div>
              ))}
            </div>

            {isBusy && (
              <div className="skeleton-stack" aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
            )}

            <div className="submit-row">
              <button disabled={isBusy || (!file && !text.trim())} type="submit">
                {isBusy ? <LoaderCircle className="spin-icon" size={17} /> : <Play size={17} />}
                {isBusy ? "分析中" : "开始生成"}
              </button>
              {status && <span className={statusType === "error" ? "status-error" : ""}>{status}</span>}
            </div>
          </aside>
        </div>
      </form>
    </section>
  );
}

function FeatureCard({ detail, icon: Icon, title }) {
  return (
    <article className="feature-card">
      <span className="feature-icon">
        <Icon size={19} />
      </span>
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
