--- /dev/null
+++ b/Users/yangjunseo/Silver_sync/Silver-Sync/capstone/SYSTEM_GUIDE.md
@@ -0,0 +1,78 @@
+# Silver Sync: Multi-Agent RAG 시스템 가이드
+
+본 문서는 Silver Sync 재진 판정 보조 시스템의 데이터 흐름, 입력 방식 및 S3 결과 저장 구조에 대해 설명합니다.
+
+## 1. 시스템 아키텍처 개요
+
+본 시스템은 AWS Lambda 상에서 컨테이너 기반으로 구동되며, 멀티 에이전트 파이프라인을 통해 환자의 상태를 분석합니다.
+
+*   **컴퓨팅**: AWS Lambda (ECR 컨테이너 이미지)
+*   **환자 데이터**: AWS DynamoDB (`SilverSyncPatients` 테이블)
+*   **참조 지침 (RAG)**: Supabase Vector Store (진료지침 및 DUR 데이터)
+*   **LLM 엔진**: AWS Bedrock (Claude Haiku 3.0)
+*   **결과 저장**: AWS S3 (`silversync-results-{AccountID}` 버킷)
+
+## 2. 입력 방식 (Input Method)
+
+시스템은 **API Gateway**를 통한 REST API 호출을 입력으로 받습니다.
+
+### 호출 규격
+*   **Method**: `POST`
+*   **Endpoint**: `<https://{api-id}.execute-api.{region}.amazonaws.com/prod/>` (예시)
+*   **Content-Type**: `application/json`
+
+### Request Body 형식
+```json
+{
+  "patient_id": "DUMMY-STABLE-001"
+}
+```
+*   `patient_id`: DynamoDB 테이블의 파티션 키(Partition Key)와 일치하는 환자 고유 식별자입니다.
+
+## 3. 처리 프로세스
+1.  **Event 수신**: Lambda 함수가 API Gateway로부터 JSON 이벤트를 수신합니다.
+2.  **데이터 로드**: `DynamoRepository`가 DynamoDB에서 해당 `patient_id`의 최신 진료 기록과 상태 스냅샷을 가져옵니다.
+3.  **파이프라인 실행**: `MultiAgentRevisitPipeline`이 구동되어 DataCurator, ClinicalReasoner 등 각 에이전트가 협업하여 분석을 수행합니다.
+4.  **RAG 참조**: 분석 과정에서 필요한 진료 지침과 약물 상호작용 정보는 Supabase에서 벡터 검색을 통해 실시간으로 참조합니다.
+5.  **데이터 정리**: 분석 결과에 포함된 DynamoDB 전용 `Decimal` 타입을 표준 JSON 규격(float/int)으로 변환합니다.
+
+## 4. S3 출력 저장 방식 (Output Storage)
+
+분석이 완료되면 모든 에이전트의 추론 결과가 포함된 최종 보고서가 S3에 JSON 파일로 자동 저장됩니다.
+
+### 버킷 명칭
+*   `silversync-results-379995600109` (설정된 AWS 계정 ID 포함)
+
+### 저장 경로 (Object Key)
+계층적 구조를 사용하여 환자별로 결과를 관리합니다.
+*   **형식**: `results/{patient_id}/{YYYYMMDD_HHMMSS}.json`
+*   **예시**: `results/DUMMY-STABLE-001/20240520_143005.json`
+
+### 저장 데이터 구성
+저장되는 JSON 파일에는 다음과 같은 데이터가 포함됩니다:
+*   `curated_case`: 정리된 환자 신호 및 데이터 품질 점수
+*   `reasoning`: 초기 임상 추론 결과 및 라우팅 결정
+*   `guardian`: 약물 상호작용(DUR) 경고 및 시스템 안전성 검토 내용
+*   `judge`: 최종 재진 판정 결과 (비대면 유지/대면 전환 등)
+*   `action_plan`: 의사를 위한 권장 조치 사항
+*   `s3_path`: 해당 결과 파일이 저장된 위치 정보
+
+## 5. 데이터 수명 주기 및 보안
+
+*   **수명 주기(Lifecycle)**: 
+    *   생성 30일 후: Standard-IA (저빈도 액세스)로 전환되어 비용 절감
+    *   생성 90일 후: Glacier (아카이브)로 전환
+    *   생성 1년 후: Deep Archive로 전환하여 장기 보관
+*   **보안**:
+    *   모든 데이터는 S3 서버 측 암호화(SSE-S3)를 통해 암호화되어 저장됩니다.
+    *   퍼블릭 액세스는 완전히 차단되어 있으며, IAM 역할과 VPC 엔드포인트를 통해서만 접근 가능합니다.
+
+---
+*작성일: 2024년 5월 20일*
+*Silver Sync Engineering Team*
+```

---

### 상세 설명 요약

1.  **입력(Input)**: 사용자가 API를 통해 `patient_id`를 던지면, Lambda가 이를 받아 DynamoDB에서 실제 환자 데이터를 조회합니다. 직접 대량의 데이터를 보낼 필요 없이 ID 하나로 시스템이 구동됩니다.
2.  **데이터 변환**: DynamoDB에서 가져온 숫자는 파이썬에서 `Decimal` 타입으로 인식되는데, 이는 표준 JSON으로 저장할 때 에러를 일으킵니다. 코드 내 `convert_decimal` 함수와 `DecimalEncoder`가 이를 자동으로 숫자로 변환하여 저장합니다.
3.  **저장(Storage)**: S3 버킷 내부에 `results/환자ID/날짜_시간.json` 형태로 저장되므로, 특정 환자의 과거 분석 이력을 시간 순으로 쉽게 조회할 수 있습니다.
4.  **비용 관리**: 수명 주기 정책(Lifecycle Configuration)이 설정되어 있어, 시간이 지난 데이터는 자동으로 매우 저렴한 스토리지로 이동되어 운영 비용을 최적화합니다.



