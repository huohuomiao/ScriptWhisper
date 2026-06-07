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
    api_protocol: str = "openai"
    max_tokens: int = 4096
    request_timeout: float = 120.0

    @classmethod
    def from_env(cls, env_path: str | Path = DEFAULT_ENV_PATH) -> "LLMSettings":
        values = _load_env_file(Path(env_path))
        api_key = os.getenv("AI_API_KEY") or values.get("AI_API_KEY")
        api_base_url = os.getenv("AI_API_BASE_URL") or values.get("AI_API_BASE_URL")
        model = os.getenv("AI_MODEL") or values.get("AI_MODEL")
        api_protocol = _normalize_api_protocol(
            os.getenv("AI_API_PROTOCOL") or values.get("AI_API_PROTOCOL") or _infer_api_protocol(api_base_url)
        )
        max_tokens = _parse_int(os.getenv("AI_MAX_TOKENS") or values.get("AI_MAX_TOKENS"), default=4096)
        request_timeout = _parse_float(
            os.getenv("AI_REQUEST_TIMEOUT_SECONDS") or values.get("AI_REQUEST_TIMEOUT_SECONDS"),
            default=120.0,
        )
        mock_value = os.getenv("AI_MOCK_MODE") or values.get("AI_MOCK_MODE", "")
        explicit_mock = mock_value.lower() in {"1", "true", "yes", "on"}
        missing_config = not api_key or not api_base_url or not model
        return cls(
            api_key=api_key,
            api_base_url=api_base_url,
            model=model,
            mock_mode=explicit_mock or missing_config,
            api_protocol=api_protocol,
            max_tokens=max_tokens,
            request_timeout=request_timeout,
        )


class LLMClient:
    def __init__(self, settings: LLMSettings | None = None, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings or LLMSettings.from_env()
        self._transport = transport

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

        if _normalize_api_protocol(self.settings.api_protocol) == "anthropic":
            return await self._chat_anthropic_async(messages, temperature)
        return await self._chat_openai_async(messages, temperature)

    async def _chat_openai_async(self, messages: list[dict[str, str]], temperature: float) -> str:
        endpoint = self.settings.api_base_url.rstrip("/") + "/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout, transport=self._transport) as client:
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
                        "max_tokens": self.settings.max_tokens,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            error_detail = _parse_api_error(exc.response)
            raise LLMClientError(error_detail) from exc
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise LLMClientError(
                "LLM API request timed out after "
                f"{_format_seconds(self.settings.request_timeout)}s. "
                "Increase AI_REQUEST_TIMEOUT_SECONDS or shorten the input."
            ) from exc
        except httpx.RequestError as exc:
            detail = str(exc).strip()
            message = f"LLM API request failed: {detail}" if detail else (
                "LLM API request failed. Check network connectivity and AI_API_BASE_URL."
            )
            raise LLMClientError(message) from exc
        except json.JSONDecodeError as exc:
            raise LLMClientError("LLM API returned invalid JSON.") from exc

        try:
            return payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError("LLM API returned an unexpected response format.") from exc

    async def _chat_anthropic_async(self, messages: list[dict[str, str]], temperature: float) -> str:
        endpoint = self.settings.api_base_url.rstrip("/") + "/v1/messages"
        system_prompt, anthropic_messages = _to_anthropic_messages(messages)
        body: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": self.settings.max_tokens,
            "messages": anthropic_messages,
            "temperature": temperature,
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout, transport=self._transport) as client:
                response = await client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self.settings.api_key}",
                        "x-api-key": self.settings.api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            error_detail = _parse_api_error(exc.response)
            raise LLMClientError(error_detail) from exc
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise LLMClientError(
                "LLM API request timed out after "
                f"{_format_seconds(self.settings.request_timeout)}s. "
                "Increase AI_REQUEST_TIMEOUT_SECONDS or shorten the input."
            ) from exc
        except httpx.RequestError as exc:
            detail = str(exc).strip()
            message = f"LLM API request failed: {detail}" if detail else (
                "LLM API request failed. Check network connectivity and AI_API_BASE_URL."
            )
            raise LLMClientError(message) from exc
        except json.JSONDecodeError as exc:
            raise LLMClientError("LLM API returned invalid JSON.") from exc

        content = _extract_anthropic_text(payload)
        if content:
            return content.strip()
        raise LLMClientError("LLM API returned an unexpected response format.")

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
        key = key.strip().lstrip("\ufeff")
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


def _normalize_api_protocol(value: str | None) -> str:
    protocol = (value or "openai").strip().lower()
    if protocol in {"anthropic", "claude"}:
        return "anthropic"
    return "openai"


def _infer_api_protocol(api_base_url: str | None) -> str:
    if api_base_url and "anthropic" in api_base_url.lower():
        return "anthropic"
    return "openai"


def _parse_int(value: str | None, *, default: int) -> int:
    try:
        parsed = int(str(value).strip()) if value else default
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _parse_float(value: str | None, *, default: float) -> float:
    try:
        parsed = float(str(value).strip()) if value else default
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _format_seconds(value: float) -> str:
    return f"{value:g}"


def _to_anthropic_messages(messages: list[dict[str, str]]) -> tuple[str | None, list[dict[str, str]]]:
    system_parts: list[str] = []
    converted: list[dict[str, str]] = []

    for message in messages:
        role = message.get("role", "user")
        content = str(message.get("content", "")).strip()
        if not content:
            continue
        if role == "system":
            system_parts.append(content)
            continue

        converted_role = "assistant" if role == "assistant" else "user"
        if converted and converted[-1]["role"] == converted_role:
            converted[-1]["content"] = f"{converted[-1]['content']}\n\n{content}"
        else:
            converted.append({"role": converted_role, "content": content})

    if not converted:
        converted.append({"role": "user", "content": ""})

    system_prompt = "\n\n".join(system_parts) if system_parts else None
    return system_prompt, converted


def _extract_anthropic_text(payload: dict[str, Any]) -> str | None:
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for block in content:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts) if parts else None


_API_ERROR_MESSAGES = {
    "insufficient_balance": "AI 服务账户余额不足，请充值后重试。",
    "invalid_api_key": "AI 服务 API Key 无效，请检查 .env 配置。",
    "model_not_found": "AI 模型名称无效，请检查 .env 中的 AI_MODEL 配置。",
    "rate_limit_exceeded": "AI 服务请求频率超限，请稍后重试。",
    "invalid_authentication": "AI 服务认证失败，请检查 .env 中的 AI_API_KEY。",
}


def _parse_api_error(response: httpx.Response) -> str:
    try:
        body = response.json()
        error_obj = body.get("error", {})
        error_type = error_obj.get("type", "")
        error_message = error_obj.get("message", "")
        error_code = str(error_obj.get("code", response.status_code))

        friendly = _API_ERROR_MESSAGES.get(error_type)
        if friendly:
            return friendly
        if error_message:
            return f"AI 服务返回错误 ({error_code}): {error_message}"
    except (json.JSONDecodeError, AttributeError):
        pass
    return f"AI 服务请求失败，状态码 {response.status_code}。"
