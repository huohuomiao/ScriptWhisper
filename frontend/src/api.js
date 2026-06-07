const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";


export async function uploadNovelFile(file) {
  const form = new FormData();
  form.append("file", file);
  return requestJson("/api/upload", {
    method: "POST",
    body: form,
  });
}


export async function convertNovel({ text, title, source, mock, targetLanguage = "zh", onProgress }) {
  if (onProgress) {
    return requestNdjson("/api/convert/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, title, source, mock, target_language: targetLanguage }),
      onProgress,
    });
  }

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


async function requestNdjson(path, { onProgress, ...options }) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `Request failed: ${response.status}`);
  }
  if (!response.body) {
    throw new Error("Streaming response is not available in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalData = null;

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        continue;
      }
      const event = JSON.parse(trimmed);
      if (event.type === "error") {
        throw new Error(event.message || event.error_code || "Streaming conversion failed.");
      }
      if (event.type === "complete") {
        finalData = event.data;
      } else {
        onProgress(event);
      }
    }

    if (done) {
      break;
    }
  }

  if (buffer.trim()) {
    const event = JSON.parse(buffer.trim());
    if (event.type === "complete") {
      finalData = event.data;
    } else if (event.type === "error") {
      throw new Error(event.message || event.error_code || "Streaming conversion failed.");
    } else {
      onProgress(event);
    }
  }

  if (!finalData) {
    throw new Error("Streaming conversion finished without a final result.");
  }
  return finalData;
}
