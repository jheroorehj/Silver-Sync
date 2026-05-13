from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

from .config import SETTINGS


class LLMClient:
    """Small provider wrapper for Bedrock or Ollama with rule-based fallback."""

    def __init__(
        self,
        model: str | None = None,
        enabled: bool | None = None,
        provider: str | None = None,
    ):
        self.provider = (provider or SETTINGS.llm_provider).lower()
        self.model = model or (
            SETTINGS.bedrock_model_id if self.provider == "bedrock" else SETTINGS.ollama_model
        )
        self.enabled = SETTINGS.use_llm if enabled is None else enabled
        self._llm = None
        self._bedrock = None
        self.last_error: str | None = None

    def set_model(self, model: str) -> None:
        if model == self.model:
            return
        self.model = model
        self._llm = None
        self._bedrock = None

    def set_backend(self, provider: str, model: str | None = None) -> None:
        provider = provider.lower()
        model = model or self.model
        if provider == self.provider and model == self.model:
            return
        self.provider = provider
        self.model = model
        self._llm = None
        self._bedrock = None

    def invoke(self, prompt: str) -> str | None:
        self.last_error = None
        if not self.enabled:
            self.last_error = "USE_LLM=0으로 모델 호출이 비활성화되어 있습니다."
            return None
        try:
            if self.provider == "bedrock":
                return self._invoke_bedrock(prompt)
            if self.provider == "ollama":
                return self._invoke_ollama(prompt)
            if self.provider == "gemma4":
                return self._invoke_gemma4(prompt)
            raise ValueError(f"지원하지 않는 LLM_PROVIDER입니다: {self.provider}")
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            if SETTINGS.require_llm:
                raise RuntimeError(f"LLM 호출 실패 ({self.model}): {self.last_error}") from exc
            return None

    def _invoke_ollama(self, prompt: str) -> str:
        if self._llm is None:
            from langchain_ollama import OllamaLLM

            self._llm = OllamaLLM(model=self.model, temperature=0)
        return self._llm.invoke(prompt)

    def _invoke_bedrock(self, prompt: str) -> str:
        if self._bedrock is None:
            import boto3

            self._bedrock = boto3.client(
                "bedrock-runtime",
                region_name=SETTINGS.bedrock_region,
            )
        response = self._bedrock.converse(
            modelId=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
            inferenceConfig={
                "temperature": 0,
                "maxTokens": 1200,
            },
        )
        content = response.get("output", {}).get("message", {}).get("content", [])
        texts = [block.get("text", "") for block in content if isinstance(block, dict)]
        return "\n".join(text for text in texts if text).strip()

    def _invoke_gemma4(self, prompt: str) -> str:
        backend = SETTINGS.gemma4_backend
        if backend == "ollama":
            return self._invoke_gemma4_ollama(prompt)
        if backend == "openai":
            return self._invoke_gemma4_openai_compatible(prompt)
        raise ValueError(f"지원하지 않는 GEMMA4_BACKEND입니다: {backend}")

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=request_headers,
        )
        with urllib.request.urlopen(request, timeout=SETTINGS.gemma4_timeout) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}

    def _invoke_gemma4_ollama(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": "당신은 당뇨와 고혈압 고령 환자 재진 판단을 보조하는 한국어 의료 AI입니다. 추측하지 말고 JSON 형식을 지키세요.",
                },
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": SETTINGS.gemma4_temperature},
        }
        data = self._post_json(f"{SETTINGS.gemma4_base_url.rstrip('/')}/api/chat", payload)
        return data.get("message", {}).get("content", "").strip()

    def _invoke_gemma4_openai_compatible(self, prompt: str) -> str:
        headers = {}
        if SETTINGS.gemma4_api_key:
            headers["Authorization"] = f"Bearer {SETTINGS.gemma4_api_key}"
        payload = {
            "model": self.model,
            "temperature": SETTINGS.gemma4_temperature,
            "messages": [
                {
                    "role": "system",
                    "content": "당신은 당뇨와 고혈압 고령 환자 재진 판단을 보조하는 한국어 의료 AI입니다. 추측하지 말고 JSON 형식을 지키세요.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        data = self._post_json(
            f"{SETTINGS.gemma4_base_url.rstrip('/')}/chat/completions",
            payload,
            headers=headers,
        )
        choices = data.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "").strip()


def extract_json_object(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def evidence_block(items: list[Any], max_chars: int = 2600) -> str:
    lines: list[str] = []
    total = 0
    for index, item in enumerate(items, 1):
        source = getattr(item, "source", "unknown")
        content = getattr(item, "content", str(item)).replace("\n", " ")
        line = f"[{index}] source={source}\n{content[:700]}"
        if total + len(line) > max_chars:
            break
        lines.append(line)
        total += len(line)
    return "\n\n".join(lines) if lines else "검색된 RAG 근거 없음"
