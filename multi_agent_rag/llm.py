from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

from .config import SETTINGS


class LLMClient:
    """Small provider wrapper for Bedrock with rule-based fallback."""

    def __init__(
        self,
        model: str | None = None,
        enabled: bool | None = None,
        provider: str | None = None,
    ):
        self.provider = "bedrock"
        self.model = model or SETTINGS.bedrock_model_id
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
        self.model = model
        self._llm = None
        self._bedrock = None

    def invoke(self, prompt: str) -> str | None:
        self.last_error = None
        if not self.enabled:
            self.last_error = "USE_LLM=0으로 모델 호출이 비활성화되어 있습니다."
            return None

        try:
            return self._invoke_bedrock(prompt)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            if SETTINGS.require_llm:
                raise RuntimeError(f"LLM 호출 실패 ({self.model}): {self.last_error}") from exc
            return None

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

        input_tok = 0
        output_tok = 0

        if "usage" in response:
            usage = response["usage"]
            input_tok = usage.get("inputTokens", 0)
            output_tok = usage.get("outputTokens", 0)
        elif "metrics" in response:
            input_tok = response["metrics"].get("inputTokenCount", 0)
            output_tok = response["metrics"].get("outputTokenCount", 0)

        total_tok = input_tok + output_tok
        if total_tok > 0:
            print(f"    └── [Haiku 토큰 소모] 입력: {input_tok:,} | 출력: {output_tok:,} | 총 소모: {total_tok:,}")

        content = response.get("output", {}).get("message", {}).get("content", [])
        texts = [block.get("text", "") for block in content if isinstance(block, dict)]
        return "\n".join(text for text in texts if text).strip()

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
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


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
