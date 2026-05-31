# Silver Sync — 비대면/대면 재진 판정 보조 시스템

> 당뇨·고혈압 동반 고위험 고령 환자의 비대면 재진 안전성을 멀티 에이전트 RAG로 평가하는 캡스톤디자인 프로젝트

---

## 시스템 아키텍처

```text
[클라이언트 / 프론트엔드]
         │ POST { patient_id }
         ▼
  [AWS API Gateway]
         │
         ▼
    [AWS Lambda]  (ECR 컨테이너, Python 3.11 / ARM64)
         │
         ├─► [AWS DynamoDB]           환자 생체 정보 & 진료 기록
         ├─► [Supabase Vector Store]  진료지침 & DUR 데이터 RAG
         ├─► [AWS Bedrock]            Claude / Nova 기반 멀티 에이전트
         │
         ▼
    [AWS S3]  최종 판정 보고서 자동 백업
```

| 계층 | 기술 스택 |
|---|---|
| 컴퓨팅 | AWS Lambda (linux/arm64 Docker) |
| 환자 DB | AWS DynamoDB (`SilverSyncPatients`) |
| 지침 RAG | Supabase Vector Store (임베딩: `jhgan/ko-sroberta-multitask`) |
| LLM | AWS Bedrock (Claude 3 Haiku / Nova Pro·Micro) 또는 Ollama |
| 보고서 저장 | AWS S3 (`silversync-results-*`) |
| 프론트엔드 | React + Vite (FE_DEMO) |

---

## 저장소 구조

```
Silver-Sync/
├── multi_agent_rag/          # 핵심 멀티 에이전트 RAG 엔진 (최신)
│   ├── agents/               # 7개 전문 에이전트
│   ├── eval/                 # 합성 벤치마크 & 평가 프레임워크
│   ├── main.py               # 로컬 실행 진입점
│   ├── pipeline.py           # 에이전트 오케스트레이션
│   ├── llm.py                # LLM 추상화 (Bedrock / Ollama / Gemma4)
│   ├── repository.py         # 데이터 접근 (DynamoDB / 더미)
│   ├── clinical_safety.py    # 안전성 가드레일
│   └── schemas.py            # Pydantic 데이터 모델
├── capstone/                 # AWS Lambda 배포 패키지
│   ├── agent/multi_agent_rag/ # Lambda용 에이전트 코드
│   ├── lambda_function.py    # Lambda 핸들러
│   ├── build_lambda.sh       # ECR 이미지 빌드 스크립트
│   └── upload_to_dynamodb.py # 환자 더미 데이터 적재
├── FE_DEMO/                  # 프론트엔드 데모 (React + Vite)
├── mongoDB 설정/              # MongoDB Atlas 초기 DB 구축 스크립트 (역사적)
├── superbaseDB 설정/          # Supabase 초기 구축 스크립트 (역사적)
├── log/                      # 에이전트 실행 로그 (의미 있는 run output)
├── EVAL_METHODOLOGY.md       # 평가 방법론 상세 문서
├── MULTI_AGENT_RUN_GUIDE.md  # 멀티 에이전트 실행 가이드
└── FRONTEND_GUIDE_v1.md      # 프론트엔드 개발 가이드
```

---

## 멀티 에이전트 파이프라인

환자 `patient_id` 하나가 들어오면 아래 7개 에이전트가 순차·병렬로 동작합니다.

| 에이전트 | 역할 |
|---|---|
| `DataCurator` | 원본 데이터 정제, 결측치 점검, 데이터 신뢰도 점수 산정 |
| `ClinicalReasoner` | 토론 필요도 계산 → `full_debate` / `fast_track` / `emergency_bypass` 3갈래 라우팅 |
| `RemoteAdvocate` | 비대면 유지가 타당한 근거 생성 (RAG 참조) |
| `InPersonAdvocate` | 대면 전환이 필요한 리스크 근거 생성 (RAG 참조) |
| `Guardian` | DUR 약물 오남용 검토, 추론 일관성 감시 |
| `Judge` | 4단계 판정(`비대면` / `대면` / `긴급내원` / `데이터불충분_대면`), 확신도 산출 |
| `ActionOrchestrator` | 의사 액션 플랜, 환자 안내 메시지, 다음 설문 생성 |

---

## 빠른 시작 (로컬)

### 1. 환경 설정

```bash
# Python 가상환경
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
pip install -r requirements.multi_agent.txt

# 환경 변수 (.env 파일 생성)
cp .env.example .env
# → .env 에 SUPABASE_URL, SUPABASE_KEY, LLM_PROVIDER 등을 채웁니다
```

### 2. LLM 설정

**AWS Bedrock 사용 시**
```bash
export LLM_PROVIDER=bedrock
export BEDROCK_API=<YOUR_BEARER_TOKEN>
export BEDROCK_MODEL_ID=us.anthropic.claude-3-5-haiku-20241022-v1:0
export AWS_REGION=us-east-1
```

**Ollama (로컬 모델) 사용 시**
```bash
export LLM_PROVIDER=ollama
export WORKER_MODEL=gemma3:4b
export PLANNER_MODEL=gemma3:4b
export JUDGE_MODEL=gemma3:4b
```

### 3. 더미 환자로 실행

```bash
# 안정 환자 (비대면 예상)
python -m multi_agent_rag.main --dummy DUMMY-STABLE-001

# 경계 환자 (토론 필요)
python -m multi_agent_rag.main --dummy DUMMY-BORDERLINE-001 --log

# 응급 환자 (긴급내원 예상)
python -m multi_agent_rag.main --dummy DUMMY-EMERGENCY-001
```

---

## API 호출 규격 (Lambda)

```
POST https://{api-id}.execute-api.ap-northeast-2.amazonaws.com/prod/
Content-Type: application/json

{ "patient_id": "DUMMY-BORDERLINE-001" }
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `patient_id` | String | DynamoDB 파티션 키와 매핑되는 환자 고유 코드 |

---

## 평가 프레임워크 (Eval)

`multi_agent_rag/eval/` 아래에 합성 벤치마크 기반 어블레이션 평가 시스템이 있습니다.

| 데이터셋 | 설명 |
|---|---|
| `eval_cases_v3.json` | 표준 벤치마크 200건 (8 아키타입 × 25) |
| `eval_cases_hard.json` | 단일 LLM이 틀리는 암시적 케이스 |
| `eval_cases_hard2.json` | 비약물 어려운 케이스 (추세·결측·다신호 충돌) |

```bash
# 규칙 베이스라인 평가
python -m multi_agent_rag.eval.baseline

# 멀티 에이전트 풀 평가
python -m multi_agent_rag.eval.run_eval

# ML 베이스라인 비교
python -m multi_agent_rag.eval.ml_baseline
```

자세한 평가 방법론은 [EVAL_METHODOLOGY.md](EVAL_METHODOLOGY.md)를 참조하세요.

---

## Lambda 배포

```bash
cd capstone
chmod +x build_lambda.sh
./build_lambda.sh     # Docker 이미지 빌드 → ECR push → Lambda 함수 업데이트
```

---

## 환경 변수 목록

| 변수 | 설명 | 기본값 |
|---|---|---|
| `LLM_PROVIDER` | `bedrock` / `ollama` | 토큰 존재 시 `bedrock` |
| `BEDROCK_API` | Bedrock Bearer Token | — |
| `BEDROCK_MODEL_ID` | 사용할 Bedrock 모델 ID | Claude 3 Haiku |
| `AWS_REGION` | AWS 리전 | `us-east-1` |
| `SUPABASE_URL` | Supabase 프로젝트 URL | — |
| `SUPABASE_KEY` | Supabase anon key | — |
| `RAG_BACKEND` | `supabase` / `mongodb` | `supabase` |
| `WORKER_MODEL` | Ollama Worker 모델 | `gemma3:4b` |
| `USE_LLM` | `0`이면 규칙 기반 fallback만 사용 | `1` |
| `REQUIRE_LLM` | `1`이면 LLM 실패 시 파이프라인 중단 | `0` |
