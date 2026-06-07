import { useMemo, useState } from "react";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const sampleText =
  "雨停后的长街泛着冷光。林澈握着那封没有署名的信，终于在旧影院门口看见了等候多时的沈微。";

export default function ConversionDemo() {
  const [novelText, setNovelText] = useState(sampleText);
  const [style, setStyle] = useState("短剧剧本");
  const [script, setScript] = useState("");
  const [provider, setProvider] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadedFile, setUploadedFile] = useState("");
  const [error, setError] = useState("");

  const canSubmit = useMemo(
    () => novelText.trim().length > 0 && !loading && !uploading,
    [novelText, loading, uploading],
  );

  async function handleFileUpload(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    setUploading(true);
    setError("");
    setUploadedFile("");

    try {
      if (!file.name.toLowerCase().endsWith(".txt")) {
        throw new Error("请上传 .txt 文件");
      }

      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch(`${apiBaseUrl}/api/upload`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || "上传失败");
      }

      const data = await response.json();
      const sizeKb = Math.max(1, Math.ceil(data.size_bytes / 1024));
      setNovelText(data.content);
      setUploadedFile(`${data.filename} · ${sizeKb} KB`);
      setScript("");
      setProvider("");
    } catch (err) {
      setError(err.message);
    } finally {
      event.target.value = "";
      setUploading(false);
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setScript("");
    setProvider("");

    try {
      const response = await fetch(`${apiBaseUrl}/api/convert`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          novel_text: novelText,
          style,
        }),
      });

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || "转换失败");
      }

      const data = await response.json();
      setScript(data.script);
      setProvider(data.provider);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="workspace" aria-label="小说转剧本工作区">
      <form className="editor-panel" onSubmit={handleSubmit}>
        <div className="panel-heading">
          <h2>小说片段</h2>
          <select value={style} onChange={(event) => setStyle(event.target.value)}>
            <option>短剧剧本</option>
            <option>电影剧本</option>
            <option>分镜脚本</option>
            <option>舞台剧本</option>
          </select>
        </div>

        <div className="upload-row">
          <label className="file-upload">
            <input type="file" accept=".txt,text/plain" onChange={handleFileUpload} disabled={uploading} />
            <span>{uploading ? "上传中..." : "上传 TXT"}</span>
          </label>
          {uploadedFile && <span className="upload-status">已载入 {uploadedFile}</span>}
        </div>

        <textarea
          value={novelText}
          onChange={(event) => setNovelText(event.target.value)}
          placeholder="粘贴小说片段"
          rows={12}
        />

        <div className="actions">
          <button type="button" className="secondary-button" onClick={() => setNovelText(sampleText)}>
            示例文本
          </button>
          <button type="submit" disabled={!canSubmit}>
            {loading ? "转换中..." : "转换为剧本"}
          </button>
        </div>
      </form>

      <section className="result-panel" aria-label="剧本结果">
        <div className="panel-heading">
          <h2>剧本草稿</h2>
          {provider && <span className="provider-tag">{provider === "api" ? "API" : "本地示例"}</span>}
        </div>

        {error && <p className="error-message">{error}</p>}
        {!error && !script && <p className="empty-result">转换结果会显示在这里。</p>}
        {script && <pre>{script}</pre>}
      </section>
    </section>
  );
}
