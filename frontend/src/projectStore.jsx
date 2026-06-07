import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { chapters as sampleChapters, scriptYaml as sampleScriptYaml } from "./sampleData.js";

const PROJECTS_KEY = "scriptwhisper.projects";
const CURRENT_PROJECT_KEY = "scriptwhisper.currentProjectId";
const LEGACY_PROJECT_KEY = "scriptwhisper.project";

const ProjectContext = createContext(null);

export function ProjectProvider({ children }) {
  const initialState = useMemo(loadInitialState, []);
  const [projects, setProjects] = useState(initialState.projects);
  const [currentProjectId, setCurrentProjectIdState] = useState(initialState.currentProjectId);

  const currentProject = useMemo(
    () => projects.find((project) => project.id === currentProjectId) || null,
    [currentProjectId, projects],
  );

  useEffect(() => {
    window.localStorage.setItem(PROJECTS_KEY, JSON.stringify(projects));
    if (currentProjectId) {
      window.localStorage.setItem(CURRENT_PROJECT_KEY, currentProjectId);
    } else {
      window.localStorage.removeItem(CURRENT_PROJECT_KEY);
    }
  }, [currentProjectId, projects]);

  function createProject(input = {}) {
    const now = new Date().toISOString();
    const title = normalizeTitle(input.title, input.fallbackTitle);
    const project = normalizeProject({
      id: input.id || `project_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      title,
      createdAt: now,
      updatedAt: now,
      status: input.status || "draft",
      mode: input.mode || "mock",
      manualInput: input.manualInput || "",
      manualChapterIndex: input.manualChapterIndex || 1,
      manualChapterTitle: input.manualChapterTitle || "",
      chapterFiles: input.chapterFiles || [],
      chapters: input.chapters || [],
      issues: input.issues || [],
      mockMode: input.mockMode ?? input.mode === "mock",
      repaired: input.repaired || false,
      scriptYaml: input.scriptYaml || createEmptyScriptYaml(title),
      exports: input.exports || { yaml: "", markdown: "" },
      uiState: input.uiState,
      chapterAnnotations: input.chapterAnnotations,
    });

    setProjects((current) => [...current, project]);
    setCurrentProjectIdState(project.id);
    return project;
  }

  function updateProject(projectId, updates) {
    setProjects((current) =>
      current.map((project) => {
        if (project.id !== projectId) {
          return project;
        }
        const resolvedUpdates = typeof updates === "function" ? updates(project) : updates;
        return normalizeProject({
          ...project,
          ...resolvedUpdates,
          updatedAt: new Date().toISOString(),
        });
      }),
    );
  }

  function updateCurrentProjectData(updates) {
    if (!currentProjectId) {
      return;
    }
    updateProject(currentProjectId, updates);
  }

  function renameProject(projectId, nextTitle) {
    updateProject(projectId, (project) => {
      const title = nextTitle;
      return {
        title,
        scriptYaml: {
          ...project.scriptYaml,
          project: {
            ...(project.scriptYaml?.project || {}),
            title: title || project.scriptYaml?.project?.title || "",
          },
        },
      };
    });
  }

  function deleteProject(projectId) {
    setProjects((current) => {
      const nextProjects = current.filter((project) => project.id !== projectId);
      if (projectId === currentProjectId) {
        setCurrentProjectIdState(nextProjects.at(-1)?.id || "");
      }
      return nextProjects;
    });
  }

  function setCurrentProject(projectId) {
    if (projects.some((project) => project.id === projectId)) {
      setCurrentProjectIdState(projectId);
    }
  }

  const value = useMemo(
    () => ({
      createProject,
      currentProject,
      currentProjectId,
      deleteProject,
      projects,
      renameProject,
      setCurrentProject,
      updateCurrentProjectData,
      updateProject,
    }),
    [currentProject, currentProjectId, projects],
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProjects() {
  const value = useContext(ProjectContext);
  if (!value) {
    throw new Error("useProjects must be used inside ProjectProvider");
  }
  return value;
}

export function createEmptyScriptYaml(title = "") {
  return {
    project: {
      title,
      version: "1.0",
      genre: "",
      logline: "",
      source: "",
      source_language: "zh",
      target_language: "zh",
      bible: {},
    },
    characters: [],
    locations: [],
    scenes: [],
    script: [],
  };
}

export function projectDisplayTitle(project, fallback = "未命名项目") {
  return String(project?.title || project?.scriptYaml?.project?.title || fallback).trim() || fallback;
}

export function projectStatus(project) {
  if (!project) {
    return "empty";
  }
  const sceneCount = project.scriptYaml?.scenes?.length || 0;
  if (sceneCount > 0) {
    return project.status === "generated" ? "generated" : "analyzed";
  }
  return project.status || "draft";
}

function loadInitialState() {
  try {
    const savedProjects = JSON.parse(window.localStorage.getItem(PROJECTS_KEY) || "[]");
    if (Array.isArray(savedProjects) && savedProjects.length) {
      const projects = savedProjects.map(normalizeProject);
      const savedCurrentId = window.localStorage.getItem(CURRENT_PROJECT_KEY);
      return {
        projects,
        currentProjectId: projects.some((project) => project.id === savedCurrentId) ? savedCurrentId : projects[0].id,
      };
    }

    const legacy = JSON.parse(window.localStorage.getItem(LEGACY_PROJECT_KEY) || "null");
    if (legacy) {
      const project = normalizeProject(projectFromLegacy(legacy));
      return { projects: [project], currentProjectId: project.id };
    }
  } catch {
    // Fall through to a bundled demo project.
  }

  const sampleProject = createSampleProject();
  return { projects: [sampleProject], currentProjectId: sampleProject.id };
}

function projectFromLegacy(legacy) {
  const title = legacy.scriptYaml?.project?.title || "未命名项目";
  return {
    id: "project_migrated",
    title,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    status: legacy.scriptYaml?.scenes?.length ? "generated" : "draft",
    mode: legacy.mockMode ? "mock" : "api",
    manualInput: chaptersToText(legacy.chapters || []),
    manualChapterIndex: 1,
    manualChapterTitle: "",
    chapterFiles: chapterFilesFromChapters(legacy.chapters || []),
    chapters: legacy.chapters || [],
    issues: legacy.issues || [],
    mockMode: legacy.mockMode ?? true,
    repaired: legacy.repaired || false,
    scriptYaml: legacy.scriptYaml || createEmptyScriptYaml(title),
    exports: { yaml: "", markdown: "" },
    uiState: legacy.uiState,
    chapterAnnotations: legacy.chapterAnnotations,
  };
}

function createSampleProject() {
  const title = sampleScriptYaml.project?.title || "雨夜来信";
  return normalizeProject({
    id: "project_sample",
    title,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    status: "generated",
    mode: "mock",
    manualInput: "",
    manualChapterIndex: 1,
    manualChapterTitle: "",
    chapterFiles: chapterFilesFromChapters(sampleChapters),
    chapters: sampleChapters,
    issues: [],
    mockMode: true,
    repaired: false,
    scriptYaml: sampleScriptYaml,
    exports: { yaml: "", markdown: "" },
    uiState: {},
    chapterAnnotations: [],
  });
}

function normalizeProject(project) {
  const title = project.title ?? project.scriptYaml?.project?.title ?? "";
  const scriptYaml = project.scriptYaml || createEmptyScriptYaml(title);
  const scriptProject = { ...(scriptYaml.project || {}) };
  return {
    id: project.id,
    title,
    createdAt: project.createdAt || new Date().toISOString(),
    updatedAt: project.updatedAt || new Date().toISOString(),
    status: project.status || "draft",
    mode: project.mode || (project.mockMode ? "mock" : "api"),
    manualInput: project.manualInput || "",
    manualChapterIndex: Number(project.manualChapterIndex) || 1,
    manualChapterTitle: project.manualChapterTitle || "",
    chapterFiles: Array.isArray(project.chapterFiles) ? project.chapterFiles.map(normalizeChapterFile) : [],
    chapters: Array.isArray(project.chapters) ? project.chapters : [],
    issues: Array.isArray(project.issues) ? project.issues : [],
    mockMode: project.mockMode ?? project.mode === "mock",
    repaired: Boolean(project.repaired),
    uiState: normalizeUiState(project.uiState),
    chapterAnnotations: normalizeChapterAnnotations(project.chapterAnnotations),
    scriptYaml: {
      ...scriptYaml,
      project: {
        ...scriptProject,
        title: title || scriptYaml.project?.title || "",
      },
      characters: Array.isArray(scriptYaml.characters) ? scriptYaml.characters : [],
      locations: Array.isArray(scriptYaml.locations) ? scriptYaml.locations : [],
      scenes: Array.isArray(scriptYaml.scenes) ? scriptYaml.scenes : [],
      script: Array.isArray(scriptYaml.script) ? scriptYaml.script : [],
    },
    exports: project.exports || { yaml: "", markdown: "" },
  };
}

function normalizeUiState(uiState = {}) {
  return {
    selectedChapterId: typeof uiState.selectedChapterId === "string" ? uiState.selectedChapterId : "",
    selectedSceneId: typeof uiState.selectedSceneId === "string" ? uiState.selectedSceneId : "",
    selectedLineId: typeof uiState.selectedLineId === "string" ? uiState.selectedLineId : "",
    scriptLineFilter: typeof uiState.scriptLineFilter === "string" ? uiState.scriptLineFilter : "all",
  };
}

function normalizeChapterAnnotations(annotations = []) {
  if (!Array.isArray(annotations)) {
    return [];
  }
  return annotations
    .map((annotation) => ({
      chapterId: String(annotation.chapterId || annotation.chapter_id || ""),
      paragraphIndex: Number(annotation.paragraphIndex ?? annotation.paragraph_index),
      highlightColor: annotation.highlightColor || annotation.highlight_color || "",
      note: String(annotation.note || ""),
      selectedText: String(annotation.selectedText || annotation.selected_text || ""),
      selectionEnd:
        annotation.selectionEnd === undefined && annotation.selection_end === undefined
          ? undefined
          : Number(annotation.selectionEnd ?? annotation.selection_end),
      selectionStart:
        annotation.selectionStart === undefined && annotation.selection_start === undefined
          ? undefined
          : Number(annotation.selectionStart ?? annotation.selection_start),
    }))
    .filter((annotation) => annotation.chapterId && Number.isFinite(annotation.paragraphIndex));
}

function normalizeChapterFile(file, index) {
  const chapterIndex = Number(file.chapterIndex ?? file.chapter_index ?? index + 1) || index + 1;
  const content = file.content || "";
  return {
    id: file.id || `chapter_file_${chapterIndex}_${index}`,
    fileName: file.fileName || file.file_name || `chapter_${chapterIndex}.txt`,
    chapterIndex,
    chapterTitle: file.chapterTitle || file.chapter_title || `第 ${chapterIndex} 章`,
    content,
    sourceType: file.sourceType || file.source_type || "file",
    wordCount: file.wordCount ?? file.word_count ?? countWords(content),
  };
}

function chapterFilesFromChapters(chapters) {
  return chapters.map((chapter, index) => {
    const chapterIndex = chapter.chapterIndex || chapter.chapter_index || index + 1;
    const content = chapter.content || chapter.summary || "";
    return {
      id: `chapter_file_${chapterIndex}`,
      fileName: `chapter_${chapterIndex}.txt`,
      chapterIndex,
      chapterTitle: chapter.title || chapter.heading || `第 ${chapterIndex} 章`,
      content,
      sourceType: "file",
      wordCount: chapter.wordCount ?? chapter.word_count ?? countWords(content),
    };
  });
}

function chaptersToText(chapters = []) {
  return chapters
    .map((chapter) => chapter.content || chapter.summary || "")
    .filter(Boolean)
    .join("\n\n");
}

function normalizeTitle(title, fallbackTitle = "未命名项目") {
  const cleaned = String(title || "").trim();
  return cleaned || fallbackTitle;
}

function countWords(text) {
  return String(text || "").replace(/\s+/g, "").length;
}
