import json

import httpx

from autolyrics.application.interfaces.llm import ILlmClient


class OpenAiCompatibleLlmClient(ILlmClient):
    """Chat completions against any OpenAI-compatible endpoint (DeepSeek, a gateway, Ollama)."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, api_key: str | None, model: str,
                 timeout: float = 180):
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def complete_json(self, system: str, prompt: str) -> dict:
        if not self._api_key:
            raise RuntimeError("no LLM API key configured (AGENT_API_KEY)")
        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "temperature": 0,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": prompt}]},
            timeout=self._timeout)
        response.raise_for_status()
        return JsonReply(response.json()["choices"][0]["message"]["content"] or "").parse()


class JsonReply:
    """Models sometimes wrap JSON in a code fence or add a sentence; take the outermost object."""

    def __init__(self, content: str):
        self._content = content

    def parse(self) -> dict:
        start, end = self._content.find("{"), self._content.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM reply contains no JSON object")
        return json.loads(self._content[start:end + 1])
