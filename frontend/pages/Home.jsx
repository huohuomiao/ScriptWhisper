import {
  ArrowRight,
  BadgeCheck,
  BookOpenCheck,
  Boxes,
  Clapperboard,
  Download,
  FileText,
  GitMerge,
  LoaderCircle,
  Play,
  Plus,
  Replace,
  Trash2,
  UploadCloud,
  WandSparkles,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";

import LanguageSelect from "../components/LanguageSelect.jsx";
import { convertNovel } from "../src/api.js";
import { projectDisplayTitle } from "../src/projectStore.jsx";

const progressKeys = [
  "pipeline.step.chapter",
  "pipeline.step.entity",
  "pipeline.step.scene",
  "pipeline.step.script",
  "pipeline.step.schema",
];

const defaultDraft = {
  title: "",
  mode: "mock",
  targetLanguage: "zh",
  manualInput: "",
  manualChapterIndex: 1,
  manualChapterTitle: "",
  chapterFiles: [],
};

export default function Home({
  createProject,
  currentProject,
  hasGeneratedContent = false,
  languageOptions,
  onNavigate = () => {},
  onAnalysisComplete,
  renameProject,
  t,
  updateCurrentProjectData,
}) {
  const [draft, setDraft] = useState(defaultDraft);
  const [status, setStatus] = useState("");
  const [statusType, setStatusType] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [progressIndex, setProgressIndex] = useState(-1);
  const [duplicateResolution, setDuplicateResolution] = useState("merge");
  const workbenchRef = useRef(null);
  const data = currentProject || draft;
  const fileRows = useMemo(() => (data.chapterFiles || []).filter((file) => file.sourceType !== "manual"), [data.chapterFiles]);
  const analysisRows = useMemo(() => buildAnalysisRows(data, fileRows, t), [data, fileRows, t]);
  const duplicateGroups = useMemo(() => duplicateGroupsFromRows(analysisRows), [analysisRows]);
  const resolvedAnalysisRows = useMemo(
    () => resolveDuplicateRows(analysisRows, duplicateResolution),
    [analysisRows, duplicateResolution],
  );
  const validation = useMemo(() => validateRows(resolvedAnalysisRows, t), [resolvedAnalysisRows, t]);
  const mode = data.mode || "mock";
  const targetLanguage = data.scriptYaml?.project?.target_language || data.targetLanguage || "zh";
  const titleValue = data.title || "";
  const canSubmit = !isBusy && resolvedAnalysisRows.length > 0 && validation.ok;
  const hasProject = Boolean(currentProject);
  const sceneCount = currentProject?.scriptYaml?.scenes?.length || 0;
  const scriptLineCount = currentProject?.scriptYaml?.script?.length || 0;
  const chapterCount = currentProject?.chapters?.length || resolvedAnalysisRows.length || 0;
  const canExport = hasGeneratedContent && sceneCount > 0 && scriptLineCount > 0;
  const hasProjectProgress = chapterCount > 0 || sceneCount > 0 || scriptLineCount > 0;

  function updateData(updates) {
    if (currentProject) {
      updateCurrentProjectData(updates);
      return;
    }
    setDraft((current) => ({ ...current, ...updates }));
  }

  function updateTitle(nextTitle) {
    if (currentProject) {
      renameProject(currentProject.id, nextTitle);
      return;
    }
    updateData({ title: nextTitle });
  }

  function updateTargetLanguage(nextLanguage) {
    if (currentProject) {
      updateCurrentProjectData((project) => ({
        scriptYaml: {
          ...project.scriptYaml,
          project: {
            ...(project.scriptYaml?.project || {}),
            target_language: nextLanguage,
          },
        },
      }));
      return;
    }
    updateData({ targetLanguage: nextLanguage });
  }

  function updateFileRows(nextRows) {
    updateData({ chapterFiles: nextRows });
  }

  async function handleFilesSelected(event) {
    const selectedFiles = Array.from(event.target.files || []).filter((file) => file.type === "text/plain" || file.name.endsWith(".txt"));
    event.target.value = "";
    if (!selectedFiles.length) {
      return;
    }

    const nextRows = [...fileRows];
    for (const file of selectedFiles) {
      const content = await file.text();
      const chapterIndex = nextChapterIndex(nextRows);
      nextRows.push({
        id: `file_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
        fileName: file.name,
        chapterIndex,
        chapterTitle: titleFromFilename(file.name, chapterIndex, t),
        content,
        sourceType: "file",
        wordCount: countWords(content),
      });
    }
    updateFileRows(nextRows);
  }

  async function handleAnalyze(event) {
    event.preventDefault();
    const latestRows = buildAnalysisRows(data, fileRows, t);
    const resolvedRows = resolveDuplicateRows(latestRows, duplicateResolution);
    const latestValidation = validateRows(resolvedRows, t);
    if (!latestValidation.ok) {
      setStatus(latestValidation.messages[0]);
      setStatusType("error");
      return;
    }

    const title = normalizedProjectTitle(titleValue, t);
    const project = ensureProject(title);
    const sortedRows = [...resolvedRows].sort((a, b) => Number(a.chapterIndex) - Number(b.chapterIndex));
    const sourceText = sortedRows.map(formatChapterForSource).join("\n\n");
    const source = sortedRows.map((row) => row.fileName).join(", ");

    setIsBusy(true);
    setStatus(t("home.generating"));
    setStatusType("");
    setProgressIndex(0);

    try {
      setStatus(mode === "mock" ? t("home.status.mock") : t("home.status.api"));
      const result = await convertNovel({
        mock: mode === "mock",
        source,
        targetLanguage,
        text: sourceText,
        title,
        onProgress: (event) => {
          setProgressIndex(progressIndexFromEvent(event));
          const nextStatus = progressStatusFromEvent(event, t);
          if (nextStatus) {
            setStatus(nextStatus);
          }
        },
      });
      setProgressIndex(progressKeys.length - 1);
      onAnalysisComplete(result, {
        chapterFiles: sortedRows,
        manualChapterIndex: Number(data.manualChapterIndex) || 1,
        manualChapterTitle: data.manualChapterTitle || "",
        manualInput: data.manualInput || "",
        mode,
        projectId: project.id,
        source,
        targetLanguage,
        title,
      });
      setStatus(result.mock_mode ? t("home.status.mockDone") : t("home.status.apiDone"));
      setStatusType("success");
    } catch (error) {
      setStatus(error.message);
      setStatusType("error");
    } finally {
      setIsBusy(false);
    }
  }

  function ensureProject(title) {
    if (currentProject) {
      if (!currentProject.title?.trim()) {
        renameProject(currentProject.id, title);
      }
      return currentProject;
    }
    return createProject({
      ...draft,
      fallbackTitle: t("app.project.untitled"),
      mode,
      title,
    });
  }

  function focusWorkbench() {
    workbenchRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
    window.setTimeout(() => {
      workbenchRef.current?.querySelector("textarea, input")?.focus();
    }, 260);
  }

  return (
    <section className={`workspace home-workspace ${hasProject ? "project-home" : ""}`}>
      {hasProject ? (
        <ContinueWorkPanel
          canExport={canExport}
          chapterCount={chapterCount}
          currentProject={currentProject}
          hasProgress={hasProjectProgress}
          onFocusInput={focusWorkbench}
          onNavigate={onNavigate}
          sceneCount={sceneCount}
          scriptLineCount={scriptLineCount}
          t={t}
        />
      ) : (
        <section className="home-hero">
          <div className="hero-copy">
            <p className="eyebrow">{t("home.hero.overline")}</p>
            <h2>{t("home.hero.title")}</h2>
            <p>{t("home.hero.description")}</p>
            <div className="hero-metrics" aria-label={t("home.hero.metricsAria")}>
              <span>{t("home.hero.metric.sceneFirst")}</span>
              <span>{t("home.hero.metric.yaml")}</span>
              <span>{t("home.hero.metric.aiAssist")}</span>
            </div>
          </div>
          <HeroWorkflowPanel t={t} />
        </section>
      )}

      <div className={`home-action-grid ${hasProject ? "project-action-grid" : ""}`}>
        <form className="workbench-card primary-workbench" ref={workbenchRef} onSubmit={handleAnalyze} aria-busy={isBusy}>
          <div className="workbench-header">
            <div>
              <p className="eyebrow">{t("home.create.overline")}</p>
              <h2>{t("home.create.title")}</h2>
              <p>{t("home.create.description")}</p>
            </div>
            <div className="mode-switch" aria-label={t("home.mode.aria")}>
              <button className={mode === "api" ? "active" : ""} type="button" onClick={() => updateData({ mode: "api", mockMode: false })}>
                <WandSparkles size={17} />
                AI API
              </button>
              <button className={mode === "mock" ? "active" : ""} type="button" onClick={() => updateData({ mode: "mock", mockMode: true })}>
                <BadgeCheck size={17} />
                Mock
              </button>
            </div>
          </div>

          <section className="input-panel" aria-label={t("home.input.aria")}>
            <div className="field-row field-row-compact">
              <label className="field-group">
                <span>{t("home.field.title")}</span>
                <input value={titleValue} placeholder={t("app.project.untitled")} onChange={(event) => updateTitle(event.target.value)} />
              </label>
              <div className="field-group">
                <span>{t("home.field.outputLanguage")}</span>
                <LanguageSelect
                  label={t("home.field.outputLanguage")}
                  onChange={updateTargetLanguage}
                  options={languageOptions}
                  value={targetLanguage}
                />
              </div>
            </div>

            <section className="file-manager" aria-label={t("home.field.file")}>
              <div className="file-manager-header">
                <div>
                  <span>{t("home.field.file")}</span>
                  <small>{t("home.files.helper")}</small>
                </div>
                <label className="file-picker-button">
                  <input accept=".txt,text/plain" multiple type="file" onChange={handleFilesSelected} />
                  <Plus size={15} />
                  {t("home.chooseFile")}
                </label>
              </div>
              <div className="file-row-list">
                {fileRows.length ? (
                  fileRows.map((row) => (
                    <FileRow
                      key={row.id}
                      onChange={(updates) =>
                        updateFileRows(fileRows.map((file) => (file.id === row.id ? { ...file, ...updates } : file)))
                      }
                      onRemove={() => updateFileRows(fileRows.filter((file) => file.id !== row.id))}
                      row={row}
                      t={t}
                    />
                  ))
                ) : (
                  <p className="empty-state compact">{t("home.files.empty")}</p>
                )}
              </div>
            </section>

            <label className="field-group">
              <span>{t("home.field.text")}</span>
              <textarea
                value={data.manualInput || ""}
                placeholder={t("home.text.placeholder")}
                rows={9}
                onChange={(event) => updateData({ manualInput: event.target.value })}
              />
            </label>
            <div className="manual-chapter-grid">
              <label className="field-group">
                <span>{t("home.files.chapterIndex")}</span>
                <input
                  min="1"
                  type="number"
                  value={data.manualChapterIndex || 1}
                  onChange={(event) => updateData({ manualChapterIndex: Number(event.target.value) || 1 })}
                />
              </label>
              <label className="field-group">
                <span>{t("home.files.chapterTitle")}</span>
                <input
                  value={data.manualChapterTitle || ""}
                  placeholder={titleValue || t("home.manual.defaultTitle")}
                  onChange={(event) => updateData({ manualChapterTitle: event.target.value })}
                />
              </label>
            </div>

            {duplicateGroups.length > 0 && (
              <DuplicateResolutionPanel
                duplicateGroups={duplicateGroups}
                resolution={duplicateResolution}
                onChange={setDuplicateResolution}
                t={t}
              />
            )}

            {!validation.ok && <p className="form-warning">{validation.messages[0]}</p>}

            <div className="submit-row">
              <button disabled={!canSubmit} type="submit">
                {isBusy ? <LoaderCircle className="spin-icon" size={17} /> : <Play size={17} />}
                {isBusy ? t("home.generating") : t("home.start")}
              </button>
              {status && <span className={statusType === "error" ? "status-error" : ""}>{status}</span>}
            </div>
          </section>
        </form>

        <FlowStatusPanel
          analysisRows={resolvedAnalysisRows}
          currentProject={currentProject}
          hasGeneratedContent={hasGeneratedContent}
          isBusy={isBusy}
          mode={mode}
          progressIndex={progressIndex}
          statusType={statusType}
          t={t}
        />
      </div>

      {!hasProject && (
        <div className="feature-grid" aria-label={t("home.features.aria")}>
          {productSteps(t).map((step) => (
            <FeatureCard key={step.title} {...step} />
          ))}
        </div>
      )}
    </section>
  );
}

function ContinueWorkPanel({
  canExport,
  chapterCount,
  currentProject,
  hasProgress,
  onFocusInput,
  onNavigate,
  sceneCount,
  scriptLineCount,
  t,
}) {
  const title = projectDisplayTitle(currentProject, t("app.project.untitled"));
  const description = hasProgress
    ? canExport
      ? t("home.continue.description.ready")
      : t("home.continue.description.draft")
    : t("home.continue.description.empty");

  return (
    <section className="continue-work-panel" aria-label={t("home.continue.aria")}>
      <div className="continue-main">
        <p className="eyebrow">{t("home.continue.overline")}</p>
        <h2>{hasProgress ? t("home.continue.title", { title }) : t("home.continue.emptyTitle", { title })}</h2>
        <p>{description}</p>
        <div className="continue-actions">
          {hasProgress ? (
            <>
              <button disabled={!chapterCount && !sceneCount} type="button" onClick={() => onNavigate("analysis")}>
                <BookOpenCheck size={16} />
                {t("home.continue.analysis")}
                <ArrowRight size={14} />
              </button>
              <button disabled={!sceneCount} type="button" onClick={() => onNavigate("preview")}>
                <Clapperboard size={16} />
                {t("home.continue.preview")}
                <ArrowRight size={14} />
              </button>
              <button className="primary" disabled={!canExport} type="button" onClick={() => onNavigate("export")}>
                <Download size={16} />
                {t("home.continue.export")}
                <ArrowRight size={14} />
              </button>
            </>
          ) : (
            <button className="primary" type="button" onClick={onFocusInput}>
              <Plus size={16} />
              {t("home.continue.addInput")}
              <ArrowRight size={14} />
            </button>
          )}
        </div>
      </div>
      <dl className="continue-side">
        <div>
          <dt>{t("home.continue.totalChapters")}</dt>
          <dd>{chapterCount}</dd>
        </div>
        <div>
          <dt>{t("home.continue.totalScenes")}</dt>
          <dd>{sceneCount}</dd>
        </div>
        <div>
          <dt>{t("home.continue.totalScriptLines")}</dt>
          <dd>{scriptLineCount}</dd>
        </div>
      </dl>
    </section>
  );
}

function DuplicateResolutionPanel({ duplicateGroups, onChange, resolution, t }) {
  const summaries = duplicateGroups.map((group) => duplicateGroupSummary(group, t));

  return (
    <section className="duplicate-resolution-panel" aria-label={t("home.duplicate.aria")}>
      <div className="duplicate-resolution-header">
        <strong>{t("home.duplicate.title")}</strong>
        <span>{t("home.duplicate.description")}</span>
      </div>
      <div className="duplicate-groups">
        {summaries.map((summary) => (
          <span key={summary.chapterIndex}>{summary.chapterLabel}</span>
        ))}
      </div>
      <div className="duplicate-preview-list">
        {summaries.map((summary) => (
          <article className="duplicate-preview-card" key={summary.chapterIndex}>
            <header>
              <strong>{summary.chapterLabel}</strong>
              <span>
                {t("home.duplicate.currentWords", { count: summary.currentWords })} /{" "}
                {t("home.duplicate.incomingWords", { count: summary.incomingWords })}
              </span>
            </header>
            <div className="duplicate-preview-grid">
              <DuplicatePreviewResult resolution={resolution} summary={summary} t={t} />
            </div>
          </article>
        ))}
      </div>
      <div className="duplicate-resolution-options">
        <button className={resolution === "merge" ? "active" : ""} type="button" onClick={() => onChange("merge")}>
          <GitMerge size={16} />
          <span>
            <strong>{t("home.duplicate.merge")}</strong>
            <small>{t("home.duplicate.mergeDescription")}</small>
          </span>
        </button>
        <button className={resolution === "replace" ? "active" : ""} type="button" onClick={() => onChange("replace")}>
          <Replace size={16} />
          <span>
            <strong>{t("home.duplicate.replace")}</strong>
            <small>{t("home.duplicate.replaceDescription")}</small>
          </span>
        </button>
      </div>
    </section>
  );
}

function DuplicatePreviewResult({ resolution, summary, t }) {
  const words = resolution === "replace" ? summary.replaceWords : summary.mergeWords;
  const preview = resolution === "replace" ? summary.replacePreview : summary.mergePreview;

  return (
    <div className="duplicate-preview-result">
      <strong>{t("home.duplicate.previewTitle")}</strong>
      <span>{t("home.duplicate.resultWords", { count: words })}</span>
      <p>{preview}</p>
    </div>
  );
}

function duplicateGroupSummary(group, t) {
  const current = group.rows[0] || {};
  const incomingRows = group.rows.slice(1);
  const latest = group.rows[group.rows.length - 1] || {};
  const mergeContent = group.rows.map((row) => row.content).filter(Boolean).join("\n\n");
  const replaceContent = latest.content || "";

  return {
    chapterIndex: group.chapterIndex,
    chapterLabel: t("analysis.chapterFallback", { index: group.chapterIndex }),
    currentWords: countWords(current.content),
    incomingWords: incomingRows.reduce((sum, row) => sum + countWords(row.content), 0),
    mergePreview: excerptText(mergeContent, 110),
    mergeWords: countWords(mergeContent),
    replacePreview: excerptText(replaceContent, 110),
    replaceWords: countWords(replaceContent),
  };
}

function HeroWorkflowPanel({ t }) {
  return (
    <aside className="hero-workflow-visual" aria-label={t("home.hero.visualAria")}>
      <div className="hero-script-preview">
        <div className="hero-preview-header">
          <Clapperboard size={17} />
          <strong>{t("home.hero.visualTitle")}</strong>
        </div>
        <div className="hero-preview-line camera">
          <span>{t("preview.filter.camera")}</span>
          <p>{t("home.hero.visual.camera")}</p>
        </div>
        <div className="hero-preview-line action">
          <span>{t("preview.filter.action")}</span>
          <p>{t("home.hero.visual.action")}</p>
        </div>
        <div className="hero-preview-line dialogue">
          <span>{t("preview.filter.dialogue")}</span>
          <p>{t("home.hero.visual.dialogue")}</p>
        </div>
      </div>
      <div className="hero-flow-steps">
        {progressKeys.map((stepKey, index) => (
          <span key={stepKey}>
            <strong>{String(index + 1).padStart(2, "0")}</strong>
            {t(stepKey)}
          </span>
        ))}
      </div>
    </aside>
  );
}

function FileRow({ onChange, onRemove, row, t }) {
  return (
    <article className="file-row">
      <div className="file-row-name">
        <FileText size={16} />
        <div>
          <strong>{row.fileName}</strong>
          <span>{t("home.files.wordCount", { count: row.wordCount || 0 })}</span>
        </div>
      </div>
      <label>
        <span>{t("home.files.chapterIndex")}</span>
        <input
          min="1"
          type="number"
          value={row.chapterIndex}
          onChange={(event) => onChange({ chapterIndex: Number(event.target.value) || 1 })}
        />
      </label>
      <label>
        <span>{t("home.files.chapterTitle")}</span>
        <input value={row.chapterTitle} onChange={(event) => onChange({ chapterTitle: event.target.value })} />
      </label>
      <button aria-label={t("home.files.remove")} type="button" onClick={onRemove}>
        <Trash2 size={15} />
      </button>
    </article>
  );
}

function FlowStatusPanel({ analysisRows, currentProject, hasGeneratedContent, isBusy, mode, progressIndex, statusType, t }) {
  const completed = !isBusy && (hasGeneratedContent || (statusType === "success" && progressIndex === progressKeys.length - 1));
  const visibleProgressIndex = completed ? progressKeys.length - 1 : progressIndex;
  const sceneCount = currentProject?.scriptYaml?.scenes?.length || 0;
  const chapterCount = currentProject?.chapters?.length || analysisRows.length || 0;
  const title = currentProject ? projectDisplayTitle(currentProject, t("app.project.untitled")) : t("app.project.none");

  return (
    <aside className="flow-status-panel" aria-label={t("pipeline.aria")}>
      <div className="flow-status-header">
        <div>
          <p className="eyebrow">{t("pipeline.overline")}</p>
          <h2>{isBusy ? t("pipeline.title.busy") : completed ? t("pipeline.title.done") : t("pipeline.title.idle")}</h2>
          <p>
            {isBusy
              ? t("pipeline.description.busy", { step: t(progressKeys[Math.max(progressIndex, 0)]) })
              : completed
                ? t("pipeline.description.done")
                : t("pipeline.description.idle")}
          </p>
        </div>
        <span className="status-chip">{mode === "api" ? t("pipeline.mode.api") : t("pipeline.mode.mock")}</span>
      </div>
      <div className="project-summary-panel">
        <h3>{t("pipeline.summary.title")}</h3>
        <dl>
          <div>
            <dt>{t("pipeline.summary.project")}</dt>
            <dd>{title}</dd>
          </div>
          <div>
            <dt>{t("pipeline.summary.chapters")}</dt>
            <dd>{chapterCount}</dd>
          </div>
          <div>
            <dt>{t("pipeline.summary.scenes")}</dt>
            <dd>{sceneCount}</dd>
          </div>
        </dl>
      </div>
      <div className="progress-panel" aria-label={t("pipeline.progressAria")}>
        {progressKeys.map((stepKey, index) => (
          <div className={progressClass(index, visibleProgressIndex, completed ? "success" : statusType)} key={stepKey}>
            <span>{index + 1}</span>
            <strong>{t(stepKey)}</strong>
          </div>
        ))}
      </div>
      {isBusy && (
        <div className="skeleton-stack" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      )}
    </aside>
  );
}

function FeatureCard({ detail, icon: Icon, tech, title }) {
  return (
    <article className="feature-card">
      <span className="feature-icon">
        <Icon size={19} />
      </span>
      <span className="feature-tech">{tech}</span>
      <h3>{title}</h3>
      <p>{detail}</p>
    </article>
  );
}

function productSteps(t) {
  return [
    { icon: UploadCloud, title: t("feature.chapter.title"), tech: "CHAPTER PARSING", detail: t("feature.chapter.detail") },
    { icon: BookOpenCheck, title: t("feature.entity.title"), tech: "ENTITY EXTRACTION", detail: t("feature.entity.detail") },
    { icon: Clapperboard, title: t("feature.scene.title"), tech: "SCENE GENERATION", detail: t("feature.scene.detail") },
    { icon: Boxes, title: t("feature.export.title"), tech: "STRUCTURED EXPORT", detail: t("feature.export.detail") },
  ];
}

function progressClass(index, progressIndex, statusType) {
  if (statusType === "error" && index === progressIndex) {
    return "progress-step error";
  }
  if (progressIndex === progressKeys.length - 1 && statusType === "success") {
    return "progress-step done";
  }
  if (index < progressIndex) {
    return "progress-step done";
  }
  if (index === progressIndex) {
    return "progress-step active";
  }
  return "progress-step";
}

function progressIndexFromEvent(event) {
  if (event.stage === "chapter_parse") {
    return 0;
  }
  if (event.stage === "chapter_generate") {
    return 3;
  }
  if (event.stage === "schema_validate") {
    return 4;
  }
  return 0;
}

function progressStatusFromEvent(event, t) {
  if (event.stage === "chapter_parse" && event.type === "stage_complete") {
    return `${t("pipeline.step.chapter")}完成`;
  }
  if (event.stage === "chapter_generate") {
    const chapter = event.chapter_title || event.chapter_index || event.current;
    const prefix = `${t("pipeline.step.script")} ${event.current || ""}/${event.total || ""}`;
    if (event.type === "stage_start") {
      return `${prefix}：${chapter}`;
    }
    const elapsed = event.log?.elapsed_seconds;
    return `${prefix}完成：${chapter}${elapsed ? `，${elapsed}s` : ""}`;
  }
  if (event.stage === "schema_validate") {
    return event.type === "stage_start" ? t("pipeline.step.schema") : `${t("pipeline.step.schema")}完成`;
  }
  return "";
}

function buildAnalysisRows(data, fileRows, t) {
  const rows = fileRows.map((row) => ({
    ...row,
    chapterIndex: Number(row.chapterIndex) || 1,
    chapterTitle: row.chapterTitle?.trim() || titleFromFilename(row.fileName, Number(row.chapterIndex) || 1, t),
    sourceType: "file",
    wordCount: row.wordCount ?? countWords(row.content),
  }));

  const manualInput = String(data.manualInput || "").trim();
  if (manualInput) {
    const chapterIndex = Number(data.manualChapterIndex) || nextChapterIndex(rows);
    rows.push({
      id: "manual_input",
      fileName: "manual_input.txt",
      chapterIndex,
      chapterTitle: data.manualChapterTitle?.trim() || data.title?.trim() || t("home.manual.defaultTitle"),
      content: manualInput,
      sourceType: "manual",
      wordCount: countWords(manualInput),
    });
  }

  return rows;
}

function duplicateGroupsFromRows(rows) {
  const byChapter = new Map();
  rows.forEach((row) => {
    const chapterIndex = Number(row.chapterIndex);
    const group = byChapter.get(chapterIndex) || [];
    group.push(row);
    byChapter.set(chapterIndex, group);
  });
  return Array.from(byChapter.entries())
    .filter(([_chapterIndex, group]) => group.length > 1)
    .map(([chapterIndex, group]) => ({ chapterIndex, rows: group }));
}

function resolveDuplicateRows(rows, resolution) {
  if (resolution === "replace") {
    const byChapter = new Map();
    rows.forEach((row) => {
      byChapter.set(Number(row.chapterIndex), row);
    });
    return Array.from(byChapter.values());
  }

  const byChapter = new Map();
  rows.forEach((row) => {
    const chapterIndex = Number(row.chapterIndex);
    const existing = byChapter.get(chapterIndex);
    if (!existing) {
      byChapter.set(chapterIndex, { ...row });
      return;
    }
    const content = [existing.content, row.content].filter(Boolean).join("\n\n");
    byChapter.set(chapterIndex, {
      ...existing,
      id: `${existing.id}_${row.id}`,
      fileName: [existing.fileName, row.fileName].filter(Boolean).join(", "),
      chapterTitle: existing.chapterTitle || row.chapterTitle,
      content,
      sourceType: "merged",
      wordCount: countWords(content),
    });
  });
  return Array.from(byChapter.values());
}

function validateRows(rows, t) {
  const messages = [];
  if (rows.some((row) => !Number.isInteger(Number(row.chapterIndex)) || Number(row.chapterIndex) <= 0)) {
    messages.push(t("home.files.positiveWarning"));
  }
  return { ok: messages.length === 0, messages };
}

function formatChapterForSource(row) {
  return `第 ${row.chapterIndex} 章 ${row.chapterTitle}\n${row.content.trim()}`;
}

function normalizedProjectTitle(title, t) {
  return String(title || "").trim() || t("app.project.untitled");
}

function nextChapterIndex(rows) {
  return rows.reduce((max, row) => Math.max(max, Number(row.chapterIndex) || 0), 0) + 1;
}

function titleFromFilename(fileName, chapterIndex, t) {
  const base = String(fileName || "").replace(/\.[^.]+$/, "").trim();
  return base || t("analysis.chapterFallback", { index: chapterIndex });
}

function countWords(text) {
  return String(text || "").replace(/\s+/g, "").length;
}

function excerptText(value, maxLength) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "";
  }
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}...`;
}
