"""Gemini 호출 래퍼. 에이전트는 이 인터페이스(research, generate_json)만 쓴다."""

import asyncio
import json
import mimetypes
from pathlib import Path
from typing import Protocol, Sequence

from .config import Settings


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    model: str

    async def research(
        self, *, agent: str, system: str, prompt: str, attachments: Sequence[Path] = ()
    ) -> str: ...

    async def generate_json(
        self,
        *,
        agent: str,
        system: str,
        prompt: str,
        schema: dict,
        attachments: Sequence[Path] = (),
    ) -> dict: ...


class GeminiLLM:
    """google-genai SDK의 비동기 클라이언트로 호출한다. 동시 요청 수는 세마포어로 묶는다."""

    def __init__(self, settings: Settings, json_retry_message: str):
        if not settings.api_key_ready:
            raise LLMError(
                "GEMINI_API_KEY가 없거나 올바르지 않습니다. 1123test/.env에 실제 키를 넣거나 dry-run으로 실행하세요."
            )
        self._json_retry = json_retry_message
        from google import genai
        from google.genai import types

        self._types = types
        self.model = settings.model
        self._temperature = settings.temperature
        self._sem = asyncio.Semaphore(settings.max_concurrency)
        self._client = genai.Client(
            api_key=settings.api_key,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=4, initial_delay=2.0)
            ),
        )

    def _contents(self, prompt: str, attachments: Sequence[Path]) -> list:
        parts = []
        for path in attachments:
            mime = mimetypes.guess_type(path.name)[0] or "application/pdf"
            parts.append(self._types.Part.from_bytes(data=path.read_bytes(), mime_type=mime))
        parts.append(prompt)
        return parts

    async def _call(self, system: str, contents: list, **config) -> str:
        cfg = self._types.GenerateContentConfig(
            system_instruction=system, temperature=self._temperature, **config
        )
        async with self._sem:
            resp = await self._client.aio.models.generate_content(
                model=self.model, contents=contents, config=cfg
            )
        text = resp.text
        if not text:
            reason = resp.candidates[0].finish_reason if resp.candidates else "응답 없음"
            raise LLMError(f"빈 응답 (finish_reason={reason})")
        return text

    async def research(self, *, agent, system, prompt, attachments=()):
        tool = self._types.Tool(google_search=self._types.GoogleSearch())
        return await self._call(system, self._contents(prompt, attachments), tools=[tool])

    async def generate_json(self, *, agent, system, prompt, schema, attachments=()):
        contents = self._contents(prompt, attachments)
        last_error = None
        for _ in range(2):
            text = await self._call(
                system,
                contents,
                response_mime_type="application/json",
                response_json_schema=schema,
            )
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                last_error = e
                contents = contents + [self._json_retry]
        raise LLMError(f"{agent}: JSON 파싱 실패 ({last_error})")
