from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


class LLMClientError(RuntimeError):
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

        return await self._chat_async(messages, temperature)

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

    async def _chat_async(self, messages: list[dict[str, str]], temperature: float) -> str:
        if not self.settings.api_key or not self.settings.api_base_url or not self.settings.model:
            raise LLMClientError("AI_API_KEY, AI_API_BASE_URL and AI_MODEL are required outside mock mode.")

        endpoint = self.settings.api_base_url.rstrip("/") + "/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self.settings.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.settings.model,
                        "messages": messages,
                        "temperature": temperature,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise LLMClientError(f"LLM API request failed: {exc.response.status_code} {exc.response.text}") from exc
        except (httpx.RequestError, TimeoutError) as exc:
            raise LLMClientError(f"LLM API request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LLMClientError("LLM API returned invalid JSON.") from exc

        try:
            return payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError("LLM API returned an unexpected response format.") from exc

    def _default_mock_response(self, messages: list[dict[str, str]]) -> str:
        user_text = next((message["content"] for message in reversed(messages) if message.get("role") == "user"), "")
        preview = user_text.strip().replace("\n", " ")[:120]
        return f"MOCK_RESPONSE: {preview}"


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
