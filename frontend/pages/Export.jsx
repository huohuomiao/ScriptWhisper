import { CheckCircle2, Clipboard, Download, FileCode2, FileText, ShieldCheck } from "lucide-react";
import { memo, useMemo, useState } from "react";

const highlightLabels = {
  "#fff3a3": "preview.color.yellowMark",
  "#cfe8ff": "preview.color.blueMark",
  "#d8f5d2": "preview.color.greenMark",
  "#ffd8d2": "preview.color.redMark",
  yellow: "preview.color.yellowMark",
  blue: "preview.color.blueMark",
  green: "preview.color.greenMark",
  red: "preview.color.redMark",
  purple: "preview.color.purpleMark",
};

const typeLabels = {
  action: "preview.filter.action",
  camera: "preview.filter.camera",
  dialogue: "preview.filter.dialogue",
  narration: "preview.filter.narration",
  note: "preview.filter.note",
  transition: "preview.filter.transition",
};

const EMPTY_ANNOTATIONS = [];

export default function Export({ chapters = [], currentProject = null, scriptYaml = emptyScriptYaml(), t = (key) => key }) {
  const [activeFormat, setActiveFormat] = useState("yaml");
  const [copiedFormat, setCopiedFormat] = useState("");
  const [includeChapterNotes, setIncludeChapterNotes] = useState(true);
  const normalizedChapters = useMemo(() => normalizeChapters(chapters), [chapters]);
  const exportData = useMemo(() => sanitizeForExport(scriptYaml, normalizedChapters), [scriptYaml, normalizedChapters]);
  const exportChapters = useMemo(
    () => (normalizedChapters.length ? normalizedChapters : chaptersFromScenes(exportData.scenes || [])),
    [exportData, normalizedChapters],
  );
  const validation = useMemo(() => validateScriptYaml(exportData, exportChapters, t), [exportData, exportChapters, t]);
  const chapterAnnotations = currentProject?.chapterAnnotations || EMPTY_ANNOTATIONS;
  const markdownAnnotations = includeChapterNotes ? chapterAnnotations : EMPTY_ANNOTATIONS;
  const yamlText = useMemo(() => (activeFormat === "yaml" ? toYaml(exportData) : ""), [activeFormat, exportData]);
  const markdownText = useMemo(
    () => (activeFormat === "markdown" ? toMarkdown(exportData, exportChapters, t, markdownAnnotations) : ""),
    [activeFormat, exportChapters, exportData, markdownAnnotations, t],
  );
  const activeOutputText = activeFormat === "markdown" ? markdownText : yamlText;
  const baseFilename = safeFilename(exportData.project?.title || "ScriptWhisper");
  const isReady = Object.values(validation).every((item) => item.ok);
  const outputs = useMemo(() => [
    {
      id: "yaml",
      copyLabel: t("export.copyYaml"),
      description: `${baseFilename}_ScriptYAML.yaml`,
      icon: FileCode2,
      label: "YAML",
      mimeType: "text/yaml;charset=utf-8",
    },
    {
      id: "markdown",
      copyLabel: t("export.copyMarkdown"),
      description: `${baseFilename}_剧本预览.md`,
      icon: FileText,
      label: "Markdown",
      mimeType: "text/markdown;charset=utf-8",
    },
  ], [baseFilename, t]);
  const activeOutput = useMemo(() => {
    const definition = outputs.find((output) => output.id === activeFormat) || outputs[0];
    return { ...definition, text: activeOutputText };
  }, [activeFormat, activeOutputText, outputs]);

  async function copyActiveOutput() {
    await navigator.clipboard.writeText(activeOutput.text);
    setCopiedFormat(activeOutput.id);
    window.setTimeout(() => setCopiedFormat(""), 1400);
  }

  function downloadActiveOutput() {
    downloadText(activeOutput.description, activeOutput.text, activeOutput.mimeType);
  }

  if (!currentProject) {
    return (
      <section className="workspace export-workspace">
        <p className="empty-state">{t("export.empty")}</p>
      </section>
    );
  }

  return (
    <section className="workspace export-workspace">
      <section className="delivery-toolbar panel" aria-label={t("export.summaryAria")}>
        <div className="delivery-status">
          <span className={`export-ready-badge ${isReady ? "ready" : "blocked"}`}>
            <ShieldCheck size={15} />
            {isReady ? t("export.ready") : t("export.needsReview")}
          </span>
          <div>
            <strong>{t("export.title")}</strong>
            <span>{activeOutput.description}</span>
          </div>
        </div>
        <div className="delivery-actions">
          <button type="button" onClick={copyActiveOutput}>
            <Clipboard size={15} />
            {copiedFormat === activeOutput.id ? t("export.copied") : activeOutput.copyLabel}
          </button>
          <button className="primary" type="button" onClick={downloadActiveOutput}>
            <Download size={15} />
            {t("export.download")}
          </button>
        </div>
      </section>

      <section className="validation-strip" aria-label={t("export.validation")}>
        <ValidationPill label={t("export.schemaStatus")} result={validation.schema} t={t} />
        <ValidationPill label={t("export.characterCheck")} result={validation.characters} t={t} />
        <ValidationPill label={t("export.locationCheck")} result={validation.locations} t={t} />
        <ValidationPill label={t("export.sourceCheck")} result={validation.sourceRefs} t={t} />
      </section>

      <div className="export-workbench-grid">
        <aside className="delivery-side-panel panel">
          <p className="eyebrow">{t("export.overline")}</p>
          <div className="delivery-summary-list">
            <SummaryItem label={t("home.field.title")} value={exportData.project?.title || t("app.project.untitled")} />
            <SummaryItem label={t("analysis.metric.chapters")} value={exportChapters.length} />
            <SummaryItem label={t("analysis.metric.scenes")} value={(exportData.scenes || []).length} />
            <SummaryItem label={t("export.scriptLines")} value={(exportData.script || []).length} />
          </div>
          <label className="export-note-toggle">
            <input checked={includeChapterNotes} type="checkbox" onChange={(event) => setIncludeChapterNotes(event.target.checked)} />
            {t("export.includeNotes")}
          </label>
        </aside>

        <section className="export-output-panel panel">
          <div className="export-output-tabs" role="tablist" aria-label="Export formats">
            {outputs.map((output) => {
              const Icon = output.icon;
              return (
                <button
                  className={activeFormat === output.id ? "active" : ""}
                  key={output.id}
                  role="tab"
                  type="button"
                  aria-selected={activeFormat === output.id}
                  onClick={() => setActiveFormat(output.id)}
                >
                  <Icon size={15} />
                  {output.label}
                </button>
              );
            })}
          </div>
          <CodePreviewPanel output={activeOutput} />
        </section>
      </div>
    </section>
  );
}

const CodePreviewPanel = memo(function CodePreviewPanel({ output }) {
  const Icon = output.icon;

  return (
    <section className="code-panel export-code-view">
      <div className="export-heading">
        <span className="heading-icon">
          <Icon size={20} />
        </span>
        <div>
          <h2>{output.label}</h2>
          <p>{output.description}</p>
        </div>
      </div>
      <pre className="export-preview">{output.text}</pre>
    </section>
  );
});

function SummaryItem({ label, value }) {
  return (
    <article className="summary-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function ValidationPill({ label, result, t }) {
  return (
    <article className={`validation-pill ${result.ok ? "valid" : "invalid"}`} title={result.ok ? t("export.pass") : result.message}>
      <CheckCircle2 size={16} />
      <strong>{label}</strong>
      <span>{result.ok ? t("export.pass") : result.message}</span>
    </article>
  );
}

function toMarkdown(data, chapters, t, chapterAnnotations = []) {
  const characterById = new Map((data.characters || []).map((character) => [character.id, character]));
  const locationById = new Map((data.locations || []).map((location) => [location.id, location]));
  const lines = [`# ${data.project?.title || t("app.project.untitled")}`, ""];
  if (data.project?.logline) {
    lines.push(`> ${data.project.logline}`, "");
  }

  for (const chapter of chapters) {
    const chapterScenes = (data.scenes || []).filter((scene) => scene.source_ref?.chapter_id === chapter.id);
    lines.push(`## ${chapter.title}`, "");
    if (!chapterScenes.length) {
      lines.push(t("preview.noScenesForChapter"), "");
      continue;
    }

    for (const scene of chapterScenes) {
      const location = locationById.get(scene.location_id);
      const sceneIndex = data.scenes.findIndex((item) => item.id === scene.id) + 1;
      lines.push(`### S${sceneIndex} ${scene.title}`, "");
      if (scene.summary) {
        lines.push(scene.summary, "");
      }
      lines.push(`- ${t("preview.sourceEvidence")}：${scene.source_ref?.chapter_title || chapter.title}`);
      if (scene.source_ref?.excerpt) {
        lines.push(`- ${t("analysis.sourceEvidence")}：${scene.source_ref.excerpt}`);
      }
      if (location || scene.location_id) {
        lines.push(`- ${t("preview.location")}：${location?.name || scene.location_id}`);
      }
      const characterNames = (scene.characters || []).map((id) => characterById.get(id)?.name || id).filter(Boolean);
      if (characterNames.length) {
        lines.push(`- ${t("preview.characters")}：${characterNames.join(" / ")}`);
      }
      lines.push("");

      for (const scriptLine of (data.script || []).filter((line) => line.scene_id === scene.id)) {
        const content = scriptLine.text || scriptLine.content || "";
        if (!content) {
          continue;
        }
        lines.push(formatScriptLine(scriptLine, content, characterById, t));
        if (scriptLine.note) {
          lines.push(`> ${t("preview.editor.note")}：${scriptLine.note}`);
        }
        lines.push("");
      }
    }
  }

  const notes = (chapterAnnotations || []).filter((annotation) => annotation.note);
  if (notes.length) {
    lines.push(`## ${t("analysis.notes")}`, "");
    for (const note of notes) {
      const chapter = chapters.find((item) => item.id === note.chapterId);
      if (!chapter) {
        continue;
      }
      const selectedText = note.selectedText ? ` / ${t("analysis.selectedText")}：${note.selectedText}` : "";
      lines.push(`- ${chapter.title} / ${t("analysis.paragraphIndex", { index: note.paragraphIndex })}${selectedText}：${note.note}`);
    }
    lines.push("");
  }

  return lines.join("\n").trim() + "\n";
}

function formatScriptLine(scriptLine, content, characterById, t) {
  const highlight = highlightLabel(getLineHighlightColor(scriptLine), t);
  const highlightText = highlight ? `【${highlight}】` : "";
  if (scriptLine.type === "dialogue") {
    const character = characterById.get(scriptLine.character_id || scriptLine.speaker_id);
    const speaker = scriptLine.speaker_name || character?.name || scriptLine.speaker_id || scriptLine.character_id || t("preview.unassigned");
    const emotion = scriptLine.emotion ? `（${scriptLine.emotion}）` : "";
    return `**${speaker}**${emotion}：${highlightText}${content}`;
  }
  return `_${t(typeLabels[scriptLine.type] || scriptLine.type)}_：${highlightText}${content}`;
}

function getLineHighlightColor(line) {
  return Object.prototype.hasOwnProperty.call(line, "highlight_color") ? line.highlight_color : line.highlightColor;
}

function highlightLabel(value, t) {
  if (!value) {
    return "";
  }
  const labelKey = highlightLabels[String(value).trim().toLowerCase()];
  return labelKey ? t(labelKey) : t("preview.color.genericMark", { color: value });
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
  return repairSourceRefs(normalizeExportScript(removeEmptyFields(value)), chapters);
}

function normalizeExportScript(value) {
  const data = structuredClone(value || emptyScriptYaml());
  data.script = (data.script || []).map((line) => {
    const nextLine = { ...line };
    const highlightColor = getLineHighlightColor(nextLine);
    delete nextLine.highlight_color;
    delete nextLine.highlightColor;
    if (highlightColor) {
      nextLine.highlightColor = highlightColor;
    }
    return nextLine;
  });
  return data;
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

function validateScriptYaml(data, chapters, t) {
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
      message: sceneCharacterIssues.length ? sceneCharacterIssues.join("；") : t("export.charactersValid"),
    },
    locations: {
      ok: locationIssues.length === 0 && scriptIssues.length === 0,
      message:
        locationIssues.length || scriptIssues.length ? [...locationIssues, ...scriptIssues].join("；") : t("export.locationsValid"),
    },
    sourceRefs: {
      ok: sourceIssues.length === 0,
      message: sourceIssues.length ? sourceIssues.join("；") : t("export.sourcesValid"),
    },
  };
}

function ValidationItem({ label, result, t }) {
  return (
    <article className={`validation-item ${result.ok ? "valid" : "invalid"}`}>
      <CheckCircle2 size={18} />
      <div>
        <h3>{label}</h3>
        <p>{result.ok ? t("export.pass") : result.message}</p>
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

function emptyScriptYaml() {
  return {
    project: {},
    characters: [],
    locations: [],
    scenes: [],
    script: [],
  };
}
