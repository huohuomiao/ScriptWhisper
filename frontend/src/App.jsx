import { BookOpenText, Clapperboard, Download, House } from "lucide-react";
import { useState } from "react";

import Analysis from "../pages/Analysis.jsx";
import Export from "../pages/Export.jsx";
import Home from "../pages/Home.jsx";
import ScriptPreview from "../pages/ScriptPreview.jsx";
import { chapters as sampleChapters, scriptYaml as sampleScriptYaml } from "./sampleData.js";

const STORAGE_KEY = "scriptwhisper.project";

export default function App() {
  const [activePage, setActivePage] = useState("home");
  const [project, setProject] = useState(loadInitialProject);

  function updateProject(nextProject) {
    setProject(nextProject);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextProject));
  }

  function handleAnalysisComplete(result) {
    updateProject({
      chapters: normalizeChapters(result.chapters),
      issues: result.issues || [],
      mockMode: result.mock_mode,
      repaired: result.repaired,
      scriptYaml: result.script_yaml,
    });
    setActivePage("analysis");
  }

  function handleScriptYamlChange(nextYaml) {
    updateProject({ ...project, scriptYaml: nextYaml });
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">ScriptWhisper</p>
          <h1>{pageTitle(activePage)}</h1>
        </div>
        <nav className="nav-tabs" aria-label="工作台导航">
          <button
            className={`nav-tab ${activePage === "home" ? "active" : ""}`}
            type="button"
            onClick={() => setActivePage("home")}
          >
            <House size={16} />
            首页
          </button>
          <button
            className={`nav-tab ${activePage === "analysis" ? "active" : ""}`}
            type="button"
            onClick={() => setActivePage("analysis")}
          >
            <BookOpenText size={16} />
            分析
          </button>
          <button
            className={`nav-tab ${activePage === "preview" ? "active" : ""}`}
            type="button"
            onClick={() => setActivePage("preview")}
          >
            <Clapperboard size={16} />
            预览
          </button>
          <button
            className={`nav-tab ${activePage === "export" ? "active" : ""}`}
            type="button"
            onClick={() => setActivePage("export")}
          >
            <Download size={16} />
            导出
          </button>
        </nav>
      </header>
      {activePage === "home" && <Home onAnalysisComplete={handleAnalysisComplete} />}
      {activePage === "analysis" && (
        <Analysis
          chapters={project.chapters}
          issues={project.issues}
          mockMode={project.mockMode}
          repaired={project.repaired}
          scriptYaml={project.scriptYaml}
        />
      )}
      {activePage === "preview" && (
        <ScriptPreview onScriptYamlChange={handleScriptYamlChange} scriptYaml={project.scriptYaml} />
      )}
      {activePage === "export" && <Export scriptYaml={project.scriptYaml} />}
    </main>
  );
}

function pageTitle(activePage) {
  if (activePage === "home") {
    return "ScriptWhisper";
  }
  if (activePage === "preview") {
    return "剧本预览";
  }
  if (activePage === "export") {
    return "导出";
  }
  return "小说分析";
}

function loadInitialProject() {
  const fallback = {
    chapters: sampleChapters,
    issues: [],
    mockMode: true,
    repaired: false,
    scriptYaml: sampleScriptYaml,
  };

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored ? { ...fallback, ...JSON.parse(stored) } : fallback;
  } catch {
    return fallback;
  }
}

function normalizeChapters(chapters) {
  return chapters.map((chapter, index) => ({
    id: chapter.id || `chapter_${index + 1}`,
    title: chapter.title || chapter.heading || `章节 ${index + 1}`,
    summary: chapter.summary || "",
    wordCount: chapter.wordCount ?? chapter.word_count ?? (chapter.content || "").length,
    status: chapter.status || "已分析",
  }));
}
