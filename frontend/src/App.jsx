import {
  BookOpenText,
  ChevronDown,
  Clapperboard,
  Clock3,
  Download,
  FolderOpen,
  House,
  Moon,
  PencilLine,
  Plus,
  Sparkles,
  Sun,
  Trash2,
  RotateCcw,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import LanguageSelect from "../components/LanguageSelect.jsx";
import Analysis from "../pages/Analysis.jsx";
import Export from "../pages/Export.jsx";
import Home from "../pages/Home.jsx";
import ScriptPreview from "../pages/ScriptPreview.jsx";
import { useI18n } from "./i18n/useI18n.js";
import { createEmptyScriptYaml, projectDisplayTitle, useProjects } from "./projectStore.jsx";

const THEME_KEY = "scriptwhisper.theme";

const navItems = [
  {
    id: "home",
    labelKey: "app.nav.home",
    icon: House,
    titleKey: "app.page.home.title",
    descriptionKey: "app.page.home.description",
  },
  {
    id: "analysis",
    labelKey: "app.nav.analysis",
    icon: BookOpenText,
    titleKey: "app.page.analysis.title",
    descriptionKey: "app.page.analysis.description",
  },
  {
    id: "preview",
    labelKey: "app.nav.preview",
    icon: Clapperboard,
    titleKey: "app.page.preview.title",
    descriptionKey: "app.page.preview.description",
  },
  {
    id: "export",
    labelKey: "app.nav.export",
    icon: Download,
    titleKey: "app.page.export.title",
    descriptionKey: "app.page.export.description",
  },
];

export default function App() {
  const [activePage, setActivePage] = useState("home");
  const [theme, setTheme] = useState(loadInitialTheme);
  const { languageOptions, locale, setLocale, t } = useI18n();
  const {
    createProject,
    currentProject,
    deleteProject,
    projects,
    renameProject,
    setCurrentProject,
    updateCurrentProjectData,
    updateProject,
  } = useProjects();
  const page = navItems.find((item) => item.id === activePage) || navItems[0];
  const scriptYaml = currentProject?.scriptYaml || createEmptyScriptYaml("");
  const sceneCount = scriptYaml.scenes?.length || 0;

  useEffect(() => {
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  function handleAnalysisComplete(result, runContext) {
    const normalizedChapters = normalizeChapters(result.chapters || [], runContext.chapterFiles || []);
    const nextYaml = syncScriptYamlToChapters(
      result.script_yaml || createEmptyScriptYaml(runContext.title),
      normalizedChapters,
      runContext.title,
      runContext.source,
    );

    updateProject(runContext.projectId, {
      chapterFiles: runContext.chapterFiles,
      chapters: normalizedChapters,
      issues: result.issues || [],
      manualChapterIndex: runContext.manualChapterIndex,
      manualChapterTitle: runContext.manualChapterTitle,
      manualInput: runContext.manualInput,
      mockMode: result.mock_mode,
      mode: runContext.mode,
      repaired: result.repaired,
      scriptYaml: nextYaml,
      stageLogs: result.stage_logs || [],
      status: "generated",
      title: runContext.title,
      uiState: {
        selectedChapterId: normalizedChapters[0]?.id || "",
        selectedSceneId: nextYaml.scenes?.[0]?.id || "",
        selectedLineId: "",
        scriptLineFilter: "all",
      },
      chapterAnnotations: [],
    });
    setActivePage("analysis");
  }

  function handleScriptYamlChange(nextYaml) {
    if (!currentProject) {
      return;
    }
    updateCurrentProjectData({
      scriptYaml: syncScriptYamlToChapters(
        nextYaml,
        currentProject.chapters || [],
        projectDisplayTitle(currentProject, t("app.project.untitled")),
      ),
      status: nextYaml.scenes?.length ? "generated" : currentProject.status,
    });
  }

  function handleRenameChapter(chapterId, nextTitle) {
    if (!currentProject) {
      return;
    }
    updateCurrentProjectData((project) => {
      const chapters = (project.chapters || []).map((chapter) => {
        if (chapter.id !== chapterId && chapter.chapterId !== chapterId && chapter.chapter_id !== chapterId) {
          return chapter;
        }
        const chapterIndex = chapter.chapterIndex || chapter.chapter_index || 1;
        return { ...chapter, title: nextTitle.trim() || t("analysis.chapterFallback", { index: chapterIndex }) };
      });
      const updatedChapter = chapters.find(
        (chapter) => chapter.id === chapterId || chapter.chapterId === chapterId || chapter.chapter_id === chapterId,
      );
      const chapterFiles = (project.chapterFiles || []).map((file) => {
        if (updatedChapter && Number(file.chapterIndex) === Number(updatedChapter.chapterIndex)) {
          return { ...file, chapterTitle: updatedChapter.title };
        }
        return file;
      });
      const scriptYaml = {
        ...project.scriptYaml,
        scenes: (project.scriptYaml?.scenes || []).map((scene) => {
          const source = scene.source_ref || {};
          if (source.chapter_id !== chapterId && source.chapterId !== chapterId) {
            return scene;
          }
          const chapterIndex = updatedChapter?.chapterIndex || source.chapter_index || source.chapterIndex || 1;
          return {
            ...scene,
            source_ref: {
              ...source,
              chapter_id: chapterId,
              chapter_index: chapterIndex,
              chapter_title: updatedChapter?.title || t("analysis.chapterFallback", { index: chapterIndex }),
            },
          };
        }),
      };
      return { chapterFiles, chapters, scriptYaml };
    });
  }

  function handleRenameScene(sceneId, nextTitle) {
    if (!currentProject) {
      return;
    }
    const title = nextTitle.trim() || t("preview.untitledScene");
    updateCurrentProjectData((project) => ({
      scriptYaml: {
        ...project.scriptYaml,
        scenes: (project.scriptYaml?.scenes || []).map((scene) => (scene.id === sceneId ? { ...scene, title } : scene)),
      },
    }));
  }

  return (
    <main className="app-shell" data-theme={theme}>
      <aside className="app-sidebar">
        <div className="brand-block">
          <span className="brand-mark" aria-hidden="true">
            SW
          </span>
          <div>
            <strong>ScriptWhisper</strong>
            <span>AI Script Studio</span>
          </div>
        </div>

        <ProjectModule
          currentProject={currentProject}
          onCreateProject={(title) => createProject({ title: title || t("app.project.untitled"), fallbackTitle: t("app.project.untitled") })}
          onDeleteProject={deleteProject}
          onRenameProject={renameProject}
          onRestoreProject={(project) => createProject({ ...project, fallbackTitle: t("app.project.untitled") })}
          onSwitchProject={setCurrentProject}
          projects={projects}
          t={t}
        />

        <nav className="sidebar-nav" aria-label={t("app.nav.aria")}>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={`sidebar-nav-item ${activePage === item.id ? "active" : ""}`}
                key={item.id}
                type="button"
                onClick={() => setActivePage(item.id)}
              >
                <Icon size={17} />
                <span>{t(item.labelKey)}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-status">
            <span className="status-dot" aria-hidden="true" />
            <div>
              <strong>{currentProject ? projectDisplayTitle(currentProject, t("app.project.untitled")) : t("app.project.none")}</strong>
              <span>{currentProject ? projectStatusLabel(currentProject, t) : t("app.project.emptyHint")}</span>
            </div>
          </div>
        </div>
      </aside>

      <section className="app-content">
        <header className="topbar">
          <div className="topbar-title">
            <p className="eyebrow">{t(page.labelKey)}</p>
            <h1>{t(page.titleKey)}</h1>
            <p>{t(page.descriptionKey)}</p>
          </div>
          <div className="topbar-actions">
            {currentProject && (
              <>
                <span className="status-chip">
                  <Sparkles size={14} />
                  {currentProject.mode === "api" ? t("app.mode.api") : t("app.mode.mock")}
                </span>
              </>
            )}
            <LanguageSelect label={t("app.systemLanguage")} onChange={setLocale} options={languageOptions} value={locale} />
            <button
              className="icon-button"
              type="button"
              aria-label={theme === "dark" ? t("app.theme.toLight") : t("app.theme.toDark")}
              title={theme === "dark" ? t("app.theme.light") : t("app.theme.dark")}
              onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
            >
              {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            </button>
          </div>
        </header>

        <div className="page-body">
          {activePage === "home" && (
            <Home
              createProject={createProject}
              currentProject={currentProject}
              hasGeneratedContent={Boolean(scriptYaml.script?.length)}
              languageOptions={languageOptions}
              onNavigate={setActivePage}
              onAnalysisComplete={handleAnalysisComplete}
              renameProject={renameProject}
              t={t}
              updateCurrentProjectData={updateCurrentProjectData}
            />
          )}
          {activePage === "analysis" && (
            <Analysis
              chapters={currentProject?.chapters || []}
              currentProject={currentProject}
              issues={currentProject?.issues || []}
              mockMode={currentProject?.mockMode}
              onRenameChapter={handleRenameChapter}
              repaired={currentProject?.repaired}
              scriptYaml={scriptYaml}
              t={t}
              updateCurrentProjectData={updateCurrentProjectData}
            />
          )}
          {activePage === "preview" && (
            <ScriptPreview
              chapters={currentProject?.chapters || []}
              currentProject={currentProject}
              onRenameChapter={handleRenameChapter}
              onRenameScene={handleRenameScene}
              onScriptYamlChange={handleScriptYamlChange}
              scriptYaml={scriptYaml}
              t={t}
              updateCurrentProjectData={updateCurrentProjectData}
            />
          )}
          {activePage === "export" && (
            <Export chapters={currentProject?.chapters || []} currentProject={currentProject} scriptYaml={scriptYaml} t={t} />
          )}
        </div>
      </section>
    </main>
  );
}

function ProjectModule({
  currentProject,
  onCreateProject,
  onDeleteProject,
  onRenameProject,
  onRestoreProject,
  onSwitchProject,
  projects,
  t,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [dialog, setDialog] = useState(null);
  const [deletedProject, setDeletedProject] = useState(null);
  const [projectFilter, setProjectFilter] = useState("all");
  const title = currentProject ? projectDisplayTitle(currentProject, t("app.project.untitled")) : t("app.project.none");
  const filteredProjects = useMemo(
    () =>
      [...projects]
        .filter((project) => projectFilter === "all" || projectStatusKind(project) === projectFilter)
        .sort((a, b) => Date.parse(b.updatedAt || b.createdAt || 0) - Date.parse(a.updatedAt || a.createdAt || 0)),
    [projectFilter, projects],
  );

  useEffect(() => {
    if (!deletedProject) {
      return undefined;
    }
    const timer = window.setTimeout(() => setDeletedProject(null), 6200);
    return () => window.clearTimeout(timer);
  }, [deletedProject]);

  function openRename(project) {
    setDialog({
      type: "rename",
      project,
      draftTitle: projectDisplayTitle(project, t("app.project.untitled")),
    });
  }

  function openCreate() {
    setDialog({
      type: "create",
      draftTitle: "",
    });
    setIsOpen(false);
  }

  function openDelete(project) {
    setDeletedProject(project);
    onDeleteProject(project.id);
    setIsOpen(false);
  }

  function closeDialog() {
    setDialog(null);
  }

  function updateDialogTitle(nextTitle) {
    setDialog((current) => (current ? { ...current, draftTitle: nextTitle } : current));
  }

  function submitDialog(event) {
    event.preventDefault();
    if (!dialog) {
      return;
    }
    const title = dialog.draftTitle.trim() || t("app.project.untitled");
    if (dialog.type === "create") {
      onCreateProject(title);
    }
    if (dialog.type === "rename") {
      onRenameProject(dialog.project.id, title);
    }
    closeDialog();
    setIsOpen(false);
  }

  function undoDelete() {
    if (!deletedProject) {
      return;
    }
    onRestoreProject(deletedProject);
    setDeletedProject(null);
  }

  return (
    <section className="project-module">
      <button
        aria-expanded={isOpen}
        className="project-current-card"
        type="button"
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className="project-icon">
          <FolderOpen size={16} />
        </span>
        <span>
          <small>{t("app.project.current")}</small>
          <strong>{title}</strong>
          <em>{currentProject ? projectStatusLabel(currentProject, t) : t("app.project.emptyHint")}</em>
        </span>
        <ChevronDown size={15} />
      </button>

      {isOpen && (
        <div className="project-menu">
          <button
            className="project-menu-action"
            type="button"
            onClick={openCreate}
          >
            <Plus size={14} />
            {t("app.project.new")}
          </button>
          {projects.length ? (
            <>
              <div className="project-menu-filters" aria-label={t("app.project.filterAria")}>
                {[
                  ["all", t("app.project.filter.all")],
                  ["ready", t("app.project.filter.ready")],
                  ["draft", t("app.project.filter.draft")],
                ].map(([value, label]) => (
                  <button
                    className={projectFilter === value ? "active" : ""}
                    key={value}
                    type="button"
                    onClick={() => setProjectFilter(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="project-list">
                {filteredProjects.length ? (
                  filteredProjects.map((project) => {
                    const isCurrent = project.id === currentProject?.id;
                    return (
                      <article className={`project-list-item ${isCurrent ? "active" : ""}`} key={project.id}>
                        <button type="button" onClick={() => onSwitchProject(project.id)}>
                          <strong>{projectDisplayTitle(project, t("app.project.untitled"))}</strong>
                          <span>{projectStatusLabel(project, t)}</span>
                          <small>
                            <Clock3 size={12} />
                            {t("app.project.updatedAt", { time: formatProjectUpdatedAt(project) })}
                          </small>
                        </button>
                        <div className="project-row-actions">
                          <button aria-label={t("app.project.rename")} type="button" onClick={() => openRename(project)}>
                            <PencilLine size={13} />
                          </button>
                          <button aria-label={t("app.project.delete")} type="button" onClick={() => openDelete(project)}>
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </article>
                    );
                  })
                ) : (
                  <p className="empty-state compact">{t("app.project.filterEmpty")}</p>
                )}
              </div>
            </>
          ) : (
            <p className="empty-state compact">{t("app.project.emptyHint")}</p>
          )}
        </div>
      )}
      {dialog && (
        <ProjectDialog
          dialog={dialog}
          onClose={closeDialog}
          onSubmit={submitDialog}
          onTitleChange={updateDialogTitle}
          t={t}
        />
      )}
      {deletedProject && <ProjectUndoToast project={deletedProject} onClose={() => setDeletedProject(null)} onUndo={undoDelete} t={t} />}
    </section>
  );
}

function ProjectDialog({ dialog, onClose, onSubmit, onTitleChange, t }) {
  const isCreate = dialog.type === "create";
  const DialogIcon = isCreate ? Plus : PencilLine;

  return createPortal(
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form
        className="project-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="project-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
        onSubmit={onSubmit}
      >
        <header>
          <span className="project-dialog-icon" aria-hidden="true">
            <DialogIcon size={18} />
          </span>
          <div>
            <h2 id="project-dialog-title">{isCreate ? t("app.project.createTitle") : t("app.project.renameTitle")}</h2>
            <p>{isCreate ? t("app.project.createDescription") : t("app.project.renameDescription")}</p>
          </div>
          <button aria-label={t("common.cancel")} type="button" onClick={onClose}>
            <X size={16} />
          </button>
        </header>

        <label className="project-dialog-field">
          <span>{t("app.project.name")}</span>
          <input
            autoFocus
            value={dialog.draftTitle}
            placeholder={t("app.project.untitled")}
            onChange={(event) => onTitleChange(event.target.value)}
          />
        </label>

        <footer>
          <button type="button" onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button className="primary" type="submit">
            {isCreate ? t("app.project.new") : t("app.project.rename")}
          </button>
        </footer>
      </form>
    </div>,
    document.body,
  );
}

function ProjectUndoToast({ onClose, onUndo, project, t }) {
  return createPortal(
    <div className="project-undo-toast" role="status" aria-live="polite">
      <div>
        <strong>{t("app.project.deletedToast", { title: projectDisplayTitle(project, t("app.project.untitled")) })}</strong>
        <span>{t("app.project.deletedToastHint")}</span>
      </div>
      <button className="project-undo-button" type="button" onClick={onUndo}>
        <RotateCcw size={14} />
        {t("app.project.undoDelete")}
      </button>
      <button className="project-toast-close" aria-label={t("common.close")} type="button" onClick={onClose}>
        <X size={14} />
      </button>
    </div>,
    document.body,
  );
}

function projectStatusKind(project) {
  const sceneCount = project.scriptYaml?.scenes?.length || 0;
  return sceneCount > 0 || project.status === "generated" ? "ready" : "draft";
}

function formatProjectUpdatedAt(project) {
  const value = project.updatedAt || project.createdAt;
  const date = value ? new Date(value) : new Date();
  return date.toLocaleString(undefined, {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
  });
}

function projectStatusLabel(project, t) {
  const sceneCount = project.scriptYaml?.scenes?.length || 0;
  const chapterCount = project.chapters?.length || project.chapterFiles?.length || 0;
  if (project.status === "generated" && sceneCount > 0) {
    return t("app.project.readyToExport");
  }
  if (sceneCount > 0) {
    return t("app.project.scenesReady", { count: sceneCount });
  }
  if (chapterCount > 0) {
    return t("app.project.analyzed", { count: chapterCount });
  }
  return t("app.project.draft");
}

function loadInitialTheme() {
  try {
    return window.localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

function normalizeChapters(chapters, chapterFiles = []) {
  const resultByIndex = new Map(
    chapters.map((chapter, index) => {
      const chapterIndex = Number(chapter.chapter_index || chapter.chapterIndex || index + 1);
      return [chapterIndex, chapter];
    }),
  );
  const sourceRows = chapterFiles.length
    ? chapterFiles
    : chapters.map((chapter, index) => ({
        chapterIndex: chapter.chapter_index || chapter.chapterIndex || index + 1,
        chapterTitle: chapter.title || chapter.heading,
        content: chapter.content || "",
        wordCount: chapter.word_count || chapter.wordCount,
      }));

  return sourceRows.map((row, index) => {
    const chapterIndex = Number(row.chapterIndex || index + 1);
    const chapter = resultByIndex.get(chapterIndex) || chapters[index] || {};
    const id = chapter.chapter_id || chapter.chapterId || chapter.id || `chapter_${chapterIndex}`;
    const content = chapter.content || row.content || "";
    return {
      id,
      chapterId: id,
      chapterIndex,
      chapter_id: id,
      chapter_index: chapterIndex,
      title: row.chapterTitle || chapter.title || chapter.heading || `第 ${chapterIndex} 章`,
      content,
      summary: chapter.summary || "",
      wordCount: chapter.wordCount ?? chapter.word_count ?? row.wordCount ?? countWords(content),
      status: chapter.status || "已分析",
    };
  });
}

function syncScriptYamlToChapters(scriptYaml, chapters, title, source = "") {
  const project = { ...(scriptYaml.project || {}) };
  const chapterById = new Map(chapters.map((chapter) => [chapter.id || chapter.chapterId || chapter.chapter_id, chapter]));
  const chapterByIndex = new Map(chapters.map((chapter) => [Number(chapter.chapterIndex || chapter.chapter_index), chapter]));

  return {
    ...scriptYaml,
    project: {
      ...project,
      title,
      source: source || project.source || "",
    },
    characters: Array.isArray(scriptYaml.characters) ? scriptYaml.characters : [],
    locations: Array.isArray(scriptYaml.locations) ? scriptYaml.locations : [],
    scenes: (scriptYaml.scenes || []).map((scene, index) => {
      const sourceRef = scene.source_ref || {};
      const chapter =
        chapterById.get(sourceRef.chapter_id || sourceRef.chapterId) ||
        chapterByIndex.get(Number(sourceRef.chapter_index || sourceRef.chapterIndex)) ||
        chapters[Math.min(index, Math.max(chapters.length - 1, 0))];
      if (!chapter) {
        return scene;
      }
      return {
        ...scene,
        source_ref: {
          ...sourceRef,
          chapter_id: chapter.id || chapter.chapterId || chapter.chapter_id,
          chapter_index: chapter.chapterIndex || chapter.chapter_index,
          chapter_title: chapter.title,
        },
      };
    }),
    script: Array.isArray(scriptYaml.script) ? scriptYaml.script : [],
  };
}

function countWords(text) {
  return String(text || "").replace(/\s+/g, "").length;
}
