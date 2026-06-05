import { Download, FileCode2, FileText } from "lucide-react";

import { scriptYaml as sampleScriptYaml } from "../src/sampleData.js";

export default function Export({ scriptYaml = sampleScriptYaml }) {
  const yamlText = toYaml(scriptYaml);
  const markdownText = toMarkdown(scriptYaml);

  return (
    <section className="workspace">
      <div className="export-grid">
        <ExportPanel
          description="script_yaml.yaml"
          icon={<FileCode2 size={22} />}
          onDownload={() => downloadText("script_yaml.yaml", yamlText, "text/yaml;charset=utf-8")}
          preview={yamlText}
          title="YAML"
        />
        <ExportPanel
          description="script_preview.md"
          icon={<FileText size={22} />}
          onDownload={() => downloadText("script_preview.md", markdownText, "text/markdown;charset=utf-8")}
          preview={markdownText}
          title="Markdown"
        />
      </div>
    </section>
  );
}

function ExportPanel({ description, icon, onDownload, preview, title }) {
  return (
    <section className="export-panel">
      <div className="export-heading">
        <span className="heading-icon">{icon}</span>
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <button type="button" onClick={onDownload}>
          <Download size={16} />
          下载
        </button>
      </div>
      <pre className="export-preview">{preview}</pre>
    </section>
  );
}

function downloadText(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function toMarkdown(data) {
  const characterById = new Map(data.characters.map((character) => [character.id, character]));
  const locationById = new Map(data.locations.map((location) => [location.id, location]));
  const lines = [`# ${data.project.title}`, "", `> ${data.project.logline || ""}`, ""];

  for (const scene of data.scenes) {
    const location = locationById.get(scene.location_id);
    lines.push(`## ${scene.title}`, "");
    lines.push(`- 地点：${location?.name || scene.location_id}`);
    lines.push(`- 人物：${scene.characters.map((id) => characterById.get(id)?.name || id).join(" / ")}`);
    lines.push("");

    for (const scriptLine of data.script.filter((line) => line.scene_id === scene.id)) {
      if (scriptLine.type === "dialogue") {
        const character = characterById.get(scriptLine.character_id);
        lines.push(`**${character?.name || scriptLine.character_id}**：${scriptLine.content}`);
      } else {
        lines.push(`_${scriptLine.type}_：${scriptLine.content}`);
      }
      lines.push("");
    }
  }

  return lines.join("\n").trim() + "\n";
}

function toYaml(value) {
  return `${dumpYaml(value, 0).join("\n")}\n`;
}

function dumpYaml(value, indent) {
  if (Array.isArray(value)) {
    return dumpYamlList(value, indent);
  }
  if (value && typeof value === "object") {
    return dumpYamlObject(value, indent);
  }
  return [`${" ".repeat(indent)}${formatScalar(value)}`];
}

function dumpYamlObject(value, indent) {
  const lines = [];
  for (const [key, item] of Object.entries(value)) {
    if (Array.isArray(item) || (item && typeof item === "object")) {
      lines.push(`${" ".repeat(indent)}${key}:`);
      lines.push(...dumpYaml(item, indent + 2));
    } else {
      lines.push(`${" ".repeat(indent)}${key}: ${formatScalar(item)}`);
    }
  }
  return lines;
}

function dumpYamlList(value, indent) {
  const lines = [];
  for (const item of value) {
    if (item && typeof item === "object" && !Array.isArray(item)) {
      const entries = Object.entries(item);
      const [firstKey, firstValue] = entries[0];
      lines.push(`${" ".repeat(indent)}- ${firstKey}: ${formatScalar(firstValue)}`);
      for (const [key, nestedValue] of entries.slice(1)) {
        if (Array.isArray(nestedValue) || (nestedValue && typeof nestedValue === "object")) {
          lines.push(`${" ".repeat(indent + 2)}${key}:`);
          lines.push(...dumpYaml(nestedValue, indent + 4));
        } else {
          lines.push(`${" ".repeat(indent + 2)}${key}: ${formatScalar(nestedValue)}`);
        }
      }
    } else {
      lines.push(`${" ".repeat(indent)}- ${formatScalar(item)}`);
    }
  }
  return lines;
}

function formatScalar(value) {
  if (value === null || value === undefined) {
    return "null";
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  const text = String(value);
  if (!text || /^[\d.]+$/.test(text) || /[:#\n]/.test(text) || text.trim() !== text) {
    return JSON.stringify(text);
  }
  return text;
}
