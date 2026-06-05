import { Camera, MessageSquareText, MoveRight, PencilLine } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import SceneEditor from "../components/SceneEditor.jsx";
import { scriptYaml as sampleScriptYaml } from "../src/sampleData.js";

const lineMeta = {
  action: { label: "动作", icon: PencilLine },
  dialogue: { label: "对白", icon: MessageSquareText },
  note: { label: "镜头", icon: Camera },
  transition: { label: "转场", icon: MoveRight },
};

export default function ScriptPreview({ scriptYaml = sampleScriptYaml, onScriptYamlChange }) {
  const [yamlData, setYamlData] = useState(scriptYaml);
  const [selectedSceneId, setSelectedSceneId] = useState(scriptYaml.scenes[0]?.id);

  useEffect(() => {
    setYamlData(scriptYaml);
    setSelectedSceneId(scriptYaml.scenes[0]?.id);
  }, [scriptYaml]);
  const [status, setStatus] = useState("");
  const characterById = useMemo(
    () => new Map(yamlData.characters.map((character) => [character.id, character])),
    [yamlData.characters],
  );
  const locationById = useMemo(
    () => new Map(yamlData.locations.map((location) => [location.id, location])),
    [yamlData.locations],
  );

  function handleYamlChange(nextYaml, message) {
    setYamlData(nextYaml);
    onScriptYamlChange?.(nextYaml);
    setStatus(message);
  }

  return (
    <section className="workspace">
      <SceneEditor
        onSceneChange={setSelectedSceneId}
        onYamlChange={handleYamlChange}
        scriptYaml={yamlData}
        selectedSceneId={selectedSceneId}
      />
      {status && <p className="editor-status">{status}</p>}

      <div className="preview-grid">
        {yamlData.scenes.map((scene, index) => {
          const lines = yamlData.script.filter((line) => line.scene_id === scene.id);
          const location = locationById.get(scene.location_id);
          const characters = scene.characters.map((id) => characterById.get(id)).filter(Boolean);

          return (
            <article className={`scene-card ${scene.id === selectedSceneId ? "selected" : ""}`} key={scene.id}>
              <header className="scene-header">
                <span className="scene-number">S{index + 1}</span>
                <div>
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
                  <dd>{characters.map((character) => character.name).join(" / ")}</dd>
                </div>
              </dl>
              <SourceRef scene={scene} fallbackChapter={index + 1} />
              <BeatGrid beats={scene.beats} summary={scene.summary} />

              <div className="script-lines">
                {lines.map((line, lineIndex) => (
                  <ScriptLine
                    character={line.character_id ? characterById.get(line.character_id) : null}
                    key={`${scene.id}-${lineIndex}`}
                    line={line}
                  />
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function SourceRef({ scene, fallbackChapter }) {
  const source = scene.source_ref || {};
  return (
    <section className="source-ref">
      <h3>来源依据</h3>
      <p>
        <strong>{source.chapter_title || source.chapterTitle || `第 ${fallbackChapter} 章`}</strong>
        <span>{source.evidence || source.text || scene.summary || "暂无原文依据。"}</span>
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

function ScriptLine({ line, character }) {
  const meta = lineMeta[line.type] || lineMeta.action;
  const Icon = meta.icon;

  return (
    <div className={`script-line ${line.type}`}>
      <span className="line-type">
        <Icon size={15} />
        {meta.label}
      </span>
      <div className="line-body">
        {character && <strong className="speaker">{character.name}</strong>}
        <p>{line.content}</p>
      </div>
    </div>
  );
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
