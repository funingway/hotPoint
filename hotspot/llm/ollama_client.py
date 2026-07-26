import asyncio
import json
import logging

import httpx

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "batiai/gemma4-12b:q4",
        temperature: float = 0.3,
        max_tokens: int = 4096,
        timeout: int = 120,
        max_retries: int = 3,
        concurrency: int = 4,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self._sem = asyncio.Semaphore(concurrency)

    async def _raw_chat(self, prompt: str) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["message"]["content"]
            except (httpx.HTTPError, KeyError, IndexError) as e:
                last_exc = e
                wait = 2 ** attempt
                logger.warning(f"Ollama call failed (attempt {attempt+1}): {e}, retry in {wait}s")
                await asyncio.sleep(wait)
        raise LLMError(f"Ollama call failed after {self.max_retries} retries: {last_exc}")

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            raise LLMError(f"Failed to parse JSON from LLM output: {text[:200]}")

    async def chat_json(self, prompt: str, schema_hint: str | None = None) -> dict:
        full_prompt = prompt
        if schema_hint:
            full_prompt = f"{prompt}\n\n必须返回符合以下结构的 JSON：\n{schema_hint}"
        async with self._sem:
            text = await self._raw_chat(full_prompt)
        return self._parse_json(text)

    async def batch_chat_json(self, prompts: list[str]) -> list[dict | None]:
        async def one(p: str) -> dict | None:
            try:
                return await self.chat_json(p)
            except LLMError as e:
                logger.warning(f"Batch call failed: {e}")
                return None
        return await asyncio.gather(*[one(p) for p in prompts])

    async def ping(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
