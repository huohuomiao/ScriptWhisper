const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";


export async function uploadNovelFile(file) {
  const form = new FormData();
  form.append("file", file);
  return requestJson("/api/upload", {
    method: "POST",
    body: form,
  });
}


export async function convertNovel({ text, title, source, mock, targetLanguage = "zh" }) {
  return requestJson("/api/convert", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, title, source, mock, target_language: targetLanguage }),
  });
}


export async function polishScene({ scriptYaml, sceneId, action }) {
  return requestJson("/api/scenes/polish", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      script_yaml: scriptYaml,
      scene_id: sceneId,
      action,
    }),
  });
}


async function requestJson(path, options) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  const payload = await response.json().catch(() => ({}));
  if (typeof payload.success === "boolean") {
    if (!payload.success) {
      throw new Error(payload.message || payload.error_code || `Request failed: ${response.status}`);
    }
    return payload.data;
  }
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed: ${response.status}`);
  }
  return payload;
}
