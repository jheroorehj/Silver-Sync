# Silver Sync Multi-Agent RAG

당뇨와 고혈압을 동시에 가진 65세 이상 만성질환자의 재진을 두고
비대면/대면 여부를 판정하는 멀티에이전트 RAG 프로토타입입니다.

## 실행

```powershell
cd C:\Users\yunye\code\capstone\agent
python -m multi_agent_rag.main --sample
python -m multi_agent_rag.main --patient P001
python -m multi_agent_rag.main --patient P001 --json
```

또는 프로젝트 루트에서 실행할 수도 있습니다.

```powershell
cd C:\Users\yunye\code\capstone
python -m agent.multi_agent_rag.main --sample
```

환경 변수는 `capstone/.env`, `capstone/agent/.env`,
기존 `capstone/RAG/SilverSynkRAGST/.env` 순서로 읽습니다.

## 모델 호출

LLM provider는 `LLM_PROVIDER`로 지정합니다. `BEDROCK_API` 또는
`AWS_BEARER_TOKEN_BEDROCK`가 있으면 기본값은 `bedrock`이고, 없으면 `ollama`입니다.

### Bedrock

```powershell
$env:LLM_PROVIDER="bedrock"
$env:BEDROCK_API="..."
$env:BEDROCK_MODEL_ID="us.anthropic.claude-3-5-haiku-20241022-v1:0"
$env:AWS_REGION="us-east-1"
```

`BEDROCK_API`는 내부에서 AWS SDK가 읽는 `AWS_BEARER_TOKEN_BEDROCK`로 매핑됩니다.

### Ollama

기본 LLM provider를 Ollama로 쓰려면:

```powershell
$env:LLM_PROVIDER="ollama"
$env:WORKER_MODEL="gemma3:4b"
$env:PLANNER_MODEL="gemma3:4b"
$env:JUDGE_MODEL="gemma3:4b"
```

개별 모델 변수가 없으면 `GEMMA_MODEL` 또는 `OLLAMA_MODEL`을 사용합니다.
`USE_LLM=0`이면 모델 호출 없이 규칙 기반 fallback만 사용합니다.
`REQUIRE_LLM=1`이면 모델 호출 실패 시 파이프라인을 중단합니다.

### 단순 라우트 Gemma4 직접 호출

`fast_track` 또는 `emergency_bypass`는 Advocate 토론을 생략하고, 후속
`ClinicalReasoner`, `Guardian`, `Judge`, `ActionOrchestrator` 호출을 Gemma4 직접
endpoint로 보냅니다. 기본값은 테스트 스크립트와 같은 Ollama Gemma4입니다.

```powershell
$env:SIMPLE_ROUTE_PROVIDER="gemma4"
$env:GEMMA4_BACKEND="ollama"
$env:GEMMA4_MODEL="gemma4:latest"
$env:GEMMA4_BASE_URL="http://localhost:11434"
```

OpenAI-compatible 서버를 쓰는 경우:

```powershell
$env:SIMPLE_ROUTE_PROVIDER="gemma4"
$env:GEMMA4_BACKEND="openai"
$env:GEMMA4_MODEL="google/gemma-4-26b-a4b-it"
$env:GEMMA4_BASE_URL="http://localhost:8000/v1"
$env:GEMMA4_API_KEY="dummy"
```

역할별 기본 배정:

- Worker: `DataCurator`, `Guardian`, `ActionOrchestrator`
- Planner: `ClinicalReasoner`, `RemoteAdvocate`, `InPersonAdvocate`
- Judge: `Judge`

라우팅별 모델 배정:

- `full_debate`: 기존 Bedrock/Nova 역할별 모델을 사용합니다.
- `fast_track`, `emergency_bypass`: Advocate 토론 없이 `SIMPLE_ROUTE_PROVIDER`의
  `GEMMA4_MODEL`을 사용합니다.

RAG 근거는 기존 MongoDB Atlas `knowledge_base`의 `vector_index`에서 가져오며,
검색 임베딩 모델은 기본 `jhgan/ko-sroberta-multitask`입니다.

## Supabase RAG 생성

1. Supabase SQL editor에서 `supabase_schema.sql`을 한 번 실행합니다.
2. `.env`에 `SUPABASE_URL`, `SUPABASE_KEY`를 설정합니다.
3. 원본 RAG 데이터를 업로드합니다. 기본 적재 대상은 `RAG/SilverSynkRAGST` 아래의
   `data`, `data_csv`, `data_plus`, `data_except`입니다.

```powershell
cd C:\Users\yunye\code\capstone
.\.venv\Scripts\python.exe -m agent.multi_agent_rag.ingest_supabase --dry-run
.\.venv\Scripts\python.exe -m agent.multi_agent_rag.ingest_supabase --reset
```

업로드되는 metadata에는 `source`, `source_folder`, `source_path`, `file_type`이 함께 저장되어
RAG 근거가 어느 폴더의 어떤 파일에서 왔는지 추적할 수 있습니다. `data_except`를 제외하려면:

```powershell
.\.venv\Scripts\python.exe -m agent.multi_agent_rag.ingest_supabase --exclude-except
```

Agent가 Supabase RAG를 참조하게 하려면:

```powershell
$env:RAG_BACKEND="supabase"
.\.venv\Scripts\python.exe -m agent.multi_agent_rag.main --sample
```

더미 환자로 실제 파이프라인을 확인하려면:

```powershell
.\.venv\Scripts\python.exe -m agent.multi_agent_rag.main --dummy DUMMY-STABLE-001
.\.venv\Scripts\python.exe -m agent.multi_agent_rag.main --dummy DUMMY-BORDERLINE-001
.\.venv\Scripts\python.exe -m agent.multi_agent_rag.main --dummy DUMMY-EMERGENCY-001
```

`--dummy`는 환자 데이터만 로컬 더미를 사용하고, RAG 근거는 Supabase를 조회합니다.
로그를 저장하려면 `--log`를 추가합니다.

```powershell
.\.venv\Scripts\python.exe -m agent.multi_agent_rag.main --dummy DUMMY-BORDERLINE-001 --log
```

`--reset`은 기존 `knowledge_base` 행을 삭제한 뒤 재적재합니다.
`data_csv`의 대형 CSV는 기본 앞 5000행만 적재하며, `--csv-limit 0`이면 전체를 처리합니다.

## 에이전트 파일

- `agents/data_curator.py`: 환자 정보, 진료 이력, 바이탈, 오버라이드 메모리 정제
- `agents/clinical_reasoner.py`: 토론 필요도 계산, 3갈래 라우팅, 핵심 쟁점 추출
- `agents/remote_advocate.py`: 비대면 가능 근거 생성
- `agents/in_person_advocate.py`: 대면 필요 리스크 근거 생성
- `agents/guardian.py`: DUR, 추론 일관성, 시스템 루프 안전 감시
- `agents/judge.py`: 4단계 판정, 확신도, 미해결 쟁점, UI 모드 산출
- `agents/action_orchestrator.py`: 의사 액션, 환자 메시지, 다음 설문 생성
