import { Camera, MessageSquareText, MoveRight, PencilLine } from "lucide-react";
import { useMemo, useState } from "react";

import SceneEditor from "../components/SceneEditor.jsx";
import { scriptYaml } from "../src/sampleData.js";

const lineMeta = {
  action: { label: "动作", icon: PencilLine },
  dialogue: { label: "对白", icon: MessageSquareText },
  note: { label: "镜头", icon: Camera },
  transition: { label: "转场", icon: MoveRight },
};

export default function ScriptPreview() {
  const [yamlData, setYamlData] = useState(scriptYaml);
  const [selectedSceneId, setSelectedSceneId] = useState(scriptYaml.scenes[0]?.id);
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
        {character && <strong>{character.name}</strong>}
        <p>{line.content}</p>
      </div>
    </div>
  );
}
