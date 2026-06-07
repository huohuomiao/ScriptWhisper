import httpx

from backend.app.config import Settings
from backend.schemas.conversion import ConvertRequest, ConvertResponse


class AIClientError(RuntimeError):
    pass


class AIClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def convert_to_script(self, payload: ConvertRequest) -> ConvertResponse:
        if not self.settings.ai_api_key or not self.settings.ai_api_base_url:
            return ConvertResponse(script=self._mock_script(payload.novel_text), provider="mock")

        model = payload.model or self.settings.ai_model
        if not model:
            raise AIClientError("AI_MODEL is required when API mode is enabled.")

        response_text = await self._call_chat_completions(payload, model)
        return ConvertResponse(script=response_text, provider="api")

    async def _call_chat_completions(self, payload: ConvertRequest, model: str) -> str:
        endpoint = self.settings.ai_api_base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.ai_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "messages": [
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
            ],
            "temperature": 0.7,
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(endpoint, headers=headers, json=body)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AIClientError(f"AI API request failed: {exc}") from exc

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise AIClientError("AI API returned an unexpected response format.") from exc

    def _mock_script(self, novel_text: str) -> str:
        excerpt = novel_text.strip().replace("\n", " ")[:120]
        return (
            "场景一  内景  深夜\n\n"
            "昏黄的灯光落在桌面上。主角停下脚步，望向窗外。\n\n"
            f"旁白：{excerpt}\n\n"
            "主角：这一刻，我知道故事必须换一种方式讲出来。\n\n"
            "镜头缓慢推近，房间里只剩下呼吸声和纸页翻动的声音。"
        )
