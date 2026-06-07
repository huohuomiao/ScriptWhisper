import { BadgeCheck, BookMarked, Check, FileText, Highlighter, MapPin, ScrollText, StickyNote, UsersRound, X } from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

import EditableTitle from "../components/EditableTitle.jsx";
import ReadingToolbar from "../components/ReadingToolbar.jsx";
import { readingClassName, useReadingSettings } from "../src/readingSettings.js";

const insightTabs = [
  { id: "bible", labelKey: "analysis.storyBible", icon: BookMarked },
  { id: "characters", labelKey: "analysis.characters", icon: UsersRound },
  { id: "locations", labelKey: "analysis.locations", icon: MapPin },
  { id: "notes", labelKey: "analysis.notes", icon: StickyNote },
];

export default function Analysis({
  chapters = [],
  currentProject = null,
  issues = [],
  mockMode = true,
  onRenameChapter,
  repaired = false,
  scriptYaml = emptyScriptYaml(),
  t = (key) => key,
  updateCurrentProjectData,
}) {
  const yaml = useMemo(() => normalizeYaml(scriptYaml), [scriptYaml]);
  const normalizedChapters = useMemo(() => chapters.map(normalizeChapter), [chapters]);
  const totalWords = useMemo(
    () => normalizedChapters.reduce((sum, chapter) => sum + chapter.wordCount, 0),
    [normalizedChapters],
  );
  const bible = useMemo(() => buildStoryBible(yaml, t), [yaml, t]);
  const sceneCountByChapter = useMemo(() => countScenesByChapter(yaml.scenes), [yaml.scenes]);
  const sceneUsageIndex = useMemo(() => buildSceneUsageIndex(yaml.scenes), [yaml.scenes]);
  const { settings, setFontSize, setHighlightColor, setLineHeight } = useReadingSettings();
  const annotations = currentProject?.chapterAnnotations || [];
  const annotationsByKey = useMemo(() => annotationsToMap(annotations), [annotations]);
  const initialChapterId = currentProject?.uiState?.selectedChapterId || normalizedChapters[0]?.id || "";
  const [selectedChapterId, setSelectedChapterId] = useState(initialChapterId);
  const [activeInsightTab, setActiveInsightTab] = useState("bible");
  const [noteDialog, setNoteDialog] = useState(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [sourceActionStatus, setSourceActionStatus] = useState("");
  const noteTextareaRef = useRef(null);
  const sourceReaderRef = useRef(null);
  const selectedChapter = useMemo(
    () => normalizedChapters.find((chapter) => chapter.id === selectedChapterId) || normalizedChapters[0],
    [normalizedChapters, selectedChapterId],
  );
  const selectedSceneCount = selectedChapter ? sceneCountByChapter.get(selectedChapter.id) || 0 : 0;

  useEffect(() => {
    if (!normalizedChapters.some((chapter) => chapter.id === selectedChapterId)) {
      const fallbackChapterId = normalizedChapters[0]?.id || "";
      setSelectedChapterId(fallbackChapterId);
      updateCurrentProjectData?.((project) => ({
        uiState: {
          ...(project.uiState || {}),
          selectedChapterId: fallbackChapterId,
        },
      }));
    }
  }, [normalizedChapters, selectedChapterId, updateCurrentProjectData]);

  useEffect(() => {
    if (currentProject?.uiState?.selectedChapterId && currentProject.uiState.selectedChapterId !== selectedChapterId) {
      setSelectedChapterId(currentProject.uiState.selectedChapterId);
    }
  }, [currentProject?.id]);

  const selectChapter = useCallback(
    (chapterId) => {
      setSelectedChapterId(chapterId);
      updateCurrentProjectData?.((project) => ({
        uiState: {
          ...(project.uiState || {}),
          selectedChapterId: chapterId,
        },
      }));
    },
    [updateCurrentProjectData],
  );

  function updateSelectionAnnotation(selection, updates) {
    if (!selectedChapter?.id || !selection) {
      return;
    }
    updateCurrentProjectData?.((project) => {
      const annotations = project.chapterAnnotations || [];
      const nextAnnotations = upsertChapterAnnotation(annotations, {
        chapterId: selectedChapter.id,
        paragraphIndex: selection.paragraphIndex,
        selectedText: selection.text,
        selectionStart: selection.start,
        selectionEnd: selection.end,
        ...updates,
      });
      return { chapterAnnotations: nextAnnotations };
    });
  }

  function getCurrentSelection() {
    const selection = readSourceSelection(sourceReaderRef.current);
    if (selection.errorKey) {
      setSourceActionStatus(t(selection.errorKey));
      return null;
    }
    return selection;
  }

  function markSelectedText() {
    const selection = getCurrentSelection();
    if (!selection) {
      return;
    }
    updateSelectionAnnotation(selection, { highlightColor: settings.highlightColor });
    window.getSelection()?.removeAllRanges();
    setSourceActionStatus(t("analysis.selectionMarked"));
  }

  function noteSelectedText() {
    const selection = getCurrentSelection();
    if (!selection) {
      return;
    }
    setNoteDialog(selection);
    setNoteDraft("");
  }

  function closeNoteDialog() {
    setNoteDialog(null);
    setNoteDraft("");
  }

  function saveSelectionNote(event) {
    event.preventDefault();
    if (!noteDialog || !noteDraft.trim()) {
      return;
    }
    updateSelectionAnnotation(noteDialog, { highlightColor: settings.highlightColor, note: noteDraft.trim() });
    window.getSelection()?.removeAllRanges();
    closeNoteDialog();
    setSourceActionStatus(t("analysis.selectionNoted"));
  }

  function clearCurrentChapterHighlights() {
    if (!selectedChapter?.id) {
      return;
    }
    updateCurrentProjectData?.((project) => ({
      chapterAnnotations: (project.chapterAnnotations || [])
        .map((annotation) =>
          annotation.chapterId === selectedChapter.id ? { ...annotation, highlightColor: "" } : annotation,
        )
        .filter((annotation) => annotation.note || annotation.highlightColor),
    }));
  }

  const currentChapterNotes = useMemo(
    () =>
      annotations.filter(
        (annotation) => annotation.chapterId === selectedChapter?.id && (annotation.note || annotation.highlightColor),
      ),
    [annotations, selectedChapter?.id],
  );

  function scrollToParagraph(paragraphIndex) {
    const node = sourceReaderRef.current?.querySelector(`[data-paragraph-index="${paragraphIndex}"]`);
    node?.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  useEffect(() => {
    if (noteDialog) {
      window.setTimeout(() => noteTextareaRef.current?.focus(), 0);
    }
  }, [noteDialog]);

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape" && noteDialog) {
        closeNoteDialog();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [noteDialog]);

  if (!currentProject || (!normalizedChapters.length && !yaml.scenes.length)) {
    return (
      <section className="workspace analysis-workspace">
        <p className="empty-state">{t("analysis.empty")}</p>
      </section>
    );
  }

  return (
    <section className="workspace analysis-workspace">
      <section className="page-intro-panel">
        <div>
          <p className="eyebrow">{t("analysis.intro.overline")}</p>
          <h2>{t("analysis.intro.title")}</h2>
          <p>{t("analysis.intro.description")}</p>
        </div>
        <div className="intro-status-row" aria-label={t("analysis.statusAria")}>
          <span className="status-chip">
            <BadgeCheck size={14} />
            {mockMode ? t("app.mode.mock") : t("app.mode.api")}
          </span>
          {issues.length > 0 && <span className="status-chip warning">{t("analysis.fixes", { count: issues.length })}</span>}
        </div>
      </section>

      <div className="metric-grid metric-grid-five" aria-label={t("analysis.metricsAria")}>
        <Metric label={t("analysis.metric.chapters")} value={normalizedChapters.length} />
        <Metric label={t("analysis.metric.characters")} value={yaml.characters.length} />
        <Metric label={t("analysis.metric.locations")} value={yaml.locations.length} />
        <Metric label={t("analysis.metric.scenes")} value={yaml.scenes.length} />
        <Metric label={t("analysis.metric.words")} value={totalWords.toLocaleString("zh-CN")} />
      </div>

      <div className="analysis-grid refined-analysis-grid">
        <ChapterNavigator
          chapters={normalizedChapters}
          onRenameChapter={onRenameChapter}
          onSelectChapter={selectChapter}
          sceneCountByChapter={sceneCountByChapter}
          selectedChapterId={selectedChapter?.id || ""}
          t={t}
        />

        <section className="analysis-reader panel matched-height-panel" aria-label={t("analysis.sourceEvidence")}>
          <div className="reader-header">
            <div>
              <p className="eyebrow">{t("analysis.sourceEvidence")}</p>
              <h2>{selectedChapter?.title || t("analysis.noChapter")}</h2>
              <p>
                {t("analysis.readerMeta", {
                  scenes: selectedSceneCount,
                  words: selectedChapter?.wordCount.toLocaleString("zh-CN") || 0,
                })}
              </p>
            </div>
            <div className="reader-header-tools">
              <ReadingToolbar
                compact
                dropdown
                settings={settings}
                onClearHighlight={clearCurrentChapterHighlights}
                onFontSizeChange={setFontSize}
                onHighlightColorChange={setHighlightColor}
                onLineHeightChange={setLineHeight}
                t={t}
              />
              <FileText size={20} />
            </div>
          </div>
          <SourceSelectionToolbar
            highlightColor={settings.highlightColor}
            onMarkSelection={markSelectedText}
            onNoteSelection={noteSelectedText}
            status={sourceActionStatus}
            t={t}
          />
          <SourceReader
            annotations={annotationsByKey}
            chapter={selectedChapter}
            readingSettings={settings}
            readerRef={sourceReaderRef}
            sceneUsageIndex={sceneUsageIndex}
            t={t}
          />
        </section>

        <aside className="insight-panel panel matched-height-panel" aria-label={t("analysis.insightsAria")}>
          <div className="insight-tabs" role="tablist" aria-label={t("analysis.insightsAria")}>
            {insightTabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  className={activeInsightTab === tab.id ? "active" : ""}
                  key={tab.id}
                  role="tab"
                  type="button"
                  aria-selected={activeInsightTab === tab.id}
                  onClick={() => setActiveInsightTab(tab.id)}
                >
                  <Icon size={15} />
                  {t(tab.labelKey)}
                </button>
              );
            })}
          </div>
          <div className="insight-content">
            {activeInsightTab === "bible" && (
              <div className="bible-grid">
                <BibleItem label={t("analysis.bible.storyType")} value={bible.storyType} />
                <BibleItem label={t("analysis.bible.mainConflict")} value={bible.mainConflict} />
                <BibleItem label={t("analysis.bible.centralMystery")} value={bible.centralMystery} />
                <BibleItem label={t("analysis.bible.adaptationAdvice")} value={bible.adaptationAdvice} />
              </div>
            )}
            {activeInsightTab === "characters" && (
              <div className="entity-list">
                {yaml.characters.map((character, index) => (
                  <EntityCard
                    key={character.id || character.name}
                    badge={initialFor(character.name, index)}
                    title={character.name}
                    subtitle={character.role || t("analysis.characterFallback")}
                    meta={character.personality || inferCharacterTrait(character, index)}
                    detail={character.motivation || inferMotivation(character)}
                  />
                ))}
              </div>
            )}
            {activeInsightTab === "locations" && (
              <div className="entity-list">
                {yaml.locations.map((location, index) => (
                  <EntityCard
                    key={location.id || location.name}
                    badge={initialFor(location.name, index)}
                    title={location.name}
                    subtitle={location.atmosphere || inferLocationAtmosphere(location)}
                    meta={location.description || t("analysis.locationFallback")}
                    detail={location.plot_use || location.plotUse || inferLocationUse(location)}
                  />
                ))}
              </div>
            )}
            {activeInsightTab === "notes" && (
              <div className="notes-list">
                {currentChapterNotes.length ? (
                  currentChapterNotes.map((note) => (
                    <button
                      className="note-card note-card-button"
                      key={annotationIdentity(note)}
                      data-highlight={normalizeHighlight(note.highlightColor) || undefined}
                      type="button"
                      onClick={() => scrollToParagraph(note.paragraphIndex)}
                    >
                      <span>{t("analysis.paragraphIndex", { index: note.paragraphIndex })}</span>
                      <p>{note.note || t("analysis.noNote")}</p>
                      {note.selectedText && <small>{t("analysis.selectedText")}：{note.selectedText}</small>}
                    </button>
                  ))
                ) : (
                  <p className="empty-state compact">{t("analysis.noMarks")}</p>
                )}
              </div>
            )}
          </div>
        </aside>
      </div>
      {noteDialog && (
        <SelectionNoteDialog
          draft={noteDraft}
          selectedText={noteDialog.text}
          textareaRef={noteTextareaRef}
          onChange={setNoteDraft}
          onClose={closeNoteDialog}
          onSave={saveSelectionNote}
          t={t}
        />
      )}
    </section>
  );
}

const ChapterNavigator = memo(function ChapterNavigator({
  chapters,
  onRenameChapter,
  onSelectChapter,
  sceneCountByChapter,
  selectedChapterId,
  t,
}) {
  return (
    <aside className="analysis-sidebar panel" aria-label={t("analysis.chapterList")}>
      <SectionHeading icon={<ScrollText size={17} />} title={t("analysis.chapterList")} />
      <div className="chapter-list compact-list">
        {chapters.map((chapter, index) => {
          const chapterSceneCount = sceneCountByChapter.get(chapter.id) || 0;
          return (
            <article
              className={`chapter-row ${chapter.id === selectedChapterId ? "selected" : ""}`}
              key={chapter.id}
              role="button"
              tabIndex={0}
              onClick={() => onSelectChapter(chapter.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  onSelectChapter(chapter.id);
                }
              }}
            >
              <span className="row-index">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h2>
                  <EditableTitle
                    ariaLabel={t("analysis.renameChapter")}
                    fallback={t("analysis.chapterFallback", { index: chapter.chapterIndex || index + 1 })}
                    onSave={(nextTitle) => onRenameChapter?.(chapter.id, nextTitle)}
                    showEditButton={false}
                    value={chapter.title}
                  />
                </h2>
                <div className="row-meta">
                  <span>{t("analysis.wordCount", { count: chapter.wordCount.toLocaleString("zh-CN") })}</span>
                  <span>{t("analysis.sceneCount", { count: chapterSceneCount })}</span>
                  <span>{chapter.status}</span>
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </aside>
  );
});

function SourceSelectionToolbar({ highlightColor, onMarkSelection, onNoteSelection, status, t }) {
  return (
    <div className="source-selection-toolbar" data-highlight={normalizeHighlight(highlightColor)}>
      <div className="source-selection-title">
        <span className="selection-color-dot" aria-hidden="true" />
        <strong>{t("analysis.selectionActions")}</strong>
      </div>
      <div className="source-selection-actions">
        <button type="button" onClick={onMarkSelection}>
          <Highlighter size={14} />
          {t("analysis.markSelection")}
        </button>
        <button type="button" onClick={onNoteSelection}>
          <StickyNote size={14} />
          {t("analysis.noteSelection")}
        </button>
      </div>
      {status && <span className="source-action-status">{status}</span>}
    </div>
  );
}

function SelectionNoteDialog({ draft, onChange, onClose, onSave, selectedText, textareaRef, t }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="selection-note-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="selection-note-title"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={onSave}
      >
        <header>
          <div>
            <p className="eyebrow">{t("analysis.selectionActions")}</p>
            <h2 id="selection-note-title">{t("analysis.notePrompt")}</h2>
          </div>
          <button aria-label={t("common.cancel")} type="button" onClick={onClose}>
            <X size={16} />
          </button>
        </header>
        <blockquote>{selectedText}</blockquote>
        <label>
          <span>{t("preview.editor.note")}</span>
          <textarea
            ref={textareaRef}
            value={draft}
            rows={5}
            placeholder={t("analysis.notePlaceholder")}
            onChange={(event) => onChange(event.target.value)}
          />
        </label>
        <footer>
          <button type="button" onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button className="primary" disabled={!draft.trim()} type="submit">
            <Check size={15} />
            {t("analysis.saveNote")}
          </button>
        </footer>
      </form>
    </div>
  );
}

const SourceReader = memo(function SourceReader({ annotations, chapter, readerRef, readingSettings, sceneUsageIndex, t }) {
  const sourceText = chapter?.content || chapter?.summary || t("analysis.noSourceText");
  const paragraphs = useMemo(() => splitParagraphs(sourceText), [sourceText]);
  const paragraphSceneNumbers = useMemo(
    () => paragraphs.map((paragraph, index) => scenesUsedForParagraph(sceneUsageIndex, chapter?.id, paragraph, index + 1)),
    [chapter?.id, paragraphs, sceneUsageIndex],
  );

  return (
    <div className={`chapter-source-text annotated-source ${readingClassName(readingSettings)}`} ref={readerRef}>
      {paragraphs.map((paragraph, index) => {
        const paragraphNumber = index + 1;
        const key = `${chapter?.id || "chapter"}:${paragraphNumber}`;
        const annotationGroup = annotations[key] || {};
        const annotation = annotationGroup.paragraph || {};
        const selections = annotationGroup.selections || [];
        const usedScenes = paragraphSceneNumbers[index] || [];
        return (
          <article
            className={`source-paragraph ${annotation.highlightColor ? "marked" : ""}`}
            data-highlight={normalizeHighlight(annotation.highlightColor)}
            data-paragraph-index={paragraphNumber}
            key={key}
          >
            <div className="source-paragraph-body">
              <p className="source-paragraph-text">{renderParagraphWithSelectionMarks(paragraph, selections, t)}</p>
              <div className="source-paragraph-tags">
                {usedScenes.map((sceneNumber) => (
                  <span key={sceneNumber}>{t("analysis.usedInScene", { scene: sceneNumber })}</span>
                ))}
                {(annotation.note || selections.some((selection) => selection.note)) && <span>{t("analysis.noted")}</span>}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
});

function annotationsToMap(annotations) {
  return (annotations || []).reduce((result, annotation) => {
    const key = `${annotation.chapterId}:${annotation.paragraphIndex}`;
    const group = result[key] || { paragraph: {}, selections: [] };
    if (hasSelectionRange(annotation)) {
      group.selections.push(annotation);
    } else {
      group.paragraph = annotation;
    }
    result[key] = group;
    return result;
  }, {});
}

function upsertChapterAnnotation(annotations, nextAnnotation) {
  const hasSelection = hasSelectionRange(nextAnnotation);
  const normalized = {
    chapterId: nextAnnotation.chapterId,
    paragraphIndex: nextAnnotation.paragraphIndex,
    ...(hasSelection
      ? {
          selectedText: String(nextAnnotation.selectedText || ""),
          selectionEnd: Number(nextAnnotation.selectionEnd),
          selectionStart: Number(nextAnnotation.selectionStart),
        }
      : {}),
    ...(Object.prototype.hasOwnProperty.call(nextAnnotation, "highlightColor")
      ? { highlightColor: nextAnnotation.highlightColor || "" }
      : {}),
    ...(Object.prototype.hasOwnProperty.call(nextAnnotation, "note") ? { note: nextAnnotation.note || "" } : {}),
  };
  const nextAnnotations = [];
  let didUpdate = false;
  const targetIdentity = annotationIdentity(normalized);

  for (const annotation of annotations || []) {
    if (annotationIdentity(annotation) === targetIdentity) {
      didUpdate = true;
      const merged = {
        ...annotation,
        ...Object.fromEntries(Object.entries(normalized).filter(([_key, value]) => value !== undefined)),
      };
      if (merged.note || merged.highlightColor) {
        nextAnnotations.push(merged);
      }
      continue;
    }
    nextAnnotations.push(annotation);
  }

  if (!didUpdate && (normalized.note || normalized.highlightColor)) {
    nextAnnotations.push({
      ...normalized,
      highlightColor: normalized.highlightColor || "",
      note: normalized.note || "",
    });
  }

  return nextAnnotations;
}

function annotationIdentity(annotation) {
  const chapterId = annotation.chapterId || annotation.chapter_id || "";
  const paragraphIndex = Number(annotation.paragraphIndex ?? annotation.paragraph_index);
  if (hasSelectionRange(annotation)) {
    return `${chapterId}:${paragraphIndex}:${Number(annotation.selectionStart)}:${Number(annotation.selectionEnd)}`;
  }
  return `${chapterId}:${paragraphIndex}:paragraph`;
}

function hasSelectionRange(annotation) {
  return Number.isFinite(Number(annotation.selectionStart)) && Number.isFinite(Number(annotation.selectionEnd));
}

function normalizeChapter(chapter, index) {
  const fallbackId = `chapter_${index + 1}`;
  return {
    ...chapter,
    id: chapter.chapter_id || chapter.chapterId || chapter.id || fallbackId,
    content: chapter.content || "",
    summary: chapter.summary || "",
    title: chapter.title || chapter.heading || `章节 ${index + 1}`,
    wordCount: chapter.wordCount ?? chapter.word_count ?? (chapter.content || "").length,
    status: chapter.status || "已分析",
  };
}

function getSceneChapterId(scene) {
  return scene.source_ref?.chapter_id || scene.sourceRef?.chapterId || scene.source_ref?.chapterId || "";
}

function countScenesByChapter(scenes) {
  const counts = new Map();
  for (const scene of scenes || []) {
    const chapterId = getSceneChapterId(scene);
    if (chapterId) {
      counts.set(chapterId, (counts.get(chapterId) || 0) + 1);
    }
  }
  return counts;
}

function buildSceneUsageIndex(scenes) {
  const byParagraph = new Map();
  const excerptCandidatesByChapter = new Map();

  (scenes || []).forEach((scene, index) => {
    const source = scene.source_ref || scene.sourceRef || {};
    const chapterId = getSceneChapterId(scene);
    if (!chapterId) {
      return;
    }

    const sceneNumber = index + 1;
    const paragraphRange = source.paragraph_range || source.paragraphRange;
    if (Array.isArray(paragraphRange) && paragraphRange.length === 2) {
      const start = Math.floor(Number(paragraphRange[0]));
      const end = Math.floor(Number(paragraphRange[1]));
      if (Number.isFinite(start) && Number.isFinite(end)) {
        const first = Math.max(1, Math.min(start, end));
        const last = Math.max(start, end);
        for (let paragraphNumber = first; paragraphNumber <= last; paragraphNumber += 1) {
          pushUniqueScene(byParagraph, `${chapterId}:${paragraphNumber}`, sceneNumber);
        }
      }
    }

    const excerpt = String(source.excerpt || "").trim();
    if (excerpt) {
      const candidates = excerptCandidatesByChapter.get(chapterId) || [];
      candidates.push({ probe: excerpt.slice(0, 24), sceneNumber });
      excerptCandidatesByChapter.set(chapterId, candidates);
    }
  });

  return { byParagraph, excerptCandidatesByChapter };
}

function scenesUsedForParagraph(sceneUsageIndex, chapterId, paragraph, paragraphNumber) {
  if (!sceneUsageIndex || !chapterId) {
    return [];
  }

  const usedScenes = [...(sceneUsageIndex.byParagraph.get(`${chapterId}:${paragraphNumber}`) || [])];
  const candidates = sceneUsageIndex.excerptCandidatesByChapter.get(chapterId) || [];
  for (const candidate of candidates) {
    if (candidate.probe && paragraph.includes(candidate.probe) && !usedScenes.includes(candidate.sceneNumber)) {
      usedScenes.push(candidate.sceneNumber);
    }
  }
  return usedScenes;
}

function pushUniqueScene(map, key, sceneNumber) {
  const scenes = map.get(key) || [];
  if (!scenes.includes(sceneNumber)) {
    scenes.push(sceneNumber);
  }
  map.set(key, scenes);
}

function splitParagraphs(text) {
  return String(text)
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function readSourceSelection(readerNode) {
  const selection = window.getSelection?.();
  if (!selection || selection.rangeCount === 0 || !readerNode) {
    return { errorKey: "analysis.selectionRequired" };
  }
  const selectedText = selection.toString();
  if (!selectedText.trim()) {
    return { errorKey: "analysis.selectionRequired" };
  }

  const range = selection.getRangeAt(0);
  if (!readerNode.contains(range.commonAncestorContainer)) {
    return { errorKey: "analysis.selectionRequired" };
  }

  const startParagraph = closestSourceParagraph(range.startContainer);
  const endParagraph = closestSourceParagraph(range.endContainer);
  if (!startParagraph || !endParagraph || startParagraph !== endParagraph) {
    return { errorKey: "analysis.selectionSameParagraph" };
  }

  const textNode = startParagraph.querySelector(".source-paragraph-text");
  if (!textNode) {
    return { errorKey: "analysis.selectionRequired" };
  }

  const startRange = document.createRange();
  startRange.selectNodeContents(textNode);
  startRange.setEnd(range.startContainer, range.startOffset);
  const start = startRange.toString().length;
  startRange.detach?.();
  const end = start + selectedText.length;
  const paragraphIndex = Number(startParagraph.dataset.paragraphIndex);

  if (!Number.isFinite(paragraphIndex) || end <= start) {
    return { errorKey: "analysis.selectionRequired" };
  }

  return {
    end,
    paragraphIndex,
    start,
    text: selectedText,
  };
}

function closestSourceParagraph(node) {
  const element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
  return element?.closest?.(".source-paragraph");
}

function renderParagraphWithSelectionMarks(paragraph, selections, t) {
  const ranges = (selections || [])
    .map((selection) => ({
      ...selection,
      selectionEnd: Number(selection.selectionEnd),
      selectionStart: Number(selection.selectionStart),
    }))
    .filter(
      (selection) =>
        Number.isFinite(selection.selectionStart) &&
        Number.isFinite(selection.selectionEnd) &&
        selection.selectionStart >= 0 &&
        selection.selectionEnd > selection.selectionStart &&
        selection.selectionStart < paragraph.length,
    )
    .sort((a, b) => a.selectionStart - b.selectionStart || a.selectionEnd - b.selectionEnd);

  if (!ranges.length) {
    return paragraph;
  }

  const parts = [];
  let cursor = 0;
  ranges.forEach((selection, index) => {
    const start = Math.max(cursor, selection.selectionStart);
    const end = Math.min(paragraph.length, selection.selectionEnd);
    if (end <= start) {
      return;
    }
    if (start > cursor) {
      parts.push(paragraph.slice(cursor, start));
    }
    const text = paragraph.slice(start, end);
    parts.push(
      <mark
        className="source-selection-mark"
        data-highlight={normalizeHighlight(selection.highlightColor)}
        key={`${start}-${end}-${index}`}
        title={selection.note || `${t("analysis.selectedText")}：${text}`}
      >
        {text}
      </mark>,
    );
    cursor = end;
  });

  if (cursor < paragraph.length) {
    parts.push(paragraph.slice(cursor));
  }

  return parts;
}

function buildStoryBible(scriptYaml, t) {
  const project = scriptYaml.project || {};
  const bible = project.bible || {};
  const firstScene = scriptYaml.scenes[0];
  const sceneTitles = scriptYaml.scenes.map((scene) => scene.title).join("、");

  return {
    storyType: bible.story_type || bible.storyType || project.genre || t("analysis.bible.pendingType"),
    mainConflict:
      bible.main_conflict ||
      bible.mainConflict ||
      project.logline ||
      t("analysis.bible.defaultConflict", { title: project.title || t("analysis.bible.story") }),
    centralMystery:
      bible.central_mystery ||
      bible.centralMystery ||
      (firstScene ? t("analysis.bible.defaultMystery", { title: firstScene.title }) : t("analysis.bible.pendingMystery")),
    adaptationAdvice:
      bible.adaptation_advice ||
      bible.adaptationAdvice ||
      t("analysis.bible.defaultAdvice", { scenes: sceneTitles || t("analysis.bible.keyScenes") }),
  };
}

function inferCharacterTrait(character, index) {
  if (character.description?.includes("等待") || character.description?.includes("推动")) {
    return "坚定、主动、压迫感强";
  }
  if (character.description?.includes("回避") || character.description?.includes("旧信")) {
    return "克制、敏感、带有逃避倾向";
  }
  return index === 0 ? "核心人物，情绪线明确" : "关系人物，功能待细化";
}

function inferMotivation(character) {
  if (character.description?.includes("回避")) {
    return "确认过去事件的真相，同时避免再次受伤";
  }
  if (character.description?.includes("推动")) {
    return "迫使对方面对答案，推动剧情进入真相";
  }
  return "围绕主线冲突完成角色目标";
}

function inferLocationAtmosphere(location) {
  const text = `${location.name || ""}${location.description || ""}`;
  if (text.includes("影院") || text.includes("放映")) {
    return "怀旧、封闭、带悬疑压迫";
  }
  if (text.includes("雨") || text.includes("街")) {
    return "潮湿、冷光、情绪低压";
  }
  return "氛围待细化";
}

function inferLocationUse(location) {
  const text = `${location.name || ""}${location.description || ""}`;
  if (text.includes("门口")) {
    return "人物重逢和线索触发点";
  }
  if (text.includes("放映")) {
    return "记忆显影和真相推进点";
  }
  return "承载场景行动和人物关系变化";
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

function BibleItem({ label, value }) {
  return (
    <article className="bible-item">
      <span>{label}</span>
      <p>{value}</p>
    </article>
  );
}

function EntityCard({ badge, detail, meta, subtitle, title }) {
  return (
    <article className="entity-card">
      <span className="entity-badge">{badge}</span>
      <div>
        <div className="entity-card-header">
          <h3>{title}</h3>
          <span>{subtitle}</span>
        </div>
        <p>{meta}</p>
        <small>{detail}</small>
      </div>
    </article>
  );
}

function initialFor(value, index) {
  return String(value || index + 1).trim().slice(0, 1).toUpperCase();
}

function SectionHeading({ icon, title }) {
  return (
    <div className="section-heading">
      <span className="heading-icon">{icon}</span>
      <h2>{title}</h2>
    </div>
  );
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
