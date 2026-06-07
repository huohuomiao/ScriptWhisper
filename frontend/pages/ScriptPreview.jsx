import { Camera, MessageSquareText, MoveRight, PencilLine } from "lucide-react";

import { scriptYaml } from "../src/sampleData.js";

const lineMeta = {
  action: { label: "动作", icon: PencilLine },
  dialogue: { label: "对白", icon: MessageSquareText },
  note: { label: "镜头", icon: Camera },
  transition: { label: "转场", icon: MoveRight },
};

export default function ScriptPreview() {
  const characterById = new Map(scriptYaml.characters.map((character) => [character.id, character]));
  const locationById = new Map(scriptYaml.locations.map((location) => [location.id, location]));

  return (
    <section className="workspace">
      <div className="preview-grid">
        {scriptYaml.scenes.map((scene, index) => {
          const lines = scriptYaml.script.filter((line) => line.scene_id === scene.id);
          const location = locationById.get(scene.location_id);
          const characters = scene.characters.map((id) => characterById.get(id)).filter(Boolean);

          return (
            <article className="scene-card" key={scene.id}>
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
