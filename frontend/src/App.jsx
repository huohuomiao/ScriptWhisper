import { BookOpenText } from "lucide-react";

import Analysis from "../pages/Analysis.jsx";

export default function App() {
  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">ScriptWhisper</p>
          <h1>小说分析</h1>
        </div>
        <nav className="nav-tabs" aria-label="工作台导航">
          <span className="nav-tab active">
            <BookOpenText size={16} />
            分析
          </span>
        </nav>
      </header>
      <Analysis />
    </main>
  );
}
