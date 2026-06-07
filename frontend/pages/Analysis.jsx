import { FileText, MapPin, UsersRound } from "lucide-react";

import { chapters, scriptYaml } from "../src/sampleData.js";

export default function Analysis() {
  const totalWords = chapters.reduce((sum, chapter) => sum + chapter.wordCount, 0);

  return (
    <section className="workspace">
      <div className="metric-grid" aria-label="分析摘要">
        <Metric label="章节" value={chapters.length} />
        <Metric label="人物" value={scriptYaml.characters.length} />
        <Metric label="地点" value={scriptYaml.locations.length} />
        <Metric label="字数" value={totalWords.toLocaleString("zh-CN")} />
      </div>

      <section className="section-block">
        <SectionHeading icon={<FileText size={18} />} title="章节列表" />
        <div className="chapter-list">
          {chapters.map((chapter, index) => (
            <article className="chapter-row" key={chapter.id}>
              <span className="row-index">{index + 1}</span>
              <div>
                <h2>{chapter.title}</h2>
                <p>{chapter.summary}</p>
              </div>
              <div className="row-meta">
                <span>{chapter.wordCount.toLocaleString("zh-CN")} 字</span>
                <span>{chapter.status}</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <div className="split-grid">
        <section className="section-block">
          <SectionHeading icon={<UsersRound size={18} />} title="人物表" />
          <DataTable
            columns={["ID", "姓名", "定位", "描述"]}
            rows={scriptYaml.characters.map((character) => [
              character.id,
              character.name,
              character.role,
              character.description,
            ])}
          />
        </section>

        <section className="section-block">
          <SectionHeading icon={<MapPin size={18} />} title="地点表" />
          <DataTable
            columns={["ID", "地点", "描述"]}
            rows={scriptYaml.locations.map((location) => [location.id, location.name, location.description])}
          />
        </section>
      </div>
    </section>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SectionHeading({ icon, title }) {
  return (
    <div className="section-heading">
      <span className="heading-icon">{icon}</span>
      <h2>{title}</h2>
    </div>
  );
}

function DataTable({ columns, rows }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.join("-")}>
              {row.map((cell, index) => (
                <td key={`${cell}-${index}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
