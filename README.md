# 🛠 SilverSync RAG Engine (`ss_service_2.py`)

`ss_service_2.py`는 SilverSync 프로젝트의 핵심 백엔드 로직으로, **검색 증강 생성(RAG, Retrieval-Augmented Generation)** 파이프라인을 구현한 엔진입니다. 

---

## 🏗 System Architecture

1. **Query Embedding**: 사용자의 자연어 질문을 `SentenceTransformer`를 통해 768차원의 고밀도 벡터로 변환합니다.
2. **Vector Retrieval**: Supabase의 `pgvector` 기반 RPC 함수(`match_knowledge_emergency`)를 호출하여 `HNSW` 인덱스로 최적화된 고속 유사도 검색을 수행합니다.
3. **Prompt Augmentation**: 검색된 상위 K개의 텍스트 컨텍스트를 시스템 프롬프트에 동적으로 삽입합니다.
4. **Answer Generation**: Ollama 서버에서 구동되는 `gemma:4b` 모델이 컨텍스트에 한정된 정답을 생성하여 Hallucination(환각 현상)을 최소화합니다.

---

## 🔍 핵심 기능 (Core Functions)

### 1. `search_knowledge`
- **목적**: Supabase 데이터베이스 내 의료 지침 검색.
- **특징**: `cosine similarity`를 사용하여 질의와 가장 연관성이 높은 [지침] 데이터 추출.
- **최적화**: 임계값(Threshold) 설정을 통해 연관성이 낮은 데이터의 간섭을 차단.

### 2. `get_gemma_response`
- **목적**: LLM 기반의 전문적인 의료 응답 생성.
- **프롬프트 엔지니어링**:
    - **Role**: 실버케어 전문 의료 보조 AI 페르소나 부여.
    - **Strictness**: 제공된 지침 외의 정보에 대해서는 "정보 부재"를 알리도록 강제.
    - **UX**: 보호자와 간호 인력이 이해하기 쉬운 친절한 전문 용어 사용(해요체).

---

## 🛠 기술 스택 (Tech Stack)

| 구분 | 기술 | 비고 |
| :--- | :--- | :--- |
| **Vector DB** | Supabase | PostgreSQL + `pgvector` |
| **Embedding** | `jhgan/ko-sroberta-multitask` | 한국어 문장 임베딩 최적화 |
| **LLM** | Ollama (Gemma:4b) | 로컬 기반 고성능 언어 모델 |
| **Backend** | Python 3.10+ | Requests, Sentence-Transformers |

---

## ⚙️ 실행 방법 (Usage)

1. **필수 라이브러리 설치**
   ```bash
   pip install supabase sentence-transformers requests python-dotenv
