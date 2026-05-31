# 🏥 Silver Sync: Multi-Agent RAG 기반 재진 판정 보조 시스템

> **AWS Lambda 컨테이너 환경에서 구동되는 고위험 환자(당뇨/고혈압) 비대면 재진 안전성 평가 멀티 에이전트 시스템**

본 저장소는 실버싱크(Silver Sync) 프로젝트의 핵심 백엔드 엔진인 **Multi-Agent RAG 시스템**의 구동 가이드 및 데이터 명세서입니다. 본 시스템은 복잡한 환자의 생체 데이터 및 과거 의무기록을 분석하고, 공인된 진료지침을 RAG(Retrieval-Augmented Generation)로 참조하여 최적의 재진 경로(비대면 유지 또는 대면 전환)를 판정합니다.

---

## 🛠️ 1. 시스템 아키텍처 개요 (Architecture)

시스템은 인프라 비용 최적화와 강력한 보안을 위해 **서버리스 컨테이너(AWS Lambda + ECR)** 아키텍처를 채택하고 있으며, 데이터 및 모델 계층은 아래와 같이 조율됩니다.

```text
[클라이언트 / 프론트엔드]
         │ (POST / patient_id)
         ▼
  [AWS API Gateway] ──(인증 및 라우팅)
         │
         ▼
    [AWS Lambda] ──(ECR 컨테이너 이미지: Python 3.11 / ARM64)
         │
         ├─► [AWS DynamoDB] ── (환자 생체 정보 & 진료기록 스냅샷 로드)
         ├─► [Supabase Vector Store] ── (임상 진료지침 및 DUR 데이터 RAG 검색)
         ├─► [AWS Bedrock (Claude Haiku)] ── (Multi-Agent 협동 토론 및 최종 추론)
         │
         ▼
    [AWS S3] ── (최종 판정 보고서 자동 백업 및 Lifecycle 관리)
```

* **컴퓨팅 환경**: AWS Lambda (linux/arm64 기반 Docker 컨테이너 이미지)
* **환자 데이터베이스**: AWS DynamoDB (`SilverSyncPatients` 테이블)
* **지침 검색 엔진 (RAG)**: Supabase Vector Store (2022 고혈압 진료지침, 2025 당뇨병 진료지침 임베딩 데이터)
* **오케스트레이션 엔진**: AWS Bedrock (Claude 3 Haiku) 기반 독립적 멀티 에이전트 파이프라인
* **결과 스토리지**: AWS S3 (`silversync-results-379995600109` 버킷)

---

## 📥 2. API 입력 방식 및 규격 (Input Specification)

시스템은 외부 대시보드 또는 프론트엔드로부터 복잡한 생체 데이터를 직접 받지 않습니다. 오직 환자의 고유 식별자(`patient_id`)만 수신하여 내부 보안 네트워크(VPC)를 통해 데이터를 안전하게 pull하는 구조입니다.

### 호출 정보
* **HTTP Method**: `POST`
* **Content-Type**: `application/json`
* **Endpoint**: `https://{api-id}.execute-api.ap-northeast-2.amazonaws.com/prod/`

### Request Body 포맷
```json
{
  "patient_id": "DUMMY-BORDERLINE-001"
}
```

| 필드명 | 타입 | 필수 여부 | 설명 |
| :--- | :--- | :---: | :--- |
| `patient_id` | `String` | **필수** | DynamoDB 파티션 키와 매핑되는 환자 고유 코드 |

---

## ⚙️ 3. 핵심 데이터 처리 프로세스 (Data Pipeline)

Lambda 함수가 트리거되면 다음과 같은 파이프라인이 직렬 및 병렬로 안전하게 수행됩니다.

1.  **Event Parsing & Context Loading**: API Gateway로부터 전달받은 JSON에서 `patient_id`를 파싱한 뒤, `DynamoRepository`가 해당 환자의 생체 데이터, 처방 약물, 과거 의사 오버라이드 기록(History)을 읽어옵니다.
2.  **Multi-Agent Pipeline Activation**:
    * **DataCurator**: 원본 데이터를 가공하고 결측치를 점검하여 '데이터 신뢰도 점수'를 산정합니다.
    * **ClinicalReasoner & Advocates**: Supabase에서 환자 맞춤형 진료지침 조각을 검색(RAG)해와서, 비대면 유지가 타당한지(Remote) 대면으로 전환해야 하는지(In-person) 각자의 논거를 바탕으로 논쟁을 벌입니다.
    * **Guardian & Judge**: 약물 오남용(DUR) 검토 및 최종 판정 배지(Verdict)를 부여합니다.
3.  **Decimal Type Conversion**: DynamoDB의 숫자 타입 연산 결과인 파이썬 `Decimal` 객체를 표준 JSON 규격으로 전송 및 저장하기 위해 `convert_decimal` 함수와 `DecimalEncoder`가 자동 후처리를 수행합니다.
