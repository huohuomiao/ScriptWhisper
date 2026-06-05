import { BadgeCheck, FileText, GitBranch, WandSparkles } from "lucide-react";

export default function Home() {
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
