import { BadgeCheck, BookMarked, FileText, MapPin, ScrollText, UsersRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import ReadingToolbar from "../components/ReadingToolbar.jsx";
import { readingClassName, useReadingSettings } from "../src/readingSettings.js";
import { chapters as sampleChapters, scriptYaml as sampleScriptYaml } from "../src/sampleData.js";

export default function Analysis({
  chapters = sampleChapters,
  issues = [],
  mockMode = true,
  repaired = false,
  scriptYaml = sampleScriptYaml,
}) {
  const normalizedChapters = useMemo(() => chapters.map(normalizeChapter), [chapters]);
  const totalWords = normalizedChapters.reduce((sum, chapter) => sum + chapter.wordCount, 0);
  const bible = buildStoryBible(scriptYaml);
  const { settings, setFontSize, setHighlightColor, setLineHeight } = useReadingSettings();
  const [selectedChapterId, setSelectedChapterId] = useState(normalizedChapters[0]?.id || "");
  const selectedChapter = normalizedChapters.find((chapter) => chapter.id === selectedChapterId) || normalizedChapters[0];
  const selectedSceneCount = selectedChapter ? sceneCountForChapter(scriptYaml.scenes, selectedChapter.id) : 0;

  useEffect(() => {
    if (!normalizedChapters.some((chapter) => chapter.id === selectedChapterId)) {
      setSelectedChapterId(normalizedChapters[0]?.id || "");
    }
  }, [normalizedChapters, selectedChapterId]);

  return (
    <section className="workspace analysis-workspace">
      <section className="page-intro-panel">
        <div>
          <p className="eyebrow">Analysis Result</p>
          <h2>内容结构已拆解为可追踪的创作资产</h2>
          <p>从原文证据出发，集中查看章节、人物、地点和 Story Bible，便于继续进入剧本预览工作台。</p>
        </div>
        <div className="intro-status-row" aria-label="分析状态">
          <span className="status-chip">
            <BadgeCheck size={14} />
            {mockMode ? "Mock Mode" : "AI API Mode"}
          </span>
          <span className="status-chip">
            <BadgeCheck size={14} />
            {repaired ? "Auto Repaired" : "Schema Validated"}
          </span>
          {issues.length > 0 && <span className="status-chip warning">{issues.length} fixes</span>}
        </div>
      </section>

      <div className="metric-grid metric-grid-five" aria-label="分析摘要">
        <Metric label="Chapters" value={normalizedChapters.length} />
        <Metric label="Characters" value={scriptYaml.characters.length} />
        <Metric label="Locations" value={scriptYaml.locations.length} />
        <Metric label="Scenes" value={scriptYaml.scenes.length} />
        <Metric label="Word Count" value={totalWords.toLocaleString("zh-CN")} />
      </div>

      <ReadingToolbar
        settings={settings}
        onClearHighlight={() => setHighlightColor("yellow")}
        onFontSizeChange={setFontSize}
        onHighlightColorChange={setHighlightColor}
        onLineHeightChange={setLineHeight}
      />

      <div className="analysis-grid">
        <aside className="analysis-sidebar panel" aria-label="章节列表">
          <SectionHeading icon={<ScrollText size={17} />} title="Chapter List" />
          <div className="chapter-list compact-list">
            {normalizedChapters.map((chapter, index) => {
              const chapterSceneCount = sceneCountForChapter(scriptYaml.scenes, chapter.id);
              return (
                <button
                  className={`chapter-row ${chapter.id === selectedChapter?.id ? "selected" : ""}`}
                  key={chapter.id}
                  type="button"
                  onClick={() => setSelectedChapterId(chapter.id)}
                >
                  <span className="row-index">{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <h2>{chapter.title}</h2>
                    <p>{chapter.summary || "暂无摘要"}</p>
                  </div>
                  <div className="row-meta">
                    <span>{chapter.wordCount.toLocaleString("zh-CN")} 字</span>
                    <span>{chapterSceneCount} 场景</span>
                    <span>{chapter.status}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        <section className="analysis-reader panel" aria-label="章节原文">
          <div className="reader-header">
            <div>
              <p className="eyebrow">Source Evidence</p>
              <h2>{selectedChapter?.title || "暂无章节"}</h2>
              <p>
                {selectedChapter?.wordCount.toLocaleString("zh-CN") || 0} 字 · {selectedSceneCount} 个生成场景
              </p>
            </div>
            <FileText size={20} />
          </div>
          <div className={`chapter-source-text ${readingClassName(settings)}`}>
            {selectedChapter?.content || selectedChapter?.summary || "暂无章节原文。"}
          </div>
        </section>

        <aside className="analysis-inspector">
          <section className="panel inspector-section">
            <SectionHeading icon={<BookMarked size={17} />} title="Story Bible" />
            <div className="bible-grid">
              <BibleItem label="故事类型" value={bible.storyType} />
              <BibleItem label="主线冲突" value={bible.mainConflict} />
              <BibleItem label="核心悬念" value={bible.centralMystery} />
              <BibleItem label="改编建议" value={bible.adaptationAdvice} />
            </div>
          </section>

          <section className="panel inspector-section">
            <SectionHeading icon={<UsersRound size={17} />} title="Characters" />
            <div className="entity-list">
              {scriptYaml.characters.map((character, index) => (
                <EntityCard
                  key={character.id || character.name}
                  badge={initialFor(character.name, index)}
                  title={character.name}
                  subtitle={character.role || "待定角色"}
                  meta={character.personality || inferCharacterTrait(character, index)}
                  detail={character.motivation || inferMotivation(character)}
                />
              ))}
            </div>
          </section>

          <section className="panel inspector-section">
            <SectionHeading icon={<MapPin size={17} />} title="Locations" />
            <div className="entity-list">
              {scriptYaml.locations.map((location, index) => (
                <EntityCard
                  key={location.id || location.name}
                  badge={initialFor(location.name, index)}
                  title={location.name}
                  subtitle={location.atmosphere || inferLocationAtmosphere(location)}
                  meta={location.description || "待补充"}
                  detail={location.plot_use || location.plotUse || inferLocationUse(location)}
                />
              ))}
            </div>
          </section>
        </aside>
      </div>
    </section>
  );
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

function sceneCountForChapter(scenes, chapterId) {
  return scenes.filter((scene) => getSceneChapterId(scene) === chapterId).length;
}

function buildStoryBible(scriptYaml) {
  const project = scriptYaml.project || {};
  const bible = project.bible || {};
  const firstScene = scriptYaml.scenes[0];
  const sceneTitles = scriptYaml.scenes.map((scene) => scene.title).join("、");

  return {
    storyType: bible.story_type || bible.storyType || project.genre || "待定类型",
    mainConflict:
      bible.main_conflict ||
      bible.mainConflict ||
      project.logline ||
      `${project.title || "故事"}围绕人物目标与隐藏真相展开。`,
    centralMystery:
      bible.central_mystery ||
      bible.centralMystery ||
      (firstScene ? `${firstScene.title}背后的真实原因尚未揭开。` : "核心悬念待补充。"),
    adaptationAdvice:
      bible.adaptation_advice ||
      bible.adaptationAdvice ||
      `建议围绕${sceneTitles || "关键场景"}强化视觉意象和场景目标。`,
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
