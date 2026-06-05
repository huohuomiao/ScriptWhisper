import { MessageSquareText, Zap } from "lucide-react";
import { useState } from "react";

import { polishScene } from "../src/api.js";

export default function SceneEditor({ scriptYaml, selectedSceneId, onSceneChange, onYamlChange }) {
  const scene = scriptYaml.scenes.find((item) => item.id === selectedSceneId) || scriptYaml.scenes[0];
  const [isBusy, setIsBusy] = useState(false);
  const [pendingChange, setPendingChange] = useState(null);
  const hasDialogue = scriptYaml.script.some((line) => line.scene_id === scene.id && line.type === "dialogue");

  function applyConflictBoost() {
    updateScene("conflict", "强化冲突", (draft) => {
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
    if (!hasDialogue) {
      return;
    }
    updateScene("dialogue", "修改对白", (draft) => {
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

  async function updateScene(action, actionLabel, recipe) {
    setIsBusy(true);
    try {
      const result = await polishScene({ scriptYaml, sceneId: scene.id, action });
      setPendingChange({
        actionLabel,
        afterYaml: result.script_yaml,
        beforeYaml: scriptYaml,
        sceneId: scene.id,
        sceneTitle: scene.title,
      });
    } catch {
      const draft = structuredClone(scriptYaml);
      recipe(draft);
      setPendingChange({
        actionLabel: `${actionLabel}（本地）`,
        afterYaml: draft,
        beforeYaml: scriptYaml,
        sceneId: scene.id,
        sceneTitle: scene.title,
      });
    } finally {
      setIsBusy(false);
    }
  }

  function applyPendingChange() {
    onYamlChange(pendingChange.afterYaml, `${pendingChange.sceneTitle} 已应用：${pendingChange.actionLabel}`);
    setPendingChange(null);
  }

  function discardPendingChange() {
    setPendingChange(null);
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
          <select
            value={scene.id}
            onChange={(event) => {
              setPendingChange(null);
              onSceneChange(event.target.value);
            }}
          >
            {scriptYaml.scenes.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </select>
        </label>

        <div className="editor-actions">
          <button disabled={isBusy} type="button" onClick={applyConflictBoost}>
            <Zap size={16} />
            强化冲突
          </button>
          <button
            disabled={isBusy || !hasDialogue}
            title={hasDialogue ? "改写当前场景对白" : "当前场景没有对白"}
            type="button"
            onClick={applyDialogueRewrite}
          >
            <MessageSquareText size={16} />
            修改对白
          </button>
        </div>
      </div>
      {pendingChange && (
        <SceneDiff
          actionLabel={pendingChange.actionLabel}
          afterYaml={pendingChange.afterYaml}
          beforeYaml={pendingChange.beforeYaml}
          onApply={applyPendingChange}
          onDiscard={discardPendingChange}
          sceneId={pendingChange.sceneId}
        />
      )}
    </section>
  );
}

function SceneDiff({ actionLabel, afterYaml, beforeYaml, onApply, onDiscard, sceneId }) {
  const beforeScene = sceneSnapshot(beforeYaml, sceneId);
  const afterScene = sceneSnapshot(afterYaml, sceneId);

  return (
    <section className="scene-diff" aria-label="润色前后对比">
      <div className="section-heading">
        <span className="heading-icon">
          <MessageSquareText size={18} />
        </span>
        <h2>润色对比：{actionLabel}</h2>
      </div>
      <div className="diff-grid">
        <DiffPanel label="修改前" snapshot={beforeScene} />
        <DiffPanel label="修改后" snapshot={afterScene} />
      </div>
      <div className="diff-actions">
        <button type="button" onClick={onApply}>
          应用修改
        </button>
        <button type="button" onClick={onDiscard}>
          放弃修改
        </button>
      </div>
    </section>
  );
}

function DiffPanel({ label, snapshot }) {
  return (
    <article className="diff-panel">
      <h3>{label}</h3>
      <p>{snapshot.summary}</p>
      <pre>{snapshot.lines.join("\n")}</pre>
    </article>
  );
}

function sceneSnapshot(scriptYaml, sceneId) {
  const scene = scriptYaml.scenes.find((item) => item.id === sceneId);
  const lines = scriptYaml.script
    .filter((line) => line.scene_id === sceneId)
    .map((line) => `${line.type}${line.character_id ? `/${line.character_id}` : ""}: ${line.content}`);

  return {
    summary: scene?.summary || "未填写场景摘要。",
    lines: lines.length ? lines : ["未生成正文。"],
  };
}
