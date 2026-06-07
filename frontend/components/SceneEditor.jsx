import { MessageSquareText, Zap } from "lucide-react";
import { useEffect, useState } from "react";

import { polishScene } from "../src/api.js";

export default function SceneEditor({
  scriptYaml,
  selectedSceneId,
  onSceneChange,
  onYamlChange,
  showSceneSelect = true,
  t = (key) => key,
}) {
  const explicitScene = scriptYaml.scenes.find((item) => item.id === selectedSceneId);
  const scene = explicitScene || (showSceneSelect ? scriptYaml.scenes[0] : null);
  const [isBusy, setIsBusy] = useState(false);
  const [pendingChange, setPendingChange] = useState(null);
  const hasDialogue = scene
    ? scriptYaml.script.some((line) => line.scene_id === scene.id && line.type === "dialogue")
    : false;

  useEffect(() => {
    setPendingChange(null);
  }, [selectedSceneId]);

  if (!scene) {
    return (
      <section className="scene-editor" aria-label={t("sceneEditor.title")}>
        <div className="section-heading">
          <span className="heading-icon">
            <Zap size={18} />
          </span>
          <h2>{t("sceneEditor.title")}</h2>
        </div>
        <p className="empty-state compact">{t("preview.noScenesForChapter")}</p>
      </section>
    );
  }

  function applyConflictBoost() {
    updateScene("conflict", t("sceneEditor.boostConflict"), (draft) => {
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
    updateScene("dialogue", hasDialogue ? t("sceneEditor.rewriteDialogue") : t("sceneEditor.addDialogue"), (draft) => {
      const sceneCharacters = scene.characters || [];
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
    onYamlChange(
      pendingChange.afterYaml,
      t("sceneEditor.appliedStatus", { action: pendingChange.actionLabel, scene: pendingChange.sceneTitle }),
    );
    setPendingChange(null);
  }

  function discardPendingChange() {
    setPendingChange(null);
  }

  return (
    <section className={`scene-editor ${pendingChange ? "has-pending-change" : ""}`} aria-label={t("sceneEditor.title")}>
      <div className="section-heading">
        <span className="heading-icon">
          <Zap size={18} />
        </span>
        <h2>{t("sceneEditor.title")}</h2>
      </div>

      <div className="editor-controls">
        {showSceneSelect ? (
          <label>
            {t("sceneEditor.scene")}
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
        ) : (
          <div className="current-scene-label">
            <span>{t("preview.currentScene")}</span>
            <strong>{scene.title}</strong>
          </div>
        )}

        <div className="editor-actions">
          <button disabled={isBusy} type="button" onClick={applyConflictBoost}>
            <Zap size={16} />
            {t("sceneEditor.boostConflict")}
          </button>
          <button
            disabled={isBusy}
            title={hasDialogue ? t("sceneEditor.rewriteDialogueHint") : t("sceneEditor.addDialogueHint")}
            type="button"
            onClick={applyDialogueRewrite}
          >
            <MessageSquareText size={16} />
            {hasDialogue ? t("sceneEditor.rewriteDialogue") : t("sceneEditor.addDialogue")}
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
          t={t}
        />
      )}
    </section>
  );
}

function SceneDiff({ actionLabel, afterYaml, beforeYaml, onApply, onDiscard, sceneId, t }) {
  const beforeScene = sceneSnapshot(beforeYaml, sceneId);
  const afterScene = sceneSnapshot(afterYaml, sceneId);
  const beforeLineKeys = new Set(beforeScene.lines.map((line) => line.key));

  return (
    <section className="scene-diff" aria-label={t("sceneEditor.previewTitle")}>
      <div className="section-heading">
        <span className="heading-icon">
          <MessageSquareText size={18} />
        </span>
        <h2>{t("sceneEditor.previewTitle")}：{actionLabel}</h2>
      </div>
      <div className="diff-grid">
        <DiffPanel label={t("sceneEditor.before")} snapshot={beforeScene} t={t} />
        <DiffPanel highlightChanges label={t("sceneEditor.after")} snapshot={afterScene} beforeLineKeys={beforeLineKeys} t={t} />
      </div>
      <div className="diff-actions">
        <button type="button" onClick={onApply}>
          {t("sceneEditor.apply")}
        </button>
        <button type="button" onClick={onDiscard}>
          {t("sceneEditor.discard")}
        </button>
      </div>
    </section>
  );
}

function DiffPanel({ beforeLineKeys = new Set(), highlightChanges = false, label, snapshot, t }) {
  return (
    <article className="diff-panel">
      <h3>{label}</h3>
      <p>{snapshot.summary || t("sceneEditor.noSummary")}</p>
      <div className="diff-script-lines">
        {snapshot.lines.length ? (
          snapshot.lines.map((line) => (
            <article
              className={`diff-script-line ${highlightChanges && !beforeLineKeys.has(line.key) ? "added" : ""}`}
              key={line.key}
            >
              <span className="line-type">{t(lineTypeLabel(line.type))}</span>
              <div className="line-body">
                {line.speaker && <strong className="speaker">{line.speaker}</strong>}
                <p>{line.content}</p>
                {line.note && <p className="line-note">{t("preview.editor.note")}：{line.note}</p>}
              </div>
            </article>
          ))
        ) : (
          <p className="empty-state compact">{t("sceneEditor.noScript")}</p>
        )}
      </div>
    </article>
  );
}

function sceneSnapshot(scriptYaml, sceneId) {
  const scene = scriptYaml.scenes.find((item) => item.id === sceneId);
  const lines = scriptYaml.script
    .filter((line) => line.scene_id === sceneId)
    .map((line, index) => {
      const speaker = line.speaker_name || line.speaker_id || line.character_id;
      const content = line.text || line.content || "";
      return {
        key: `${line.type}:${speaker || ""}:${content}:${line.note || ""}:${index}`,
        type: line.type,
        speaker,
        content,
        note: line.note,
      };
    });

  return {
    summary: scene?.summary || "",
    lines,
  };
}

function lineTypeLabel(type) {
  const labels = {
    action: "preview.filter.action",
    camera: "preview.filter.camera",
    dialogue: "preview.filter.dialogue",
    narration: "preview.filter.narration",
    note: "preview.filter.note",
    transition: "preview.filter.transition",
  };
  return labels[type] || type || "preview.filter.action";
}
