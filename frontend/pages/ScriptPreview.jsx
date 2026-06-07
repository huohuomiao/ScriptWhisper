import {
  ArrowDown,
  ArrowUp,
  Camera,
  Check,
  ChevronDown,
  Edit3,
  Highlighter,
  MessageSquareText,
  MoreHorizontal,
  MoveRight,
  PencilLine,
  Plus,
  ScrollText,
  StickyNote,
  Trash2,
} from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useState } from "react";

import EditableTitle from "../components/EditableTitle.jsx";
import ReadingToolbar from "../components/ReadingToolbar.jsx";
import SceneEditor from "../components/SceneEditor.jsx";
import { highlightColors, readingClassName, useReadingSettings } from "../src/readingSettings.js";

const lineMeta = {
  action: { labelKey: "preview.filter.action", icon: PencilLine },
  camera: { labelKey: "preview.filter.camera", icon: Camera },
  dialogue: { labelKey: "preview.filter.dialogue", icon: MessageSquareText },
  narration: { labelKey: "preview.filter.narration", icon: ScrollText },
  note: { labelKey: "preview.filter.note", icon: StickyNote },
  remark: { labelKey: "preview.filter.note", icon: StickyNote },
  transition: { labelKey: "preview.filter.transition", icon: MoveRight },
};

export default function ScriptPreview({
  chapters = [],
  currentProject = null,
  onRenameChapter,
  onRenameScene,
  onScriptYamlChange,
  scriptYaml = emptyScriptYaml(),
  t = (key) => key,
  updateCurrentProjectData,
}) {
  const [yamlData, setYamlData] = useState(normalizeYaml(scriptYaml));
  const { settings, setFontSize, setHighlightColor, setLineHeight } = useReadingSettings();
  const normalizedChapters = useMemo(() => normalizeChapters(chapters), [chapters]);
  const sceneGroups = useMemo(
    () => groupScenesByChapter(yamlData.scenes, normalizedChapters),
    [yamlData.scenes, normalizedChapters],
  );
  const firstChapterId = sceneGroups[0]?.id || "";
  const firstSceneId = sceneGroups.find((group) => group.scenes.length > 0)?.scenes[0]?.id || "";
  const initialUiState = currentProject?.uiState || {};
  const [selectedChapterId, setSelectedChapterId] = useState(initialUiState.selectedChapterId || firstChapterId);
  const [selectedSceneId, setSelectedSceneId] = useState(initialUiState.selectedSceneId || firstSceneId);
  const [selectedLineId, setSelectedLineId] = useState(initialUiState.selectedLineId || "");
  const [scriptLineFilter, setScriptLineFilter] = useState(initialUiState.scriptLineFilter || "all");
  const [status, setStatus] = useState("");

  useEffect(() => {
    setYamlData(normalizeYaml(scriptYaml));
  }, [scriptYaml]);

  useEffect(() => {
    const uiState = currentProject?.uiState || {};
    setSelectedChapterId(uiState.selectedChapterId || firstChapterId);
    setSelectedSceneId(uiState.selectedSceneId || firstSceneId);
    setSelectedLineId(uiState.selectedLineId || "");
    setScriptLineFilter(uiState.scriptLineFilter || "all");
  }, [currentProject?.id]);

  const saveUiState = useCallback(
    (updates) => {
      updateCurrentProjectData?.((project) => ({
        uiState: {
          ...(project.uiState || {}),
          ...updates,
        },
      }));
    },
    [updateCurrentProjectData],
  );

  useEffect(() => {
    if (!sceneGroups.some((group) => group.id === selectedChapterId)) {
      setSelectedChapterId(firstChapterId);
      saveUiState({ selectedChapterId: firstChapterId });
    }
  }, [firstChapterId, saveUiState, sceneGroups, selectedChapterId]);

  useEffect(() => {
    const selectedGroup = sceneGroups.find((group) => group.id === selectedChapterId);
    const sceneExists = selectedGroup?.scenes.some((scene) => scene.id === selectedSceneId);
    if (!sceneExists) {
      const fallbackSceneId = selectedGroup?.scenes[0]?.id || "";
      setSelectedSceneId(fallbackSceneId);
      setSelectedLineId("");
      saveUiState({ selectedSceneId: fallbackSceneId, selectedLineId: "" });
    }
  }, [saveUiState, sceneGroups, selectedChapterId, selectedSceneId]);

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
    const nextSceneId = group.scenes[0]?.id || "";
    setSelectedSceneId(nextSceneId);
    setSelectedLineId("");
    saveUiState({ selectedChapterId: group.id, selectedSceneId: nextSceneId, selectedLineId: "" });
  }

  function selectScene(scene) {
    const nextChapterId = getSceneChapterId(scene) || selectedChapterId;
    setSelectedChapterId(nextChapterId);
    setSelectedSceneId(scene.id);
    setSelectedLineId("");
    saveUiState({ selectedChapterId: nextChapterId, selectedSceneId: scene.id, selectedLineId: "" });
  }

  function selectLine(lineId) {
    setSelectedLineId(lineId);
    saveUiState({ selectedLineId: lineId });
  }

  function changeLineFilter(nextFilter) {
    setScriptLineFilter(nextFilter);
    saveUiState({ scriptLineFilter: nextFilter });
  }

  function addLine(line) {
    if (!selectedScene) {
      return "";
    }
    const script = [...(yamlData.script || [])];
    const sceneLineIndexes = script.map((item, index) => (item.scene_id === selectedScene.id ? index : -1)).filter((index) => index >= 0);
    const insertAt = sceneLineIndexes.length ? sceneLineIndexes[sceneLineIndexes.length - 1] + 1 : script.length;
    const id = nextLineId(script);
    script.splice(
      insertAt,
      0,
      normalizeLineForSave(
        {
          ...line,
          id,
          scene_id: selectedScene.id,
        },
        t,
      ),
    );
    applyScript(script, t("preview.status.lineAdded"));
    selectLine(id);
    return id;
  }

  function updateLine(lineIndex, updates) {
    const script = (yamlData.script || []).map((line, index) =>
      index === lineIndex
        ? normalizeLineForSave(
            {
              ...line,
              id: ensureLineId(line, index),
              ...updates,
            },
            t,
          )
        : line,
    );
    applyScript(script, t("preview.status.lineUpdated"));
  }

  function deleteLine(lineIndex) {
    const deletedLineId = ensureLineId((yamlData.script || [])[lineIndex] || {}, lineIndex);
    applyScript(
      (yamlData.script || []).filter((_line, index) => index !== lineIndex),
      t("preview.status.lineDeleted"),
    );
    if (selectedLineId === deletedLineId) {
      selectLine("");
    }
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
    applyScript(script, t("preview.status.lineMoved"));
  }

  function setLineHighlight(lineIndex, highlightColor) {
    updateLine(lineIndex, { highlight_color: highlightColor });
  }

  function renameScene(sceneId, nextTitle) {
    const title = nextTitle.trim() || t("preview.untitledScene");
    const nextYaml = {
      ...yamlData,
      scenes: yamlData.scenes.map((scene) => (scene.id === sceneId ? { ...scene, title } : scene)),
    };
    handleYamlChange(nextYaml, t("preview.status.sceneRenamed"));
    onRenameScene?.(sceneId, title);
  }

  function clearCurrentSceneHighlights() {
    if (!selectedScene) {
      return;
    }
    const script = (yamlData.script || []).map((line) => {
      if (line.scene_id !== selectedScene.id || !getLineHighlightColor(line)) {
        return line;
      }
      const nextLine = { ...line };
      delete nextLine.highlight_color;
      delete nextLine.highlightColor;
      return nextLine;
    });
    applyScript(script, t("preview.status.highlightsCleared"));
  }

  if (!currentProject || !yamlData.scenes.length) {
    return (
      <section className="workspace preview-workspace">
        <p className="empty-state">{t("preview.empty")}</p>
      </section>
    );
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
          t={t}
        />
      </section>
      {status && <p className="editor-status">{status}</p>}

      <div className="preview-layout">
        <aside className="scene-navigator panel" aria-label={t("preview.sceneMap")}>
          <div className="navigator-header">
            <div>
              <p className="eyebrow">{t("preview.sceneMap")}</p>
              <h2>{t("preview.chapterScene")}</h2>
            </div>
            <ScrollText size={18} />
          </div>
          <div className="chapter-scene-list">
            {sceneGroups.map((group) => (
              <div className="chapter-scene-group" key={group.id}>
                <article
                  className={`chapter-selector ${group.id === selectedChapterId ? "active" : ""}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => selectChapter(group)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      selectChapter(group);
                    }
                  }}
                >
                  <strong>
                    <EditableTitle
                      ariaLabel={t("analysis.renameChapter")}
                      fallback={t("analysis.chapterFallback", { index: group.chapterIndex || 1 })}
                      onSave={(nextTitle) => onRenameChapter?.(group.id, nextTitle)}
                      showEditButton={false}
                      value={group.title}
                    />
                  </strong>
                  <span>{t("analysis.sceneCount", { count: group.scenes.length })}</span>
                </article>
                <div className="scene-selector-list">
                  {group.scenes.length ? (
                    group.scenes.map((scene) => (
                      <article
                        className={`scene-selector ${scene.id === selectedSceneId ? "active" : ""}`}
                        key={scene.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => selectScene(scene)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            selectScene(scene);
                          }
                        }}
                      >
                        <span>{sceneNumber(yamlData.scenes, scene)}</span>
                        <strong>
                          <EditableTitle
                            ariaLabel={t("preview.renameScene")}
                            fallback={t("preview.untitledScene")}
                            onSave={(nextTitle) => renameScene(scene.id, nextTitle)}
                            showEditButton={false}
                            value={scene.title}
                          />
                        </strong>
                      </article>
                    ))
                  ) : group.id === selectedChapterId ? (
                    <p className="empty-state compact">{t("preview.noScenesForChapter")}</p>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </aside>

        <section className="scene-detail-panel">
          {selectedScene ? (
            <SceneDetailPanel
              characterById={characterById}
              characters={yamlData.characters}
              chapters={normalizedChapters}
              lineEntries={selectedLineEntries}
              lineIndex={yamlData.scenes.findIndex((scene) => scene.id === selectedScene.id) + 1}
              location={locationById.get(selectedScene.location_id)}
              onAddLine={addLine}
              onDeleteLine={deleteLine}
              onMoveLine={moveLine}
              onRenameScene={renameScene}
              onClearSceneHighlights={clearCurrentSceneHighlights}
              onFontSizeChange={setFontSize}
              onHighlightColorChange={setHighlightColor}
              onScriptLineFilterChange={changeLineFilter}
              onSelectLine={selectLine}
              onSetHighlight={setLineHighlight}
              onLineHeightChange={setLineHeight}
              onUpdateLine={updateLine}
              readingSettings={settings}
              scriptLineFilter={scriptLineFilter}
              scene={selectedScene}
              selectedLineId={selectedLineId}
              t={t}
            />
          ) : (
            <p className="empty-state">{t("preview.noScenesForChapter")}</p>
          )}
        </section>
      </div>
    </section>
  );
}

const SceneDetailPanel = memo(function SceneDetailPanel({
  characterById,
  characters,
  chapters,
  lineEntries,
  lineIndex,
  location,
  onAddLine,
  onClearSceneHighlights,
  onDeleteLine,
  onFontSizeChange,
  onHighlightColorChange,
  onMoveLine,
  onRenameScene,
  onLineHeightChange,
  onScriptLineFilterChange,
  onSelectLine,
  onSetHighlight,
  onUpdateLine,
  readingSettings,
  scriptLineFilter,
  scene,
  selectedLineId,
  t,
}) {
  const [editingLineIndex, setEditingLineIndex] = useState(null);
  const [isAddingLine, setIsAddingLine] = useState(false);
  const [newLineType, setNewLineType] = useState("action");
  const [isAddMenuOpen, setIsAddMenuOpen] = useState(false);
  const charactersInScene = (scene.characters || []).map((id) => characterById.get(id)).filter(Boolean);
  const filteredLineEntries = lineEntries.filter((entry) => {
    if (scriptLineFilter === "all") {
      return true;
    }
    return normalizeLineType(entry.line.type) === scriptLineFilter;
  });
  const sceneLinePosition = new Map(lineEntries.map((entry, index) => [entry.index, index]));
  const selectedLineEntry = lineEntries.find((entry) => entry.line.id === selectedLineId) || null;
  const selectedLinePosition = selectedLineEntry ? sceneLinePosition.get(selectedLineEntry.index) ?? 0 : -1;
  const sourceChapter = findChapterForScene(chapters, scene);

  useEffect(() => {
    setEditingLineIndex(null);
    setIsAddingLine(false);
    setNewLineType("action");
    setIsAddMenuOpen(false);
  }, [scene.id]);

  useEffect(() => {
    if (selectedLineId && !lineEntries.some((entry) => entry.line.id === selectedLineId)) {
      onSelectLine("");
    }
  }, [lineEntries, onSelectLine, selectedLineId]);

  function startAddingLine(type) {
    setNewLineType(type);
    setIsAddingLine(true);
    setIsAddMenuOpen(false);
  }

  function editSelectedLine() {
    if (selectedLineEntry) {
      setEditingLineIndex(selectedLineEntry.index);
    }
  }

  function deleteSelectedLine() {
    if (!selectedLineEntry) {
      return;
    }
    const fallbackLine = lineEntries[selectedLinePosition + 1] || lineEntries[selectedLinePosition - 1];
    onDeleteLine(selectedLineEntry.index);
    onSelectLine(fallbackLine?.line.id || "");
  }

  function moveSelectedLine(direction) {
    if (!selectedLineEntry) {
      return;
    }
    onMoveLine(selectedLineEntry.index, direction);
  }

  useEffect(() => {
    function handleKeyDown(event) {
      if (!selectedLineEntry || editingLineIndex !== null || event.repeat || isEditingTarget(event.target)) {
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      if (event.key === "e" || event.key === "E" || event.key === "n" || event.key === "N") {
        event.preventDefault();
        editSelectedLine();
        return;
      }
      if (event.key === "Delete") {
        event.preventDefault();
        deleteSelectedLine();
        return;
      }
      if (event.key === "ArrowUp" && selectedLinePosition > 0) {
        event.preventDefault();
        moveSelectedLine(-1);
        return;
      }
      if (event.key === "ArrowDown" && selectedLinePosition >= 0 && selectedLinePosition < lineEntries.length - 1) {
        event.preventDefault();
        moveSelectedLine(1);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [editingLineIndex, lineEntries.length, selectedLineEntry, selectedLinePosition]);

  return (
    <article className="scene-card scene-detail-card">
      <header className="scene-header scene-hero-header">
        <span className="scene-number">S{String(lineIndex).padStart(2, "0")}</span>
        <div className="scene-title-block">
          <p className="eyebrow">{t("preview.currentScene")}</p>
          <h2>
            <EditableTitle
              ariaLabel={t("preview.renameScene")}
              fallback={t("preview.untitledScene")}
              onSave={(nextTitle) => onRenameScene(scene.id, nextTitle)}
              value={scene.title}
            />
          </h2>
        </div>
      </header>

      <dl className="scene-meta compact-scene-meta">
        <div>
          <dt>{t("preview.location")}</dt>
          <dd>{location?.name || scene.location_id}</dd>
        </div>
        <div>
          <dt>{t("preview.characters")}</dt>
          <dd>{charactersInScene.map((character) => character.name).join(" / ") || t("preview.unassigned")}</dd>
        </div>
        <div>
          <dt>{t("preview.sourceChapter")}</dt>
          <dd>{sourceChapter?.title || sourceLabel(scene, t)}</dd>
        </div>
      </dl>

      <SourceEvidenceDrawer
        chapter={sourceChapter}
        readingSettings={readingSettings}
        scene={scene}
        t={t}
      />
      <details className="beat-details">
        <summary>{t("preview.beatDetails")}</summary>
        <BeatGrid beats={scene.beats} summary={scene.summary} t={t} />
      </details>

      <div className="script-section-header">
        <div>
          <p className="eyebrow">{t("preview.scriptLines")}</p>
          <h3>{t("preview.scriptLineCount", { count: lineEntries.length })}</h3>
          <div className="script-filter-chips" aria-label={t("preview.filterAria")}>
            {lineFilterOptions(t).map(([value, label]) => (
              <button
                className={scriptLineFilter === value ? "active" : ""}
                key={value}
                type="button"
                onClick={() => onScriptLineFilterChange(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="script-section-tools">
          <div className="script-reading-toolbar desktop-only">
            <ReadingToolbar
              compact
              settings={readingSettings}
              onClearHighlight={onClearSceneHighlights}
              onFontSizeChange={onFontSizeChange}
              onHighlightColorChange={onHighlightColorChange}
              onLineHeightChange={onLineHeightChange}
              t={t}
            />
          </div>
          <div className="script-reading-toolbar mobile-only">
            <ReadingToolbar
              dropdown
              settings={readingSettings}
              onClearHighlight={onClearSceneHighlights}
              onFontSizeChange={onFontSizeChange}
              onHighlightColorChange={onHighlightColorChange}
              onLineHeightChange={onLineHeightChange}
              t={t}
            />
          </div>
          <div className="script-add-menu-wrap">
            <button
              aria-expanded={isAddMenuOpen}
              className="add-line-menu-button"
              type="button"
              onClick={() => setIsAddMenuOpen((current) => !current)}
            >
              <Plus size={15} />
              {t("preview.addLine")}
              <ChevronDown size={14} />
            </button>
            {isAddMenuOpen && (
              <div className="line-menu add-line-menu" role="menu">
                {[
                  ["camera", Camera, t("preview.addCamera")],
                  ["action", PencilLine, t("preview.addAction")],
                  ["dialogue", MessageSquareText, t("preview.addDialogue")],
                  ["note", StickyNote, t("preview.addNote")],
                  ["transition", MoveRight, t("preview.addTransition")],
                ].map(([type, Icon, label]) => (
                  <button key={type} role="menuitem" type="button" onClick={() => startAddingLine(type)}>
                    <Icon size={14} />
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <ScriptContextToolbar
        canMoveDown={selectedLinePosition >= 0 && selectedLinePosition < lineEntries.length - 1}
        canMoveUp={selectedLinePosition > 0}
        line={selectedLineEntry?.line || null}
        onAddNote={editSelectedLine}
        onDelete={deleteSelectedLine}
        onEdit={editSelectedLine}
        onHighlight={(highlightColor) => selectedLineEntry && onSetHighlight(selectedLineEntry.index, highlightColor)}
        onMoveDown={() => moveSelectedLine(1)}
        onMoveUp={() => moveSelectedLine(-1)}
        t={t}
      />

      {scriptLineFilter !== "all" && (
        <p className="filter-result-note">
          {t("preview.filterResult", { type: lineFilterOptions(t).find(([value]) => value === scriptLineFilter)?.[1] })}
        </p>
      )}

      <ScriptLineList
        characterById={characterById}
        characters={characters}
        editingLineIndex={editingLineIndex}
        entries={filteredLineEntries}
        onCancelEdit={() => setEditingLineIndex(null)}
        onSaveLine={(lineIndex, line) => {
          onUpdateLine(lineIndex, line);
          setEditingLineIndex(null);
        }}
        onSelectLine={onSelectLine}
        readingSettings={readingSettings}
        selectedLineId={selectedLineId}
        t={t}
      />

      <div className="add-line-panel">
        {isAddingLine && (
          <LineEditorForm
            characters={characters}
            initialLine={{ scene_id: scene.id, type: newLineType, content: "" }}
            onCancel={() => setIsAddingLine(false)}
            onSave={(line) => {
              onAddLine(line);
              setIsAddingLine(false);
            }}
            submitLabel={t("preview.addLine")}
            t={t}
          />
        )}
      </div>
    </article>
  );
});

function SourceEvidenceDrawer({ chapter, readingSettings, scene, t }) {
  const [isOpen, setIsOpen] = useState(false);
  const source = scene.source_ref || {};
  const sourceExcerpt = source.excerpt || source.evidence || source.text || "";
  const summary = scene.summary || t("preview.adaptedFromChapter");
  const sourceText = chapter?.content || sourceExcerpt || summary || t("preview.noSourceEvidence");
  const paragraphs = splitParagraphs(sourceText);
  const highlightExcerpt = source.excerpt || sourceExcerpt;
  const hasExcerptMatch = Boolean(highlightExcerpt && sourceText.includes(highlightExcerpt));
  const sourceTitle = sourceLabel(scene, t);
  const sourceWords = countSourceWords(sourceText);

  return (
    <section className="source-evidence-drawer">
      <div className="source-evidence-summary">
        <div>
          <h3>{t("preview.sourceEvidence")}</h3>
          <p>
            <strong>{t("preview.sourceSummary")}</strong>
            <span>{summary}</span>
            {sourceExcerpt && (
              <small>
                {t("preview.keyExcerpt")}：{excerpt(sourceExcerpt, 88)}
              </small>
            )}
          </p>
        </div>
        <button aria-expanded={isOpen} type="button" onClick={() => setIsOpen((current) => !current)}>
          {isOpen ? t("preview.hideFullSource") : t("preview.viewFullSource")}
        </button>
      </div>
      {isOpen && (
        <div className="source-evidence-reader">
          <div className="evidence-reader-meta">
            <span>{sourceTitle}</span>
            <span>{t("analysis.wordCount", { count: sourceWords })}</span>
            {sourceExcerpt && <span>{t("preview.keyExcerpt")}</span>}
          </div>
          {!hasExcerptMatch && <p className="source-evidence-hint">{t("preview.adaptedFromChapter")}</p>}
          <div className={`chapter-source-text evidence-full-text ${readingClassName(readingSettings)}`}>
            {paragraphs.map((paragraph, index) => (
              <p key={`${scene.id}-source-${index}`}>{renderParagraphWithExcerpt(paragraph, highlightExcerpt)}</p>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function BeatGrid({ beats, summary, t }) {
  const beatData = buildBeats(beats, summary, t);
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

const ScriptLineList = memo(function ScriptLineList({
  characterById,
  characters,
  editingLineIndex,
  entries,
  onCancelEdit,
  onSaveLine,
  onSelectLine,
  readingSettings,
  selectedLineId,
  t,
}) {
  return (
    <div className={`script-lines ${readingClassName(readingSettings)}`}>
      {entries.length ? (
        entries.map((entry) => (
          <div className="script-line-wrap" key={entry.line.id}>
            <ScriptLine
              character={entry.line.character_id ? characterById.get(entry.line.character_id) : null}
              line={entry.line}
              onSelect={() => onSelectLine(entry.line.id)}
              selected={entry.line.id === selectedLineId}
              t={t}
            />
            {editingLineIndex === entry.index && (
              <LineEditorForm
                characters={characters}
                initialLine={entry.line}
                onCancel={onCancelEdit}
                onSave={(line) => onSaveLine(entry.index, line)}
                submitLabel={t("preview.saveChanges")}
                t={t}
              />
            )}
          </div>
        ))
      ) : (
        <p className="empty-state compact">{t("preview.noLinesForFilter")}</p>
      )}
    </div>
  );
});

function ScriptContextToolbar({
  canMoveDown,
  canMoveUp,
  line,
  onAddNote,
  onDelete,
  onEdit,
  onHighlight,
  onMoveDown,
  onMoveUp,
  t,
}) {
  if (!line) {
    return null;
  }

  const meta = lineMeta[line.type] || lineMeta.action;
  const selectedPreview = excerpt(lineText(line), 34);

  return (
    <div className="script-context-toolbar">
      <div className="context-selected-label">
        <span>{t("preview.contextSelected")}</span>
        <strong>{t(meta.labelKey)}</strong>
        {selectedPreview && <em title={lineText(line)}>{selectedPreview}</em>}
      </div>
      <div className="context-actions">
        <button title="E" type="button" onClick={onEdit}>
          <Edit3 size={14} />
          {t("preview.action.edit")}
        </button>
        <button title="N" type="button" onClick={onAddNote}>
          <StickyNote size={14} />
          {t("preview.action.addNote")}
        </button>
        <HighlightMenuButton currentHighlight={normalizeHighlight(getLineHighlightColor(line))} onHighlight={onHighlight} t={t} />
        <button disabled={!canMoveUp} title="↑" type="button" onClick={onMoveUp}>
          <ArrowUp size={14} />
          {t("preview.action.moveUp")}
        </button>
        <button disabled={!canMoveDown} title="↓" type="button" onClick={onMoveDown}>
          <ArrowDown size={14} />
          {t("preview.action.moveDown")}
        </button>
        <button className="danger-action" title="Delete" type="button" onClick={onDelete}>
          <Trash2 size={14} />
          {t("preview.action.delete")}
        </button>
      </div>
    </div>
  );
}

function HighlightMenuButton({ currentHighlight, onHighlight, t }) {
  const [isHighlightMenuOpen, setIsHighlightMenuOpen] = useState(false);

  function choose(highlightColor) {
    onHighlight(highlightColor);
    setIsHighlightMenuOpen(false);
  }

  return (
    <div className="highlight-menu-wrap">
      <button
        aria-expanded={isHighlightMenuOpen}
        type="button"
        onClick={() => setIsHighlightMenuOpen((current) => !current)}
      >
        <Highlighter size={14} />
        {t("preview.action.mark")}
        <ChevronDown size={13} />
      </button>
      {isHighlightMenuOpen && (
        <div className="line-menu highlight-menu" role="menu">
          <button role="menuitem" type="button" onClick={() => choose(null)}>
            <span className="color-dot empty" />
            {t("preview.color.none")}
            {!currentHighlight && <Check size={14} />}
          </button>
          {highlightColors.map((color) => (
            <button key={color.id} role="menuitem" type="button" onClick={() => choose(color.id)}>
              <span className={`color-dot ${color.id}`} />
              {t(`preview.color.${color.id}`)}
              {currentHighlight === color.id && <Check size={14} />}
            </button>
          ))}
          <button className="danger-menu-item" role="menuitem" type="button" onClick={() => choose(null)}>
            <span className="color-dot empty" />
            {t("preview.color.clear")}
          </button>
        </div>
      )}
    </div>
  );
}

function ScriptLine({ character, line, onSelect, selected, t }) {
  const meta = lineMeta[line.type] || lineMeta.action;
  const Icon = meta.icon;
  const speaker = line.speaker_name || character?.name || line.speaker_id || line.character_id;
  const currentHighlight = normalizeHighlight(getLineHighlightColor(line));
  const notePreview = excerpt(line.note, 14);

  return (
    <article
      className={`script-line ${line.type} ${selected ? "selected" : ""} ${currentHighlight ? "highlighted" : ""}`}
      data-highlight={currentHighlight}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
    >
      <span className="line-type">
        <Icon size={15} />
        {t(meta.labelKey)}
      </span>
      <div className="line-body">
        {speaker && <strong className="speaker">{speaker}</strong>}
        {line.emotion && <span className="line-emotion">{line.emotion}</span>}
        <p>{lineText(line)}</p>
        <div className="line-indicators">
          {line.note && (
            <span className="line-note-indicator" title={line.note}>
              <StickyNote size={13} />
              <span>{t("preview.editor.note")}：{notePreview}</span>
            </span>
          )}
          {currentHighlight && <span className="line-highlight-indicator">{t(`preview.color.${currentHighlight}`)}</span>}
        </div>
      </div>
      <span className="line-more-button" aria-hidden="true">
        <MoreHorizontal size={16} />
      </span>
    </article>
  );
}

function LineEditorForm({ characters, initialLine, onCancel, onSave, submitLabel, t }) {
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
    onSave(draftToLine(draft, initialLine, t));
  }

  return (
    <form className="line-edit-form" onSubmit={submit}>
      <div className="line-edit-grid">
        <label>
          {t("preview.editor.type")}
          <select value={draft.type} onChange={(event) => updateDraft("type", event.target.value)}>
            {lineTypeOptions(t).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {draft.type === "dialogue" && (
          <>
            <label>
              {t("preview.editor.speakerId")}
              <select value={draft.speakerId} onChange={(event) => updateDraft("speakerId", event.target.value)}>
                <option value="">{t("preview.editor.customSpeaker")}</option>
                {characters.map((character) => (
                  <option key={character.id} value={character.id}>
                    {character.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("preview.editor.speakerName")}
              <input value={draft.speakerName} onChange={(event) => updateDraft("speakerName", event.target.value)} />
            </label>
            <label>
              {t("preview.editor.emotion")}
              <input value={draft.emotion} onChange={(event) => updateDraft("emotion", event.target.value)} />
            </label>
          </>
        )}
      </div>
      <label>
        {t("preview.editor.text")}
        <textarea value={draft.text} rows={4} onChange={(event) => updateDraft("text", event.target.value)} />
      </label>
      <label>
        {t("preview.editor.note")}
        <textarea value={draft.note} rows={2} onChange={(event) => updateDraft("note", event.target.value)} />
      </label>
      <div className="line-edit-actions">
        <button type="submit">{submitLabel}</button>
        <button type="button" onClick={onCancel}>
          {t("common.cancel")}
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

function findChapterForScene(chapters, scene) {
  const source = scene.source_ref || {};
  const chapterId = getSceneChapterId(scene);
  const requestedIndex = Number(source.chapter_index || source.chapterIndex);
  return (
    chapters.find((chapter) => chapter.id === chapterId) ||
    chapters.find((chapter) => Number(chapter.chapterIndex || chapter.chapter_index) === requestedIndex) ||
    null
  );
}

function sourceLabel(scene, t) {
  const source = scene.source_ref || {};
  const chapterIndex = source.chapter_index || source.chapterIndex;
  return (
    source.chapter_title ||
    source.chapterTitle ||
    (chapterIndex ? t("analysis.chapterFallback", { index: chapterIndex }) : t("preview.unboundChapter"))
  );
}

function splitParagraphs(text) {
  return String(text || "")
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}

function countSourceWords(text) {
  return String(text || "").replace(/\s+/g, "").length;
}

function renderParagraphWithExcerpt(paragraph, excerpt) {
  if (!excerpt || !paragraph.includes(excerpt)) {
    return paragraph;
  }
  const start = paragraph.indexOf(excerpt);
  const before = paragraph.slice(0, start);
  const after = paragraph.slice(start + excerpt.length);
  return (
    <>
      {before}
      <mark className="evidence-highlight">{excerpt}</mark>
      {after}
    </>
  );
}

function sceneNumber(scenes, scene) {
  return `S${scenes.findIndex((item) => item.id === scene.id) + 1}`;
}

function buildBeats(beats, summary, t) {
  const source = beats || {};
  return [
    [t("preview.beat.goal"), source.goal || t("preview.beat.goalFallback")],
    [t("preview.beat.conflict"), source.conflict || t("preview.beat.conflictFallback")],
    [t("preview.beat.turn"), source.turn || source.twist || t("preview.beat.turnFallback")],
    [t("preview.beat.outcome"), source.outcome || source.result || summary || t("preview.beat.outcomeFallback")],
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

function draftToLine(draft, initialLine, t = (key) => key) {
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
      line.speaker_name = t("preview.unassigned");
    }
  } else {
    delete line.character_id;
    delete line.speaker_id;
    delete line.speaker_name;
    delete line.emotion;
  }

  return compactLine(line);
}

function normalizeLineForSave(line, t) {
  const { highlightColor: _highlightColor, ...restLine } = line;
  const nextHighlightColor = Object.prototype.hasOwnProperty.call(line, "highlight_color")
    ? line.highlight_color
    : line.highlightColor;
  return draftToLine(
    lineToDraft(line),
    {
      ...restLine,
      id: line.id,
      scene_id: line.scene_id,
      highlight_color: nextHighlightColor,
    },
    t,
  );
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

function excerpt(value, maxLength) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "";
  }
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}...`;
}

function isEditingTarget(target) {
  return Boolean(target?.closest?.("input, textarea, select, [contenteditable='true']"));
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

function getLineHighlightColor(line) {
  return Object.prototype.hasOwnProperty.call(line, "highlight_color") ? line.highlight_color : line.highlightColor;
}

function normalizeHighlight(value) {
  if (!value) {
    return "";
  }
  const normalized = String(value).trim().toLowerCase();
  const legacy = {
    "#fff3a3": "yellow",
    "#cfe8ff": "blue",
    "#d8f5d2": "green",
    "#ffd8d2": "red",
  };
  return legacy[normalized] || normalized;
}

function lineTypeOptions(t) {
  return [
    ["camera", t("preview.filter.camera")],
    ["action", t("preview.filter.action")],
    ["dialogue", t("preview.filter.dialogue")],
    ["narration", t("preview.filter.narration")],
    ["note", t("preview.filter.note")],
    ["transition", t("preview.filter.transition")],
  ];
}

function lineFilterOptions(t) {
  return [
    ["all", t("preview.filter.all")],
    ["camera", t("preview.filter.camera")],
    ["action", t("preview.filter.action")],
    ["dialogue", t("preview.filter.dialogue")],
    ["note", t("preview.filter.note")],
    ["transition", t("preview.filter.transition")],
  ];
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

function normalizeYaml(scriptYaml) {
  return {
    project: scriptYaml?.project || {},
    characters: Array.isArray(scriptYaml?.characters) ? scriptYaml.characters : [],
    locations: Array.isArray(scriptYaml?.locations) ? scriptYaml.locations : [],
    scenes: Array.isArray(scriptYaml?.scenes) ? scriptYaml.scenes : [],
    script: Array.isArray(scriptYaml?.script) ? scriptYaml.script : [],
  };
}
