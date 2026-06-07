import { MessageSquareText, Zap } from "lucide-react";

export default function SceneEditor({ scriptYaml, selectedSceneId, onSceneChange, onYamlChange }) {
  const scene = scriptYaml.scenes.find((item) => item.id === selectedSceneId) || scriptYaml.scenes[0];

  function applyConflictBoost() {
    updateScene("强化冲突", (draft) => {
      const targetScene = draft.scenes.find((item) => item.id === scene.id);
      targetScene.summary = `${targetScene.summary || targetScene.title} 双方目标更明确，场面压力升级。`;
      draft.script.push({
        scene_id: scene.id,
        type: "note",
        content: "镜头提示：压低环境声，保留人物呼吸和停顿，强化对峙感。",
      });
      draft.script.push({
        scene_id: scene.id,
        type: "action",
        content: "两人之间的距离没有变化，但每一句话都像在逼近对方的底线。",
      });
    });
  }

  function applyDialogueRewrite() {
    updateScene("修改对白", (draft) => {
      const sceneCharacters = scene.characters;
      const fallbackCharacterId = sceneCharacters[0] || draft.characters[0]?.id;
      const dialogue = draft.script.find((line) => line.scene_id === scene.id && line.type === "dialogue");

      if (dialogue) {
        dialogue.content = `${dialogue.content} 但这次，我不会再替你沉默。`;
        return;
      }

      draft.script.push({
        scene_id: scene.id,
        type: "dialogue",
        character_id: fallbackCharacterId,
        content: "你以为我只是在等你，其实我是在等一个答案。",
      });
    });
  }

  function updateScene(actionLabel, recipe) {
    const draft = structuredClone(scriptYaml);
    recipe(draft);
    onYamlChange(draft, `${scene.title} 已执行：${actionLabel}`);
  }

  return (
    <section className="scene-editor" aria-label="单场景润色">
      <div className="section-heading">
        <span className="heading-icon">
          <Zap size={18} />
        </span>
        <h2>单场景润色</h2>
      </div>

      <div className="editor-controls">
        <label>
          场景
          <select value={scene.id} onChange={(event) => onSceneChange(event.target.value)}>
            {scriptYaml.scenes.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>

        <div className="editor-actions">
          <button type="button" onClick={applyConflictBoost}>
            <Zap size={16} />
            强化冲突
          </button>
          <button type="button" onClick={applyDialogueRewrite}>
            <MessageSquareText size={16} />
            修改对白
          </button>
        </div>
      </div>
    </section>
  );
}
