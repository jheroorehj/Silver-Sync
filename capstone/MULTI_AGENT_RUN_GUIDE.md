이 문서는 AWS DynamoDB와 Bedrock(Claude 3 Haiku) 인프라로 완전히 전환된 당뇨+고혈압 고령 환자 재진 판별 멀티에이전트 시스템의 최신 실행 가이드입니다.

1. 실행 위치 및 가상환경

모든 명령어는 프로젝트 루트 디렉토리에서 실행합니다.
cd C:\Users\yunye\code\capstone


파이썬 실행 시 가상환경 파이프라인 및 바이트코드 생성 방지 옵션(-B)을 함께 사용하는 것을 적극 권장합니다.
.\.venv\Scripts\python.exe --version


2. 필수 환경 변수 설정 (.env)
시스템은 로컬 개발 환경에서 config.py를 통해 설정을 로드하며, AWS Lambda 배포 시에는 콘솔 환경 변수를 직접 참조합니다.
프로젝트 루트 또는 agent/multi_agent_rag/ 내부의 .env 파일에 아래 설정을 입력하세요.

# AWS 인증 및 기본 리전 설정
BEDROCK_REGION=ap-northeast-2
AWS_REGION=ap-northeast-2

# DynamoDB 테이블 명칭 통합 (중요)
DYNAMODB_TABLE_NAME=SilverSyncPatients
DYNAMODB_GUIDELINES_TABLE_NAME=SilverSyncGuidelines

# LLM 백엔드 인프라 (AWS Bedrock 및 Claude 3 Haiku 단일화)
LLM_PROVIDER=bedrock
BEDROCK_MODEL_ID=apac.anthropic.claude-3-haiku-20240307-v1:0


💡 알림: 기존 구형 레거시 버전에서 사용되던 SUPABASE_*, GEMMA4_*, OLLAMA_*, Nova 관련 환경 변수들은 현재 소스 코드 구조에서 완전히 제거되었으므로 더 이상 필요하지 않습니다.

3. 데이터 마이그레이션 (DynamoDB 적재)
3.1 환자 더미 데이터 업로드
로컬에 위치한 dummy_patients.json 데이터를 AWS DynamoDB 환자 테이블로 마이그레이션합니다. 테이블이 없을 경우 자동으로 온디맨드 모드로 생성 및 활성화됩니다.
.\.venv\Scripts\python.exe -B .\upload_to_dynamodb.py


3.2 의학 지침 PDF 및 CSV 매핑 데이터 벡터 라이징 (1024차원)
Amazon Titan Text Embeddings V2 규격(1024차원 고정)을 사용하여 의학 지침서 PDF 및 DUR/노인주의 약물 매핑 CSV를 SilverSyncGuidelines 테이블에 임베딩 적재합니다.
.\.venv\Scripts\python.exe -B .\titanRAG.py


4. 파이프라인 로컬 실행 테스트
4.1 LLM 없이 규칙 기반 Fallback 엔진만 검증
네트워크 통신이나 Bedrock 호출 없이 시스템 자체 하드코딩 룰셋 및 점수 구조만 빠르고 가볍게 테스트하고 싶을 때 사용합니다.
$env:USE_LLM='0'
.\.venv\Scripts\python.exe -B -m agent.multi_agent_rag.main --dummy DUMMY-STABLE-001


4.2 실제 AWS Bedrock (Claude 3 Haiku) 호출 및 실행
모든 에이전트(Curator, Reasoner, Advocates, Guardian, Judge, Orchestrator)가 실제 AWS 클라우드 인프라와 통신하며 판정을 내립니다.
$env:USE_LLM='1'
$env:REQUIRE_LLM='1'
.\.venv\Scripts\python.exe -B -m agent.multi_agent_rag.main --dummy DUMMY-BORDERLINE-001 --log


호출 시 실시간으로 Haiku 모델의 토큰 소모량(입력/출력/총합)과 Titan 임베딩 토큰 사용량이 터미널에 명확히 프린트됩니다.

5. 서버 연동용 JSON 출력 및 로그 확인

5.1 웹 대시보드 인터페이스 연동용 JSON 파싱
.\.venv\Scripts\python.exe -B -m agent.multi_agent_rag.main --dummy DUMMY-BORDERLINE-001 --json
lambda_function.py 표준 스펙과 완벽히 호환되는 최상위 에이전트 파이프라인 결과 object가 완벽히 출력됩니다.

5.2 실행 로그 추적

--log 옵션 활성화 시 agent/log/ 폴더 내부에 파일이 영구 저장됩니다.
로그 위치: capstone/agent/log/YYYYMMDD_HHMMSS_[환자ID].txt
포함 정보: Claude 3 Haiku 토큰 사양, 데이터 신뢰도 점수, RAG 임베딩 매칭 근거 리스트, DUR 복약 가디언 위험 알림 경고 등

6. 라우팅 시나리오별 모델 배치 구조

현재 파이프라인은 복잡한 다중 오케스트레이션을 Claude 3 Haiku 단일 모델 ID로 통합하여 레이턴시와 비용 효율을 극대화했습니다.

full_debate (심층 토론 케이스):
데이터 조건 및 안전성 점수가 경계선일 때 가동됩니다.

Data Curator ➔ Clinical Reasoner ➔ 비대면/대면 Advocates 찬반 교차 논증 ➔ Guardian 안전성 필터 ➔ Judge 최종 보조 판정 ➔ Action Orchestrator 워크플로우 변환 프로세스를 차례대로 거칩니다.

fast_track / emergency_bypass (고속 패스 및 응급 우회):
바이탈이 매우 안정적이거나, 반대로 즉시 병원 후송이 필요한 극단적 Red Flag 수치일 때 작동합니다.
불필요한 비용 낭비를 막기 위해 양측 Advocate 토론을 생략(Skipped)하고 즉시 상위 안전장치와 의사결정 에이전트로 직행합니다.

7. 주요 아키텍처 파일 구성

agent/multi_agent_rag/main.py: CLI 엔진 및 터미널 시각화 디스플레이
agent/multi_agent_rag/pipeline.py: 6개 파이프라인 에이전트 순차 동기 제어 레이어
agent/multi_agent_rag/dynamo_repository.py: DynamoDB 입출력, 1024D 코사인 유사도 벡터 검색 인터페이스
agent/multi_agent_rag/llm.py: Bedrock Converse API 연동 및 실시간 토큰 카운터 파서
agent/multi_agent_rag/personas.py: Silver Sync 전용 임상 전문가 프롬프트 정의서
agent/multi_agent_rag/schemas.py: 데이터 정제 및 JSON 직렬화 대응 데이터 클래스
upload_to_dynamodb.py: 기본 더미 환자 마이그레이션 스크립트
titanRAG.py: 1024차원 의학 지침 벡터 라이징 빌더
lambda_function.py: AWS Lambda 배포용 메인 핸들러 라우터