from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request

from backend.schemas.conversion import ConvertRequest, ConvertResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


class LLMClientError(RuntimeError):
    pass


class AIClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMSettings:
    api_key: str | None
    api_base_url: str | None
    model: str | None
    mock_mode: bool = False

    @classmethod
    def from_env(cls, env_path: str | Path = DEFAULT_ENV_PATH) -> "LLMSettings":
        values = _load_env_file(Path(env_path))
        api_key = os.getenv("AI_API_KEY") or values.get("AI_API_KEY")
        api_base_url = os.getenv("AI_API_BASE_URL") or values.get("AI_API_BASE_URL")
        model = os.getenv("AI_MODEL") or values.get("AI_MODEL")
        mock_value = os.getenv("AI_MOCK_MODE") or values.get("AI_MOCK_MODE", "")
        explicit_mock = mock_value.lower() in {"1", "true", "yes", "on"}
        missing_config = not api_key or not api_base_url or not model
        return cls(api_key=api_key, api_base_url=api_base_url, model=model, mock_mode=explicit_mock or missing_config)


class LLMClient:
    def __init__(self, settings: LLMSettings | None = None):
        self.settings = settings or LLMSettings.from_env()

    @property
    def mock_mode(self) -> bool:
        return self.settings.mock_mode

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        mock_response: str | None = None,
    ) -> str:
        if self.mock_mode:
            return mock_response or self._default_mock_response(messages)

        return await asyncio.to_thread(self._chat_sync, messages, temperature)

    async def json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        mock_response: dict[str, Any] | list[Any] | None = None,
    ) -> dict[str, Any] | list[Any]:
        if self.mock_mode:
            return mock_response or {}

        content = await self.chat(messages, temperature=temperature)
        try:
            return json.loads(_extract_json_text(content))
        except json.JSONDecodeError as exc:
            raise LLMClientError("LLM response is not valid JSON.") from exc

    def _chat_sync(self, messages: list[dict[str, str]], temperature: float) -> str:
        if not self.settings.api_key or not self.settings.api_base_url or not self.settings.model:
            raise LLMClientError("AI_API_KEY, AI_API_BASE_URL and AI_MODEL are required outside mock mode.")

        endpoint = self.settings.api_base_url.rstrip("/") + "/chat/completions"
        body = json.dumps(
            {
                "model": self.settings.model,
                "messages": messages,
                "temperature": temperature,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMClientError(f"LLM API request failed: {exc.code} {detail}") from exc
        except (error.URLError, TimeoutError) as exc:
            raise LLMClientError(f"LLM API request failed: {exc}") from exc

        try:
            return payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError("LLM API returned an unexpected response format.") from exc

    def _default_mock_response(self, messages: list[dict[str, str]]) -> str:
        user_text = next((message["content"] for message in reversed(messages) if message.get("role") == "user"), "")
        preview = user_text.strip().replace("\n", " ")[:120]
        return f"MOCK_RESPONSE: {preview}"


class AIClient:
    def __init__(self, settings: Any):
        self.settings = settings

    async def convert_to_script(self, payload: ConvertRequest) -> ConvertResponse:
        has_api_config = bool(self.settings.ai_api_key and self.settings.ai_api_base_url)
        model = payload.model or self.settings.ai_model
        if has_api_config and not model:
            raise AIClientError("AI_MODEL is required when API mode is enabled.")

        client = LLMClient(
            LLMSettings(
                api_key=self.settings.ai_api_key,
                api_base_url=self.settings.ai_api_base_url,
                model=model,
                mock_mode=not has_api_config,
            )
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是专业影视编剧。请把小说片段改写为中文剧本，"
                    "保留关键剧情、人物动机和场景氛围，输出清晰的场景、动作和对白。"
                ),
            },
            {
                "role": "user",
                "content": f"目标风格：{payload.style}\n\n小说片段：\n{payload.novel_text}",
            },
        ]

        try:
            script = await client.chat(messages, temperature=0.7, mock_response=self._mock_script(payload.novel_text))
        except LLMClientError as exc:
            raise AIClientError(str(exc)) from exc

        return ConvertResponse(script=script, provider="mock" if client.mock_mode else "api")

    def _mock_script(self, novel_text: str) -> str:
        excerpt = novel_text.strip().replace("\n", " ")[:120]
        return (
            "场景一  内景  深夜\n\n"
            "昏黄的灯光落在桌面上。主角停下脚步，望向窗外。\n\n"
            f"旁白：{excerpt}\n\n"
            "主角：这一刻，我知道故事必须换一种方式讲出来。\n\n"
            "镜头缓慢推近，房间里只剩下呼吸声和纸页翻动的声音。"
        )


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value

    return values


def _extract_json_text(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```").strip()
        stripped = stripped.removesuffix("```").strip()
    return stripped
