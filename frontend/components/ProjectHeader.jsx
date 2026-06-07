export default function ProjectHeader() {
  return (
    <header className="project-header">
      <div>
        <p className="eyebrow">Novel to Screenplay</p>
        <h1>AI 小说转剧本工具</h1>
        <p className="intro">
          将小说片段整理成带场景、动作和对白的剧本草稿，适合短剧、分镜和影视改编的早期创作。
        </p>
      </div>
      <span className="stack-badge">FastAPI + React</span>
    </header>
  );
}
