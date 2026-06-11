from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):  # type: ignore[misc]
        pass


PACKAGE_DIR = Path(__file__).resolve().parent
AGENT_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = AGENT_DIR.parent
LEGACY_RAG_DIR = PROJECT_ROOT / "RAG" / "SilverSynkRAGST"

for env_path in (
    PROJECT_ROOT / ".env",
    AGENT_DIR / ".env",
    PACKAGE_DIR / ".env",
    LEGACY_RAG_DIR / ".env",
):
    load_dotenv(env_path)

BEDROCK_API_KEY = os.getenv("BEDROCK_API") or os.getenv("AWS_BEARER_TOKEN_BEDROCK")
if BEDROCK_API_KEY and not os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = BEDROCK_API_KEY

LLM_PROVIDER = os.getenv("LLM_PROVIDER")
if not LLM_PROVIDER:
    LLM_PROVIDER = "bedrock" if BEDROCK_API_KEY else "ollama"

BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    os.getenv("AWS_BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0"),
)
OLLAMA_MODEL = os.getenv("GEMMA_MODEL", os.getenv("OLLAMA_MODEL", "gemma3:4b"))
DEFAULT_CHAT_MODEL = BEDROCK_MODEL_ID if LLM_PROVIDER == "bedrock" else OLLAMA_MODEL
DEFAULT_WORKER_MODEL = BEDROCK_MODEL_ID if LLM_PROVIDER == "bedrock" else DEFAULT_CHAT_MODEL
DEFAULT_PLANNER_MODEL = BEDROCK_MODEL_ID if LLM_PROVIDER == "bedrock" else DEFAULT_CHAT_MODEL
DEFAULT_JUDGE_MODEL = BEDROCK_MODEL_ID if LLM_PROVIDER == "bedrock" else DEFAULT_CHAT_MODEL
GEMMA4_BACKEND = os.getenv("GEMMA4_BACKEND", os.getenv("GEMMA_BACKEND", "ollama")).lower()
GEMMA4_MODEL = os.getenv(
    "GEMMA4_MODEL",
    os.getenv(
        "GEMMA_MODEL",
        "gemma4:latest" if GEMMA4_BACKEND == "ollama" else "google/gemma-4-26b-a4b-it",
    ),
)
GEMMA4_BASE_URL = os.getenv(
    "GEMMA4_BASE_URL",
    os.getenv(
        "GEMMA_BASE_URL",
        "http://localhost:11434" if GEMMA4_BACKEND == "ollama" else "http://localhost:8000/v1",
    ),
)
DEFAULT_SIMPLE_ROUTE_PROVIDER = os.getenv("SIMPLE_ROUTE_PROVIDER", LLM_PROVIDER)
DEFAULT_SIMPLE_ROUTE_MODEL = (
    GEMMA4_MODEL if DEFAULT_SIMPLE_ROUTE_PROVIDER == "gemma4" else DEFAULT_WORKER_MODEL
)
DEFAULT_RAG_BACKEND = "supabase" if os.getenv("SUPABASE_URL") else "mongodb"


@dataclass(frozen=True)
class Settings:
    mongo_uri: str | None = os.getenv("MONGO_URI")
    db_name: str = os.getenv("DB_NAME", "silver_sync_db")
    rag_backend: str = os.getenv("RAG_BACKEND", DEFAULT_RAG_BACKEND).lower()
    supabase_url: str | None = os.getenv("SUPABASE_URL")
    supabase_key: str | None = os.getenv("SUPABASE_KEY")
    supabase_table: str = os.getenv("SUPABASE_TABLE", "knowledge_base")
    supabase_match_fn: str = os.getenv("SUPABASE_MATCH_FN", "match_documents")
    supabase_upsert_conflict: str = os.getenv("SUPABASE_UPSERT_CONFLICT", "content_hash")
    llm_provider: str = LLM_PROVIDER
    bedrock_api_key: str | None = BEDROCK_API_KEY
    bedrock_region: str = os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "ap-northeast-2")))
    bedrock_model_id: str = BEDROCK_MODEL_ID
    ollama_model: str = OLLAMA_MODEL
    worker_model: str = os.getenv("WORKER_MODEL", os.getenv("OLLAMA_WORKER_MODEL", DEFAULT_WORKER_MODEL))
    planner_model: str = os.getenv("PLANNER_MODEL", os.getenv("OLLAMA_PLANNER_MODEL", DEFAULT_PLANNER_MODEL))
    judge_model: str = os.getenv("JUDGE_MODEL", os.getenv("OLLAMA_JUDGE_MODEL", DEFAULT_JUDGE_MODEL))
    gemma4_backend: str = GEMMA4_BACKEND
    gemma4_model: str = GEMMA4_MODEL
    gemma4_base_url: str = GEMMA4_BASE_URL
    gemma4_api_key: str | None = os.getenv("GEMMA4_API_KEY", os.getenv("GEMMA_API_KEY"))
    gemma4_temperature: float = float(os.getenv("GEMMA4_TEMPERATURE", os.getenv("GEMMA_TEMPERATURE", "0")))
    gemma4_timeout: int = int(os.getenv("GEMMA4_TIMEOUT", os.getenv("GEMMA_TIMEOUT", "120")))
    simple_route_provider: str = DEFAULT_SIMPLE_ROUTE_PROVIDER
    simple_route_model: str = os.getenv(
        "SIMPLE_ROUTE_MODEL",
        os.getenv("FAST_TRACK_MODEL", DEFAULT_SIMPLE_ROUTE_MODEL),
    )
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
    vector_index_name: str = os.getenv("VECTOR_INDEX_NAME", "vector_index")
    use_llm: bool = os.getenv("USE_LLM", "1") != "0"
    require_llm: bool = os.getenv("REQUIRE_LLM", "0") == "1"
    guideline_top_k: int = int(os.getenv("GUIDELINE_TOP_K", "5"))
    ingest_csv_limit: int = int(os.getenv("INGEST_CSV_LIMIT", "5000"))
    max_loop_count: int = int(os.getenv("MAX_AGENT_LOOP_COUNT", "3"))
    legacy_rag_dir: Path = LEGACY_RAG_DIR


SETTINGS = Settings()
