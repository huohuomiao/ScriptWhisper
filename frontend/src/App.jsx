import { BookOpenText, Clapperboard, Download, House } from "lucide-react";
import { useState } from "react";

import Analysis from "../pages/Analysis.jsx";
import Export from "../pages/Export.jsx";
import Home from "../pages/Home.jsx";
import ScriptPreview from "../pages/ScriptPreview.jsx";

export default function App() {
  const [activePage, setActivePage] = useState("home");

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
      {activePage === "home" && <Home />}
      {activePage === "analysis" && <Analysis />}
      {activePage === "preview" && <ScriptPreview />}
      {activePage === "export" && <Export />}
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
