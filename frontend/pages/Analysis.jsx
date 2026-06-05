import { BookMarked, FileText, MapPin, UsersRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import ReadingToolbar from "../components/ReadingToolbar.jsx";
import { readingClassName, useReadingSettings } from "../src/readingSettings.js";
import { chapters as sampleChapters, scriptYaml as sampleScriptYaml } from "../src/sampleData.js";

export default function Analysis({ chapters = sampleChapters, issues = [], mockMode = true, repaired = false, scriptYaml = sampleScriptYaml }) {
  const normalizedChapters = useMemo(() => chapters.map(normalizeChapter), [chapters]);
  const totalWords = normalizedChapters.reduce((sum, chapter) => sum + chapter.wordCount, 0);
  const bible = buildStoryBible(scriptYaml);
  const { settings, setFontSize, setHighlightColor, setLineHeight } = useReadingSettings();
  const [selectedChapterId, setSelectedChapterId] = useState(normalizedChapters[0]?.id || "");
  const selectedChapter = normalizedChapters.find((chapter) => chapter.id === selectedChapterId) || normalizedChapters[0];
  const selectedSceneCount = selectedChapter
    ? scriptYaml.scenes.filter((scene) => getSceneChapterId(scene) === selectedChapter.id).length
    : 0;

  useEffect(() => {
    if (!normalizedChapters.some((chapter) => chapter.id === selectedChapterId)) {
      setSelectedChapterId(normalizedChapters[0]?.id || "");
    }
  }, [normalizedChapters, selectedChapterId]);

  return (
    <section className="workspace">
      <div className="metric-grid metric-grid-five" aria-label="分析摘要">
        <Metric label="原文字数" value={totalWords.toLocaleString("zh-CN")} />
        <Metric label="识别章节" value={normalizedChapters.length} />
        <Metric label="人物数量" value={scriptYaml.characters.length} />
        <Metric label="地点数量" value={scriptYaml.locations.length} />
        <Metric label="生成场景" value={scriptYaml.scenes.length} />
      </div>
      <p className="analysis-status">
        {mockMode ? "mock 模式" : "AI API 模式"} · {repaired ? "已自动修复" : "Schema 已校验"}
        {issues.length ? ` · ${issues.length} 个修复记录` : ""}
      </p>
      <ReadingToolbar
        settings={settings}
        onClearHighlight={() => setHighlightColor("yellow")}
        onFontSizeChange={setFontSize}
        onHighlightColorChange={setHighlightColor}
        onLineHeightChange={setLineHeight}
      />

      <section className="section-block">
        <SectionHeading icon={<BookMarked size={18} />} title="故事 Bible" />
        <div className="bible-grid">
          <BibleItem label="故事类型" value={bible.storyType} />
          <BibleItem label="主线冲突" value={bible.mainConflict} />
          <BibleItem label="核心悬念" value={bible.centralMystery} />
          <BibleItem label="改编建议" value={bible.adaptationAdvice} />
        </div>
      </section>

      <section className="section-block">
        <SectionHeading icon={<FileText size={18} />} title="章节列表" />
        <div className="chapter-list">
          {normalizedChapters.map((chapter, index) => (
            <button
              className={`chapter-row ${chapter.id === selectedChapter?.id ? "selected" : ""}`}
              key={chapter.id}
              type="button"
              onClick={() => setSelectedChapterId(chapter.id)}
            >
              <span className="row-index">{index + 1}</span>
              <div>
                <h2>{chapter.title}</h2>
                <p>{chapter.summary}</p>
              </div>
              <div className="row-meta">
                <span>{chapter.wordCount.toLocaleString("zh-CN")} 字</span>
                <span>{chapter.status}</span>
              </div>
            </button>
          ))}
        </div>
        {selectedChapter && (
          <article className="chapter-source-card">
            <div className="section-heading">
              <span className="heading-icon">
                <FileText size={18} />
              </span>
              <h2>章节原文</h2>
            </div>
            <div className="chapter-source-meta">
              <strong>{selectedChapter.title}</strong>
              <span>{selectedChapter.wordCount.toLocaleString("zh-CN")} 字</span>
              <span>{selectedSceneCount} 个场景</span>
            </div>
            <div className={`chapter-source-text ${readingClassName(settings)}`}>
              {selectedChapter.content || selectedChapter.summary || "暂无章节原文。"}
            </div>
          </article>
        )}
      </section>

      <div className="split-grid">
        <section className="section-block">
          <SectionHeading icon={<UsersRound size={18} />} title="人物表" />
          <DataTable
            columns={["姓名", "定位", "性格", "动机", "说话风格", "首次出现章节"]}
            rows={scriptYaml.characters.map((character, index) => [
              character.name,
              character.role || "待定",
              character.personality || inferCharacterTrait(character, index),
              character.motivation || inferMotivation(character),
              character.speech_style || character.speechStyle || inferSpeechStyle(character),
              character.first_chapter || character.firstChapter || firstChapterTitle(chapters),
            ])}
          />
        </section>

        <section className="section-block">
          <SectionHeading icon={<MapPin size={18} />} title="地点表" />
          <DataTable
            columns={["地点", "描述", "氛围", "剧情用途"]}
            rows={scriptYaml.locations.map((location) => [
              location.name,
              location.description || "待补充",
              location.atmosphere || inferLocationAtmosphere(location),
              location.plot_use || location.plotUse || inferLocationUse(location),
            ])}
          />
        </section>
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

function firstChapterTitle(chapters) {
  return chapters[0]?.title || "第一章";
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

function inferSpeechStyle(character) {
  if (character.description?.includes("回避")) {
    return "短句、停顿、含蓄表达";
  }
  if (character.description?.includes("推动")) {
    return "平静、直接、带压力";
  }
  return "待根据对白样本细化";
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

function SectionHeading({ icon, title }) {
  return (
    <div className="section-heading">
      <span className="heading-icon">{icon}</span>
      <h2>{title}</h2>
    </div>
  );
}

function DataTable({ columns, rows }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.join("-")}>
              {row.map((cell, index) => (
                <td key={`${cell}-${index}`}>{cell || "待补充"}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
