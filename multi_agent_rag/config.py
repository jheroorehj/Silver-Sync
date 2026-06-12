from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PACKAGE_DIR = Path(__file__).resolve().parent
AGENT_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = AGENT_DIR.parent

for env_path in (
    PROJECT_ROOT / ".env",
    AGENT_DIR / ".env",
    PACKAGE_DIR / ".env",
):
    load_dotenv(env_path)

BEDROCK_API_KEY = os.getenv("BEDROCK_API") or os.getenv("AWS_BEARER_TOKEN_BEDROCK")
if BEDROCK_API_KEY and not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = BEDROCK_API_KEY

LLM_PROVIDER = os.getenv("LLM_PROVIDER")
if not LLM_PROVIDER:
    LLM_PROVIDER = "bedrock"

BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    os.getenv("AWS_BEDROCK_MODEL_ID", "apac.anthropic.claude-3-haiku-20240307-v1:0"),
)

DEFAULT_CHAT_MODEL = BEDROCK_MODEL_ID
DEFAULT_WORKER_MODEL = BEDROCK_MODEL_ID
DEFAULT_PLANNER_MODEL = BEDROCK_MODEL_ID
DEFAULT_JUDGE_MODEL = BEDROCK_MODEL_ID
DEFAULT_SIMPLE_ROUTE_PROVIDER = "bedrock"
DEFAULT_SIMPLE_ROUTE_MODEL = BEDROCK_MODEL_ID
DEFAULT_RAG_BACKEND = "dynamodb"


@dataclass(frozen=True)
class Settings:
    rag_backend: str = os.getenv("RAG_BACKEND", DEFAULT_RAG_BACKEND).lower()
    dynamodb_guidelines_table_name: str = os.getenv("DYNAMODB_GUIDELINES_TABLE_NAME", "SilverSyncGuidelines")
    llm_provider: str = LLM_PROVIDER
    bedrock_api_key: str | None = BEDROCK_API_KEY
    bedrock_region: str = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-northeast-2"))
    bedrock_model_id: str = BEDROCK_MODEL_ID
    worker_model: str = os.getenv("WORKER_MODEL", os.getenv("OLLAMA_WORKER_MODEL", DEFAULT_WORKER_MODEL))
    planner_model: str = os.getenv("PLANNER_MODEL", os.getenv("OLLAMA_PLANNER_MODEL", DEFAULT_PLANNER_MODEL))
    judge_model: str = os.getenv("JUDGE_MODEL", os.getenv("OLLAMA_JUDGE_MODEL", DEFAULT_JUDGE_MODEL))
    simple_route_provider: str = DEFAULT_SIMPLE_ROUTE_PROVIDER
    simple_route_model: str = os.getenv(
        "SIMPLE_ROUTE_MODEL",
        os.getenv("FAST_TRACK_MODEL", DEFAULT_SIMPLE_ROUTE_MODEL),
    )
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
    vector_index_name: str = os.getenv("VECTOR_INDEX_NAME", "vector_index")
    use_llm: bool = os.getenv("USE_LLM", "1") != "0"
    require_llm: bool = os.getenv("REQUIRE_LLM", "0") == "1"
    guideline_top_k: int = int(os.getenv("GUIDELINE_TOP_K", "5"))
    ingest_csv_limit: int = int(os.getenv("INGEST_CSV_LIMIT", "5000"))
    max_loop_count: int = int(os.getenv("MAX_AGENT_LOOP_COUNT", "3"))


SETTINGS = Settings()
