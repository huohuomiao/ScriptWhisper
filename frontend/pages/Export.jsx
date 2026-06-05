import { CheckCircle2, Clipboard, Download, FileCode2, FileText, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { scriptYaml as sampleScriptYaml } from "../src/sampleData.js";

export default function Export({ scriptYaml = sampleScriptYaml }) {
  const exportData = useMemo(() => sanitizeForExport(scriptYaml), [scriptYaml]);
  const validation = useMemo(() => validateScriptYaml(exportData), [exportData]);
  const yamlText = toYaml(exportData);
  const markdownText = toMarkdown(exportData);
  const baseFilename = safeFilename(exportData.project?.title || "ScriptWhisper");

  return (
    <section className="workspace">
      <section className="section-block validation-panel">
        <div className="section-heading">
          <span className="heading-icon">
            <ShieldCheck size={18} />
          </span>
          <h2>导出校验</h2>
        </div>
        <div className="validation-grid">
          <ValidationItem label="Schema 状态" result={validation.schema} />
          <ValidationItem label="人物 ID 校验" result={validation.characters} />
          <ValidationItem label="地点 ID 校验" result={validation.locations} />
        </div>
      </section>
      <div className="export-grid">
        <ExportPanel
          description={`${baseFilename}_ScriptYAML.yaml`}
          icon={<FileCode2 size={22} />}
          onDownload={() => downloadText(`${baseFilename}_ScriptYAML.yaml`, yamlText, "text/yaml;charset=utf-8")}
          preview={yamlText}
          copyLabel="复制 YAML"
          title="YAML"
        />
        <ExportPanel
          description={`${baseFilename}_ScriptPreview.md`}
          icon={<FileText size={22} />}
          onDownload={() => downloadText(`${baseFilename}_ScriptPreview.md`, markdownText, "text/markdown;charset=utf-8")}
          preview={markdownText}
          copyLabel="复制 Markdown"
          title="Markdown"
        />
      </div>
    </section>
  );
}

function ExportPanel({ copyLabel, description, icon, onDownload, preview, title }) {
  const [copied, setCopied] = useState(false);

  async function copyPreview() {
    await navigator.clipboard.writeText(preview);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <section className="export-panel">
      <div className="export-heading">
        <span className="heading-icon">{icon}</span>
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <div className="export-actions">
          <button type="button" onClick={copyPreview}>
            <Clipboard size={16} />
            {copied ? "已复制" : copyLabel}
          </button>
          <button type="button" onClick={onDownload}>
            <Download size={16} />
            下载
          </button>
        </div>
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
  const lines = [`# ${data.project.title || "未指定"}`, ""];
  if (data.project.logline) {
    lines.push(`> ${data.project.logline}`, "");
  }

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
  return `${dumpYaml(removeEmptyFields(value), 0).join("\n")}\n`;
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
    if (isEmptyExportValue(item)) {
      continue;
    }
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
      const entries = Object.entries(removeEmptyFields(item));
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
    return "未指定";
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

function sanitizeForExport(value) {
  return removeEmptyFields(value);
}

function removeEmptyFields(value) {
  if (Array.isArray(value)) {
    return value.map(removeEmptyFields).filter((item) => !isEmptyExportValue(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([_key, item]) => !isEmptyExportValue(item))
        .map(([key, item]) => [key, removeEmptyFields(item)]),
    );
  }
  return value;
}

function isEmptyExportValue(value) {
  return (
    value === null ||
    value === undefined ||
    value === "" ||
    (Array.isArray(value) && value.length === 0) ||
    (value && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === 0)
  );
}

function validateScriptYaml(data) {
  const characters = data.characters || [];
  const locations = data.locations || [];
  const scenes = data.scenes || [];
  const script = data.script || [];
  const characterIds = new Set(characters.map((character) => character.id));
  const locationIds = new Set(locations.map((location) => location.id));
  const sceneIds = new Set(scenes.map((scene) => scene.id));
  const sceneCharacterIssues = scenes.flatMap((scene) =>
    (scene.characters || []).filter((id) => !characterIds.has(id)).map((id) => `${scene.id} -> ${id}`),
  );
  const locationIssues = scenes
    .filter((scene) => !locationIds.has(scene.location_id))
    .map((scene) => `${scene.id} -> ${scene.location_id}`);
  const scriptIssues = script.filter((line) => !sceneIds.has(line.scene_id)).map((line) => line.scene_id);

  return {
    schema: {
      ok: Boolean(data.project?.title && characters.length && locations.length && scenes.length && script.length),
      message: "project / characters / locations / scenes / script",
    },
    characters: {
      ok: sceneCharacterIssues.length === 0,
      message: sceneCharacterIssues.length ? sceneCharacterIssues.join("；") : "场景人物引用有效",
    },
    locations: {
      ok: locationIssues.length === 0 && scriptIssues.length === 0,
      message: locationIssues.length || scriptIssues.length ? [...locationIssues, ...scriptIssues].join("；") : "地点与场景引用有效",
    },
  };
}

function ValidationItem({ label, result }) {
  return (
    <article className={`validation-item ${result.ok ? "valid" : "invalid"}`}>
      <CheckCircle2 size={18} />
      <div>
        <h3>{label}</h3>
        <p>{result.ok ? "通过" : result.message}</p>
      </div>
    </article>
  );
}

function safeFilename(value) {
  return String(value || "ScriptWhisper")
    .trim()
    .replace(/[\\/:*?"<>|]/g, "_")
    .replace(/\s+/g, "_");
}
