import { BookOpenText, Clapperboard } from "lucide-react";
import { useState } from "react";

import Analysis from "../pages/Analysis.jsx";
import ScriptPreview from "../pages/ScriptPreview.jsx";

export default function App() {
  const [activePage, setActivePage] = useState("analysis");

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">ScriptWhisper</p>
          <h1>{activePage === "analysis" ? "小说分析" : "剧本预览"}</h1>
        </div>
        <nav className="nav-tabs" aria-label="工作台导航">
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
        </nav>
      </header>
      {activePage === "analysis" ? <Analysis /> : <ScriptPreview />}
    </main>
  );
}
