import { CheckCircle2, Clipboard, Download, FileCode2, FileText, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { chapters as sampleChapters, scriptYaml as sampleScriptYaml } from "../src/sampleData.js";

const highlightLabels = {
  "#fff3a3": "黄色标记",
  "#cfe8ff": "蓝色标记",
  "#d8f5d2": "绿色标记",
  "#ffd8d2": "红色标记",
  yellow: "黄色标记",
  blue: "蓝色标记",
  green: "绿色标记",
  red: "红色标记",
};

const typeLabels = {
  action: "动作",
  camera: "镜头",
  dialogue: "对白",
  narration: "旁白",
  note: "备注",
  transition: "转场",
};

export default function Export({ chapters = sampleChapters, scriptYaml = sampleScriptYaml }) {
  const normalizedChapters = useMemo(() => normalizeChapters(chapters), [chapters]);
  const exportData = useMemo(() => sanitizeForExport(scriptYaml, normalizedChapters), [scriptYaml, normalizedChapters]);
  const exportChapters = useMemo(
    () => (normalizedChapters.length ? normalizedChapters : chaptersFromScenes(exportData.scenes || [])),
    [exportData, normalizedChapters],
  );
  const validation = useMemo(() => validateScriptYaml(exportData, exportChapters), [exportData, exportChapters]);
  const yamlText = toYaml(exportData);
  const markdownText = toMarkdown(exportData, exportChapters);
  const baseFilename = safeFilename(exportData.project?.title || "ScriptWhisper");
  const isReady = Object.values(validation).every((item) => item.ok);

  return (
    <section className="workspace export-workspace">
      <section className="page-intro-panel export-intro">
        <div>
          <p className="eyebrow">Structured Output</p>
          <h2>导出可校验的剧本文档</h2>
          <p>将当前 ScriptYAML 快照和 Markdown 剧本稿保存为可交付、可继续加工的结构化文件。</p>
        </div>
        <span className={`export-ready-badge ${isReady ? "ready" : "blocked"}`}>
          <ShieldCheck size={15} />
          {isReady ? "Ready to Export" : "Needs Review"}
        </span>
      </section>

      <div className="export-summary-grid" aria-label="导出摘要">
        <SummaryItem label="Project Title" value={exportData.project?.title || "未命名项目"} />
        <SummaryItem label="Chapters" value={exportChapters.length} />
        <SummaryItem label="Scenes" value={(exportData.scenes || []).length} />
        <SummaryItem label="Script Lines" value={(exportData.script || []).length} />
        <SummaryItem label="Validation" value={isReady ? "Passed" : "Review"} />
      </div>

      <section className="panel validation-panel">
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
          <ValidationItem label="章节来源校验" result={validation.sourceRefs} />
        </div>
      </section>

      <div className="export-grid">
        <ExportPanel
          copyLabel="复制 YAML"
          description={`${baseFilename}_ScriptYAML.yaml`}
          icon={<FileCode2 size={20} />}
          onDownload={() => downloadText(`${baseFilename}_ScriptYAML.yaml`, yamlText, "text/yaml;charset=utf-8")}
          preview={yamlText}
          title="YAML"
        />
        <ExportPanel
          copyLabel="复制 Markdown"
          description={`${baseFilename}_剧本预览.md`}
          icon={<FileText size={20} />}
          onDownload={() => downloadText(`${baseFilename}_剧本预览.md`, markdownText, "text/markdown;charset=utf-8")}
          preview={markdownText}
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
    <section className="export-panel code-panel">
      <div className="export-heading">
        <span className="heading-icon">{icon}</span>
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        <div className="export-actions">
          <button type="button" onClick={copyPreview}>
            <Clipboard size={15} />
            {copied ? "已复制" : copyLabel}
          </button>
          <button type="button" onClick={onDownload}>
            <Download size={15} />
            下载
          </button>
        </div>
      </div>
      <pre className="export-preview">{preview}</pre>
    </section>
  );
}

function SummaryItem({ label, value }) {
  return (
    <article className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function toMarkdown(data, chapters) {
  const characterById = new Map((data.characters || []).map((character) => [character.id, character]));
  const locationById = new Map((data.locations || []).map((location) => [location.id, location]));
  const lines = [`# ${data.project?.title || "未指定"}`, ""];
  if (data.project?.logline) {
    lines.push(`> ${data.project.logline}`, "");
  }

  for (const chapter of chapters) {
    const chapterScenes = (data.scenes || []).filter((scene) => scene.source_ref?.chapter_id === chapter.id);
    lines.push(`## ${chapter.title}`, "");
    if (!chapterScenes.length) {
      lines.push("当前章节还没有生成场景。", "");
      continue;
    }

    for (const scene of chapterScenes) {
      const location = locationById.get(scene.location_id);
      const sceneIndex = data.scenes.findIndex((item) => item.id === scene.id) + 1;
      lines.push(`### S${sceneIndex} ${scene.title}`, "");
      if (scene.summary) {
        lines.push(scene.summary, "");
      }
      lines.push(`- 来源章节：${scene.source_ref?.chapter_title || chapter.title}`);
      if (scene.source_ref?.excerpt) {
        lines.push(`- 原文依据：${scene.source_ref.excerpt}`);
      }
      if (location || scene.location_id) {
        lines.push(`- 地点：${location?.name || scene.location_id}`);
      }
      const characterNames = (scene.characters || []).map((id) => characterById.get(id)?.name || id).filter(Boolean);
      if (characterNames.length) {
        lines.push(`- 人物：${characterNames.join(" / ")}`);
      }
      lines.push("");

      for (const scriptLine of (data.script || []).filter((line) => line.scene_id === scene.id)) {
        const content = scriptLine.text || scriptLine.content || "";
        if (!content) {
          continue;
        }
        lines.push(formatScriptLine(scriptLine, content, characterById));
        if (scriptLine.note) {
          lines.push(`> 备注：${scriptLine.note}`);
        }
        lines.push("");
      }
    }
  }

  return lines.join("\n").trim() + "\n";
}

function formatScriptLine(scriptLine, content, characterById) {
  const highlight = highlightLabel(scriptLine.highlight_color);
  const highlightText = highlight ? `【${highlight}】` : "";
  if (scriptLine.type === "dialogue") {
    const character = characterById.get(scriptLine.character_id || scriptLine.speaker_id);
    const speaker = scriptLine.speaker_name || character?.name || scriptLine.speaker_id || scriptLine.character_id || "未指定";
    const emotion = scriptLine.emotion ? `（${scriptLine.emotion}）` : "";
    return `**${speaker}**${emotion}：${highlightText}${content}`;
  }
  return `_${typeLabels[scriptLine.type] || scriptLine.type}_：${highlightText}${content}`;
}

function highlightLabel(value) {
  if (!value) {
    return "";
  }
  return highlightLabels[String(value).trim().toLowerCase()] || `${value}标记`;
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
      if (!entries.length) {
        continue;
      }
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
    } else if (!isEmptyExportValue(item)) {
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

function sanitizeForExport(value, chapters) {
  return repairSourceRefs(removeEmptyFields(value), chapters);
}

function repairSourceRefs(value, chapters) {
  const data = structuredClone(value);
  const chapterRefs = chapters.length ? chapters : [{ id: "chapter_1", chapterIndex: 1, title: "第 1 章" }];
  const chapterIds = new Set(chapterRefs.map((chapter) => chapter.id));

  data.scenes = (data.scenes || []).map((scene, index) => {
    const source = scene.source_ref || {};
    const requestedIndex = Number(source.chapter_index || source.chapterIndex);
    let chapter = source.chapter_id && chapterIds.has(source.chapter_id) ? chapterRefs.find((item) => item.id === source.chapter_id) : null;
    if (!chapter && Number.isFinite(requestedIndex)) {
      const clampedIndex = Math.min(Math.max(requestedIndex, 1), chapterRefs.length);
      chapter = chapterRefs[clampedIndex - 1];
    }
    if (!chapter) {
      chapter = chapterRefs[Math.min(index, chapterRefs.length - 1)];
    }
    return {
      ...scene,
      source_ref: removeEmptyFields({
        chapter_id: chapter.id,
        chapter_index: chapter.chapterIndex,
        chapter_title: chapter.title,
        excerpt: source.excerpt || source.evidence || source.text,
        paragraph_range: source.paragraph_range,
      }),
    };
  });
  return removeEmptyFields(data);
}

function normalizeChapters(chapters) {
  return (chapters || []).map((chapter, index) => {
    const chapterIndex = chapter.chapter_index || chapter.chapterIndex || index + 1;
    return {
      ...chapter,
      id: chapter.chapter_id || chapter.chapterId || chapter.id || `chapter_${chapterIndex}`,
      chapterIndex,
      title: chapter.title || chapter.heading || `第 ${chapterIndex} 章`,
    };
  });
}

function chaptersFromScenes(scenes) {
  const chapters = [];
  const seen = new Set();
  for (const scene of scenes) {
    const source = scene.source_ref || {};
    const id = source.chapter_id || "chapter_1";
    if (seen.has(id)) {
      continue;
    }
    seen.add(id);
    chapters.push({
      id,
      chapterIndex: source.chapter_index || chapters.length + 1,
      title: source.chapter_title || `第 ${chapters.length + 1} 章`,
    });
  }
  return chapters.length ? chapters : [{ id: "chapter_1", chapterIndex: 1, title: "第 1 章" }];
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

function validateScriptYaml(data, chapters) {
  const characters = data.characters || [];
  const locations = data.locations || [];
  const scenes = data.scenes || [];
  const script = data.script || [];
  const characterIds = new Set(characters.map((character) => character.id));
  const locationIds = new Set(locations.map((location) => location.id));
  const chapterIds = new Set(chapters.map((chapter) => chapter.id));
  const sceneIds = new Set(scenes.map((scene) => scene.id));
  const sceneCharacterIssues = scenes.flatMap((scene) =>
    (scene.characters || []).filter((id) => !characterIds.has(id)).map((id) => `${scene.id} -> ${id}`),
  );
  const locationIssues = scenes
    .filter((scene) => !locationIds.has(scene.location_id))
    .map((scene) => `${scene.id} -> ${scene.location_id}`);
  const scriptIssues = script.filter((line) => !sceneIds.has(line.scene_id)).map((line) => line.scene_id);
  const sourceIssues = scenes
    .filter((scene) => !chapterIds.has(scene.source_ref?.chapter_id))
    .map((scene) => `${scene.id} -> ${scene.source_ref?.chapter_id || "missing"}`);

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
      message:
        locationIssues.length || scriptIssues.length ? [...locationIssues, ...scriptIssues].join("；") : "地点与场景引用有效",
    },
    sourceRefs: {
      ok: sourceIssues.length === 0,
      message: sourceIssues.length ? sourceIssues.join("；") : "章节来源引用有效",
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

function downloadText(filename, text, mimeType) {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
