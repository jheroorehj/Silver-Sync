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
        
        # 🎯 [Converse API 정석 파싱] 2026 AWS Bedrock 공식 규격 적용
        # 최신 converse API는 response 최상단이나 메타데이터에 'usage' 오브젝트를 품고 반환합니다.
        input_tok = 0
        output_tok = 0
        
        # 1. 최상단 'usage' 맵 서치
        if "usage" in response:
            usage = response["usage"]
            input_tok = usage.get("inputTokens", 0)
            output_tok = usage.get("outputTokens", 0)
            
        # 2. 크로스 리전(apac) 경로나 하위 메타데이터 맵 서치 (교차 방어)
        elif "metrics" in response:
            input_tok = response["metrics"].get("inputTokenCount", 0)
            output_tok = response["metrics"].get("outputTokenCount", 0)

        total_tok = input_tok + output_tok
        
        # 📊 확보된 토큰 정보 터미널에 강력하게 고정 인쇄
        if total_tok > 0:
            print(f"    └── [Haiku 토큰 소모] 입력: {input_tok:,} | 출력: {output_tok:,} | 총 소모: {total_tok:,}")
        else:
            # 최종 디버깅: 어떤 구조로 응답 데이터가 반환되는지 키값들만 추려내어 강제 출력
            print(f"    ⚠️ [토큰 디버그] 키 배열: {list(response.keys())}")

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
