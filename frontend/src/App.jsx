import {
  BadgeCheck,
  BookOpenText,
  Clapperboard,
  Download,
  House,
  Moon,
  Sparkles,
  Sun,
} from "lucide-react";
import { useEffect, useState } from "react";

import Analysis from "../pages/Analysis.jsx";
import Export from "../pages/Export.jsx";
import Home from "../pages/Home.jsx";
import ScriptPreview from "../pages/ScriptPreview.jsx";
import { chapters as sampleChapters, scriptYaml as sampleScriptYaml } from "./sampleData.js";

const STORAGE_KEY = "scriptwhisper.project";
const THEME_KEY = "scriptwhisper.theme";

const navItems = [
  {
    id: "home",
    label: "首页",
    icon: House,
    title: "ScriptWhisper",
    description: "AI 小说转剧本的创建入口与工作流总览。",
  },
  {
    id: "analysis",
    label: "分析",
    icon: BookOpenText,
    title: "Novel Analysis",
    description: "查看章节结构、Story Bible、人物地点和原文证据。",
  },
  {
    id: "preview",
    label: "预览",
    icon: Clapperboard,
    title: "Screenplay Workspace",
    description: "审阅、标记和编辑按场景生成的剧本正文。",
  },
  {
    id: "export",
    label: "导出",
    icon: Download,
    title: "Export",
    description: "将结构化剧本导出为 YAML 与 Markdown 文档。",
  },
];

export default function App() {
  const [activePage, setActivePage] = useState("home");
  const [project, setProject] = useState(loadInitialProject);
  const [theme, setTheme] = useState(loadInitialTheme);
  const page = navItems.find((item) => item.id === activePage) || navItems[0];
  const sceneCount = project.scriptYaml?.scenes?.length || 0;

  useEffect(() => {
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

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
    <main className="app-shell" data-theme={theme}>
      <aside className="app-sidebar">
        <div className="brand-block">
          <span className="brand-mark" aria-hidden="true">
            SW
          </span>
          <div>
            <strong>ScriptWhisper</strong>
            <span>AI Script Studio</span>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="工作台导航">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={`sidebar-nav-item ${activePage === item.id ? "active" : ""}`}
                key={item.id}
                type="button"
                onClick={() => setActivePage(item.id)}
              >
                <Icon size={17} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-status">
            <span className="status-dot" aria-hidden="true" />
            <div>
              <strong>{project.scriptYaml?.project?.title || "未命名项目"}</strong>
              <span>{sceneCount} scenes ready</span>
            </div>
          </div>
        </div>
      </aside>

      <section className="app-content">
        <header className="topbar">
          <div className="topbar-title">
            <p className="eyebrow">{page.label}</p>
            <h1>{page.title}</h1>
            <p>{page.description}</p>
          </div>
          <div className="topbar-actions">
            <span className="status-chip">
              <Sparkles size={14} />
              {project.mockMode ? "Mock Mode" : "AI API Mode"}
            </span>
            <span className="status-chip">
              <BadgeCheck size={14} />
              {project.repaired ? "Auto Repaired" : "Schema Validated"}
            </span>
            <button
              className="icon-button"
              type="button"
              aria-label={theme === "dark" ? "切换到浅色主题" : "切换到深色主题"}
              title={theme === "dark" ? "浅色主题" : "深色主题"}
              onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </header>

        <div className="page-body">
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
            <ScriptPreview
              chapters={project.chapters}
              onScriptYamlChange={handleScriptYamlChange}
              scriptYaml={project.scriptYaml}
            />
          )}
          {activePage === "export" && <Export chapters={project.chapters} scriptYaml={project.scriptYaml} />}
        </div>
      </section>
    </main>
  );
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

function loadInitialTheme() {
  try {
    return window.localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function normalizeChapters(chapters) {
  return chapters.map((chapter, index) => ({
    id: chapter.chapter_id || chapter.id || `chapter_${index + 1}`,
    chapterId: chapter.chapter_id || chapter.id || `chapter_${index + 1}`,
    chapterIndex: chapter.chapter_index || chapter.chapterIndex || index + 1,
    title: chapter.title || chapter.heading || `章节 ${index + 1}`,
    content: chapter.content || "",
    summary: chapter.summary || "",
    wordCount: chapter.wordCount ?? chapter.word_count ?? (chapter.content || "").length,
    status: chapter.status || "已分析",
  }));
}
