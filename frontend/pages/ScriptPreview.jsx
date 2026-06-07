import {
  ArrowDown,
  ArrowUp,
  Camera,
  Edit3,
  Highlighter,
  MessageSquareText,
  MoveRight,
  PencilLine,
  Plus,
  ScrollText,
  StickyNote,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import ReadingToolbar from "../components/ReadingToolbar.jsx";
import SceneEditor from "../components/SceneEditor.jsx";
import { readingClassName, selectedHighlightValue, useReadingSettings } from "../src/readingSettings.js";
import { chapters as sampleChapters, scriptYaml as sampleScriptYaml } from "../src/sampleData.js";

const lineMeta = {
  action: { label: "动作", icon: PencilLine },
  camera: { label: "镜头", icon: Camera },
  dialogue: { label: "对白", icon: MessageSquareText },
  narration: { label: "旁白", icon: ScrollText },
  note: { label: "备注", icon: StickyNote },
  remark: { label: "备注", icon: StickyNote },
  transition: { label: "转场", icon: MoveRight },
};

const lineTypeOptions = [
  ["camera", "镜头"],
  ["action", "动作"],
  ["dialogue", "对白"],
  ["narration", "旁白"],
  ["note", "备注"],
];

export default function ScriptPreview({ chapters = sampleChapters, scriptYaml = sampleScriptYaml, onScriptYamlChange }) {
  const [yamlData, setYamlData] = useState(scriptYaml);
  const { settings, setFontSize, setHighlightColor, setLineHeight } = useReadingSettings();
  const normalizedChapters = useMemo(() => normalizeChapters(chapters), [chapters]);
  const sceneGroups = useMemo(
    () => groupScenesByChapter(yamlData.scenes, normalizedChapters),
    [yamlData.scenes, normalizedChapters],
  );
  const firstChapterId = sceneGroups[0]?.id || "";
  const firstSceneId = sceneGroups.find((group) => group.scenes.length > 0)?.scenes[0]?.id || "";
  const [selectedChapterId, setSelectedChapterId] = useState(firstChapterId);
  const [selectedSceneId, setSelectedSceneId] = useState(firstSceneId);
  const [status, setStatus] = useState("");

  useEffect(() => {
    setYamlData(scriptYaml);
  }, [scriptYaml]);

  useEffect(() => {
    if (!sceneGroups.some((group) => group.id === selectedChapterId)) {
      setSelectedChapterId(firstChapterId);
    }
  }, [firstChapterId, sceneGroups, selectedChapterId]);

  useEffect(() => {
    const selectedGroup = sceneGroups.find((group) => group.id === selectedChapterId);
    const sceneExists = selectedGroup?.scenes.some((scene) => scene.id === selectedSceneId);
    if (!sceneExists) {
      setSelectedSceneId(selectedGroup?.scenes[0]?.id || "");
    }
  }, [sceneGroups, selectedChapterId, selectedSceneId]);

  const selectedGroup = sceneGroups.find((group) => group.id === selectedChapterId);
  const selectedScene = selectedGroup?.scenes.find((scene) => scene.id === selectedSceneId) || null;
  const characterById = useMemo(
    () => new Map(yamlData.characters.map((character) => [character.id, character])),
    [yamlData.characters],
  );
  const locationById = useMemo(
    () => new Map(yamlData.locations.map((location) => [location.id, location])),
    [yamlData.locations],
  );
  const selectedLineEntries = useMemo(
    () =>
      (yamlData.script || [])
        .map((line, index) => ({ index, line: withLineDefaults(line, index) }))
        .filter((entry) => entry.line.scene_id === selectedSceneId),
    [selectedSceneId, yamlData.script],
  );

  function handleYamlChange(nextYaml, message) {
    setYamlData(nextYaml);
    onScriptYamlChange?.(nextYaml);
    setStatus(message);
  }

  function applyScript(nextScript, message) {
    handleYamlChange({ ...yamlData, script: nextScript }, message);
  }

  function selectChapter(group) {
    setSelectedChapterId(group.id);
    setSelectedSceneId(group.scenes[0]?.id || "");
  }

  function selectScene(scene) {
    setSelectedChapterId(getSceneChapterId(scene) || selectedChapterId);
    setSelectedSceneId(scene.id);
  }

  function addLine(line) {
    if (!selectedScene) {
      return;
    }
    const script = [...(yamlData.script || [])];
    const sceneLineIndexes = script.map((item, index) => (item.scene_id === selectedScene.id ? index : -1)).filter((index) => index >= 0);
    const insertAt = sceneLineIndexes.length ? sceneLineIndexes[sceneLineIndexes.length - 1] + 1 : script.length;
    script.splice(
      insertAt,
      0,
      normalizeLineForSave({
        ...line,
        id: nextLineId(script),
        scene_id: selectedScene.id,
      }),
    );
    applyScript(script, "已添加剧本行");
  }

  function updateLine(lineIndex, updates) {
    const script = (yamlData.script || []).map((line, index) =>
      index === lineIndex
        ? normalizeLineForSave({
            ...line,
            id: ensureLineId(line, index),
            ...updates,
          })
        : line,
    );
    applyScript(script, "已更新剧本行");
  }

  function deleteLine(lineIndex) {
    applyScript(
      (yamlData.script || []).filter((_line, index) => index !== lineIndex),
      "已删除剧本行",
    );
  }

  function moveLine(lineIndex, direction) {
    const script = [...(yamlData.script || [])];
    const sceneLineIndexes = script.map((item, index) => (item.scene_id === selectedSceneId ? index : -1)).filter((index) => index >= 0);
    const currentPosition = sceneLineIndexes.indexOf(lineIndex);
    const targetIndex = sceneLineIndexes[currentPosition + direction];
    if (targetIndex === undefined) {
      return;
    }
    [script[lineIndex], script[targetIndex]] = [script[targetIndex], script[lineIndex]];
    applyScript(script, "已调整剧本行顺序");
  }

  function markLine(lineIndex) {
    updateLine(lineIndex, { highlight_color: selectedHighlightValue(settings) });
  }

  function clearCurrentSceneHighlights() {
    if (!selectedScene) {
      return;
    }
    const script = (yamlData.script || []).map((line) => {
      if (line.scene_id !== selectedScene.id || !line.highlight_color) {
        return line;
      }
      const nextLine = { ...line };
      delete nextLine.highlight_color;
      return nextLine;
    });
    applyScript(script, "已清除当前场景标记");
  }

  return (
    <section className="workspace preview-workspace">
      <section className="preview-command-bar">
        <SceneEditor
          onSceneChange={setSelectedSceneId}
          onYamlChange={handleYamlChange}
          scriptYaml={yamlData}
          selectedSceneId={selectedSceneId}
          showSceneSelect={false}
        />
        <ReadingToolbar
          settings={settings}
          onClearHighlight={clearCurrentSceneHighlights}
          onFontSizeChange={setFontSize}
          onHighlightColorChange={setHighlightColor}
          onLineHeightChange={setLineHeight}
        />
      </section>
      {status && <p className="editor-status">{status}</p>}

      <div className="preview-layout">
        <aside className="scene-navigator panel" aria-label="章节和场景选择">
          <div className="navigator-header">
            <div>
              <p className="eyebrow">Scene Map</p>
              <h2>章节 / 场景</h2>
            </div>
            <ScrollText size={18} />
          </div>
          <div className="chapter-scene-list">
            {sceneGroups.map((group) => (
              <div className="chapter-scene-group" key={group.id}>
                <button
                  className={`chapter-selector ${group.id === selectedChapterId ? "active" : ""}`}
                  type="button"
                  onClick={() => selectChapter(group)}
                >
                  <strong>{group.title}</strong>
                  <span>{group.scenes.length} scenes</span>
                </button>
                <div className="scene-selector-list">
                  {group.scenes.length ? (
                    group.scenes.map((scene) => (
                      <button
                        className={`scene-selector ${scene.id === selectedSceneId ? "active" : ""}`}
                        key={scene.id}
                        type="button"
                        onClick={() => selectScene(scene)}
                      >
                        <span>{sceneNumber(yamlData.scenes, scene)}</span>
                        <strong>{scene.title}</strong>
                      </button>
                    ))
                  ) : group.id === selectedChapterId ? (
                    <p className="empty-state compact">当前章节还没有生成场景。</p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </aside>

        <section className="scene-detail-panel">
          {selectedScene ? (
            <SceneDetail
              characterById={characterById}
              characters={yamlData.characters}
              lineEntries={selectedLineEntries}
              lineIndex={yamlData.scenes.findIndex((scene) => scene.id === selectedScene.id) + 1}
              location={locationById.get(selectedScene.location_id)}
              onAddLine={addLine}
              onDeleteLine={deleteLine}
              onMarkLine={markLine}
              onMoveLine={moveLine}
              onUpdateLine={updateLine}
              readingSettings={settings}
              scene={selectedScene}
            />
          ) : (
            <p className="empty-state">当前章节还没有生成场景。</p>
          )}
        </section>
      </div>
    </section>
  );
}

function SceneDetail({
  characterById,
  characters,
  lineEntries,
  lineIndex,
  location,
  onAddLine,
  onDeleteLine,
  onMarkLine,
  onMoveLine,
  onUpdateLine,
  readingSettings,
  scene,
}) {
  const [editingLineIndex, setEditingLineIndex] = useState(null);
  const [isAddingLine, setIsAddingLine] = useState(false);
  const [newLineType, setNewLineType] = useState("action");
  const charactersInScene = scene.characters.map((id) => characterById.get(id)).filter(Boolean);

  useEffect(() => {
    setEditingLineIndex(null);
    setIsAddingLine(false);
    setNewLineType("action");
  }, [scene.id]);

  function startAddingLine(type) {
    setNewLineType(type);
    setIsAddingLine(true);
  }

  return (
    <article className="scene-card scene-detail-card">
      <header className="scene-header scene-hero-header">
        <span className="scene-number">S{String(lineIndex).padStart(2, "0")}</span>
        <div className="scene-title-block">
          <p className="eyebrow">Current Scene</p>
          <h2>{scene.title}</h2>
          <p>{scene.summary}</p>
        </div>
      </header>

      <dl className="scene-meta">
        <div>
          <dt>地点</dt>
          <dd>{location?.name || scene.location_id}</dd>
        </div>
        <div>
          <dt>人物</dt>
          <dd>{charactersInScene.map((character) => character.name).join(" / ") || "待补充"}</dd>
        </div>
      </dl>

      <SourceRef scene={scene} />
      <BeatGrid beats={scene.beats} summary={scene.summary} />

      <div className="script-section-header">
        <div>
          <p className="eyebrow">Script Lines</p>
          <h3>{lineEntries.length} 行剧本正文</h3>
        </div>
        <div className="script-inline-toolbar" aria-label="添加剧本行">
          {[
            ["camera", Camera, "镜头"],
            ["action", PencilLine, "动作"],
            ["dialogue", MessageSquareText, "对白"],
            ["note", StickyNote, "备注"],
          ].map(([type, Icon, label]) => (
            <button key={type} type="button" onClick={() => startAddingLine(type)}>
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className={`script-lines ${readingClassName(readingSettings)}`}>
        {lineEntries.length ? (
          lineEntries.map((entry, position) => (
            <div className="script-line-wrap" key={entry.line.id}>
              <ScriptLine
                canMoveDown={position < lineEntries.length - 1}
                canMoveUp={position > 0}
                character={entry.line.character_id ? characterById.get(entry.line.character_id) : null}
                line={entry.line}
                onAddNote={() => setEditingLineIndex(entry.index)}
                onDelete={() => onDeleteLine(entry.index)}
                onEdit={() => setEditingLineIndex(entry.index)}
                onMark={() => onMarkLine(entry.index)}
                onMoveDown={() => onMoveLine(entry.index, 1)}
                onMoveUp={() => onMoveLine(entry.index, -1)}
              />
              {editingLineIndex === entry.index && (
                <LineEditorForm
                  characters={characters}
                  initialLine={entry.line}
                  onCancel={() => setEditingLineIndex(null)}
                  onSave={(line) => {
                    onUpdateLine(entry.index, line);
                    setEditingLineIndex(null);
                  }}
                  submitLabel="保存修改"
                />
              )}
            </div>
          ))
        ) : (
          <p className="empty-state compact">当前场景还没有生成剧本行。</p>
        )}
      </div>

      <div className="add-line-panel">
        {isAddingLine ? (
          <LineEditorForm
            characters={characters}
            initialLine={{ scene_id: scene.id, type: newLineType, content: "" }}
            onCancel={() => setIsAddingLine(false)}
            onSave={(line) => {
              onAddLine(line);
              setIsAddingLine(false);
            }}
            submitLabel="添加剧本行"
          />
        ) : (
          <button className="add-line-button" type="button" onClick={() => startAddingLine("action")}>
            <Plus size={16} />
            添加剧本行
          </button>
        )}
      </div>
    </article>
  );
}

function SourceRef({ scene }) {
  const source = scene.source_ref || {};
  const chapterIndex = source.chapter_index || source.chapterIndex;
  const chapterLabel = source.chapter_title || source.chapterTitle || (chapterIndex ? `第 ${chapterIndex} 章` : "未绑定章节");
  const excerpt = source.excerpt || source.evidence || source.text || scene.summary || "暂无原文依据。";
  return (
    <section className="source-ref">
      <h3>来源章节</h3>
      <p>
        <strong>{chapterLabel}</strong>
        <span>{excerpt}</span>
      </p>
    </section>
  );
}

function BeatGrid({ beats, summary }) {
  const beatData = buildBeats(beats, summary);
  return (
    <dl className="beat-grid">
      {beatData.map((beat) => (
        <div key={beat.label}>
          <dt>{beat.label}</dt>
          <dd>{beat.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ScriptLine({
  canMoveDown,
  canMoveUp,
  character,
  line,
  onAddNote,
  onDelete,
  onEdit,
  onMark,
  onMoveDown,
  onMoveUp,
}) {
  const meta = lineMeta[line.type] || lineMeta.action;
  const Icon = meta.icon;
  const speaker = line.speaker_name || character?.name || line.speaker_id || line.character_id;

  return (
    <div
      className={`script-line ${line.type} ${line.highlight_color ? "highlighted" : ""}`}
      style={line.highlight_color ? { "--line-highlight": line.highlight_color } : undefined}
    >
      <span className="line-type">
        <Icon size={15} />
        {meta.label}
      </span>
      <div className="line-body">
        {speaker && <strong className="speaker">{speaker}</strong>}
        {line.emotion && <span className="line-emotion">{line.emotion}</span>}
        <p>{lineText(line)}</p>
        {line.note && <p className="line-note">备注：{line.note}</p>}
      </div>
      <div className="line-actions">
        <button type="button" onClick={onEdit}>
          <Edit3 size={14} />
          编辑
        </button>
        <button type="button" onClick={onAddNote}>
          <StickyNote size={14} />
          添加备注
        </button>
        <button type="button" onClick={onMark}>
          <Highlighter size={14} />
          标记
        </button>
        <button type="button" onClick={onDelete}>
          <Trash2 size={14} />
          删除
        </button>
        <button disabled={!canMoveUp} type="button" onClick={onMoveUp}>
          <ArrowUp size={14} />
          上移
        </button>
        <button disabled={!canMoveDown} type="button" onClick={onMoveDown}>
          <ArrowDown size={14} />
          下移
        </button>
      </div>
    </div>
  );
}

function LineEditorForm({ characters, initialLine, onCancel, onSave, submitLabel }) {
  const [draft, setDraft] = useState(() => lineToDraft(initialLine));

  useEffect(() => {
    setDraft(lineToDraft(initialLine));
  }, [initialLine]);

  function updateDraft(key, value) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function submit(event) {
    event.preventDefault();
    const text = draft.text.trim();
    if (!text) {
      return;
    }
    onSave(draftToLine(draft, initialLine));
  }

  return (
    <form className="line-edit-form" onSubmit={submit}>
      <div className="line-edit-grid">
        <label>
          类型
          <select value={draft.type} onChange={(event) => updateDraft("type", event.target.value)}>
            {lineTypeOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {draft.type === "dialogue" && (
          <>
            <label>
              说话人 ID
              <select value={draft.speakerId} onChange={(event) => updateDraft("speakerId", event.target.value)}>
                <option value="">自定义说话人</option>
                {characters.map((character) => (
                  <option key={character.id} value={character.id}>
                    {character.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              说话人名称
              <input value={draft.speakerName} onChange={(event) => updateDraft("speakerName", event.target.value)} />
            </label>
            <label>
              情绪
              <input value={draft.emotion} onChange={(event) => updateDraft("emotion", event.target.value)} />
            </label>
          </>
        )}
      </div>
      <label>
        文本
        <textarea value={draft.text} rows={4} onChange={(event) => updateDraft("text", event.target.value)} />
      </label>
      <label>
        备注
        <textarea value={draft.note} rows={2} onChange={(event) => updateDraft("note", event.target.value)} />
      </label>
      <div className="line-edit-actions">
        <button type="submit">{submitLabel}</button>
        <button type="button" onClick={onCancel}>
          取消
        </button>
      </div>
    </form>
  );
}

function normalizeChapters(chapters) {
  return chapters.map((chapter, index) => {
    const id = chapter.chapter_id || chapter.chapterId || chapter.id || `chapter_${index + 1}`;
    const chapterIndex = chapter.chapter_index || chapter.chapterIndex || index + 1;
    return {
      ...chapter,
      id,
      chapterIndex,
      title: chapter.title || chapter.heading || `第 ${chapterIndex} 章`,
    };
  });
}

function groupScenesByChapter(scenes, chapters) {
  const groups = chapters.map((chapter) => ({ ...chapter, scenes: [] }));
  const groupById = new Map(groups.map((group) => [group.id, group]));

  for (const scene of scenes) {
    const chapterId = getSceneChapterId(scene) || groups[0]?.id || "chapter_1";
    let group = groupById.get(chapterId);
    if (!group) {
      const source = scene.source_ref || {};
      group = {
        id: chapterId,
        chapterIndex: source.chapter_index || groups.length + 1,
        title: source.chapter_title || `第 ${groups.length + 1} 章`,
        scenes: [],
      };
      groups.push(group);
      groupById.set(chapterId, group);
    }
    group.scenes.push(scene);
  }

  return groups;
}

function getSceneChapterId(scene) {
  return scene.source_ref?.chapter_id || scene.sourceRef?.chapterId || scene.source_ref?.chapterId || "";
}

function sceneNumber(scenes, scene) {
  return `S${scenes.findIndex((item) => item.id === scene.id) + 1}`;
}

function buildBeats(beats, summary) {
  const source = beats || {};
  return [
    ["目标", source.goal || "明确本场人物要达成的行动目标。"],
    ["冲突", source.conflict || "让人物目标受到阻碍，形成场面压力。"],
    ["转折", source.turn || source.twist || "安排信息变化或选择变化。"],
    ["结果", source.outcome || source.result || summary || "交代本场结束后的状态变化。"],
  ].map(([label, value]) => ({ label, value }));
}

function lineToDraft(line) {
  return {
    emotion: line.emotion || "",
    note: line.note || "",
    speakerId: line.speaker_id || line.character_id || "",
    speakerName: line.speaker_name || "",
    text: lineText(line),
    type: normalizeLineType(line.type),
  };
}

function draftToLine(draft, initialLine) {
  const text = draft.text.trim();
  const line = {
    ...initialLine,
    content: text,
    text,
    type: normalizeLineType(draft.type),
  };

  if (draft.note.trim()) {
    line.note = draft.note.trim();
  } else {
    delete line.note;
  }

  if (line.type === "dialogue") {
    const speakerId = draft.speakerId.trim();
    const speakerName = draft.speakerName.trim();
    if (speakerId) {
      line.character_id = speakerId;
      line.speaker_id = speakerId;
    } else {
      delete line.character_id;
      delete line.speaker_id;
    }
    if (speakerName) {
      line.speaker_name = speakerName;
    } else {
      delete line.speaker_name;
    }
    if (draft.emotion.trim()) {
      line.emotion = draft.emotion.trim();
    } else {
      delete line.emotion;
    }
    if (!line.character_id && !line.speaker_name) {
      line.speaker_name = "未指定";
    }
  } else {
    delete line.character_id;
    delete line.speaker_id;
    delete line.speaker_name;
    delete line.emotion;
  }

  return compactLine(line);
}

function normalizeLineForSave(line) {
  return draftToLine(lineToDraft(line), {
    ...line,
    id: line.id,
    scene_id: line.scene_id,
    highlight_color: line.highlight_color,
  });
}

function withLineDefaults(line, index) {
  return {
    ...line,
    id: ensureLineId(line, index),
    type: normalizeLineType(line.type),
  };
}

function lineText(line) {
  return String(line.text ?? line.content ?? "");
}

function normalizeLineType(type) {
  if (type === "shot") {
    return "camera";
  }
  if (type === "remark") {
    return "note";
  }
  return type || "action";
}

function ensureLineId(line, index) {
  return line.id || `${line.scene_id || "scene"}_line_${index + 1}`;
}

function nextLineId(script) {
  const existing = new Set(script.map((line, index) => ensureLineId(line, index)));
  let index = existing.size + 1;
  while (existing.has(`line_${index}`)) {
    index += 1;
  }
  return `line_${index}`;
}

function compactLine(line) {
  return Object.fromEntries(Object.entries(line).filter(([_key, value]) => value !== undefined && value !== ""));
}
