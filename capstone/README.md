# **🌟 Silver Sync: Multi-Agent RAG 시스템 가이드 (2026 최신본)**

본 문서는 AWS DynamoDB, Bedrock, S3 인프라로 완전히 일원화된 **Silver Sync 재진 판별 보조 시스템**의 종합 데이터 흐름, API 입력 방식, RAG 동작 원리 및 S3 결과 저장 구조에 대해 설명합니다.

## **1\. 시스템 아키텍처 개요**

본 시스템은 AWS Lambda 상에서 무상태(Stateless) 컨테이너 또는 고성능 마이크로서비스 환경에서 구동되며, 6개의 전문 협업 임상 에이전트 파이프라인을 통해 고령 환자의 재진 위험도를 구조화하고 의사결정을 보조합니다.

\[사용자 요청 (patient\_id)\]  
        │  
        ▼  
┌────────────────────────────────────────────────────────┐  
│               AWS Lambda (Python 3.11+)                │  
│  \- MultiAgentRevisitPipeline                           │  
│  \- DynamoRepository                                    │  
└──────┬──────────────────────┬───────────────────┬──────┘  
       │                      │                   │  
       ▼ (환자 정보 조회)       ▼ (1024D 벡터 검색)  ▼ (추론 분석)  
┌──────────────┐      ┌─────────────────┐   ┌───────────────┐  
│  DynamoDB    │      │    DynamoDB     │   │  AWS Bedrock  │  
│  Patients    │      │   Guidelines    │   │  Claude 3     │  
│  Table       │      │   Table (RAG)   │   │  Haiku        │  
└──────────────┘      └─────────────────┘   └───────────────┘  
                                                  │  
                                                  ▼ (보고서 저장)  
                                            ┌───────────────┐  
                                            │    AWS S3     │  
                                            │  Results Buck.│  
                                            └───────────────┘

* **컴퓨팅**: AWS Lambda (Warm Start 효율 최적화 및 리포지토리 글로벌 인스턴스화 적용)  
* **환자 데이터**: AWS DynamoDB (SilverSyncPatients 테이블)  
* **참조 지침 (RAG)**: AWS DynamoDB (SilverSyncGuidelines 테이블 \- Titan V2 1024차원 벡터 수록)  
* **LLM 엔진**: AWS Bedrock (Claude 3 Haiku \- Converse API 규격 적용)  
* **결과 저장**: AWS S3 (silversync-results-YOUR\_AWS\_ACCOUNT\_ID 버킷)

## **2\. API 입력 방식 (Input Method)**

시스템은 **API Gateway** 또는 직접 호출 이벤트를 통해 비동기/동기 REST API 형식으로 환자 식별자를 입력받습니다.

### **2.1 호출 규격**

* **HTTP Method**: POST  
* **Endpoint**: https://{api-id}.execute-api.ap-northeast-2.amazonaws.com/prod/revisit  
* **Content-Type**: application/json; charset=utf-8

### **2.2 Request Body 형식**

{  
  "patient\_id": "DUMMY-BORDERLINE-001"  
}

* patient\_id: SilverSyncPatients 테이블의 파티션 키(Partition Key, S 타입)에 대응하는 고유 환자 코드입니다.

## **3\. 핵심 처리 프로세스**

1. **Event 수신 및 파싱**: Lambda 함수가 요청을 수신하여 patient\_id 유효성을 검증합니다.  
2. **환자 스냅샷 로드**: DynamoRepository가 SilverSyncPatients 테이블에서 대상 환자의 인적사항, 기저질환(conditions), 복용 약물(medications), 과거 의사 오버라이드 기록, 그리고 과거 바이탈 진료 기록(records)을 한 번에 읽어와 PatientSnapshot 객체로 역직렬화합니다.  
3. **데이터 정제 (Data Curator)**: 데이터의 누락 및 품질 점수를 연산하고, 최근 수치 변동 폭(Delta) 등의 시놉시스를 생성합니다.  
4. **1차 추론 및 임베딩 RAG 검색 (Clinical Reasoner)**:  
   * 임상 쟁점을 정의한 뒤, amazon.titan-embed-text-v2:0 모델을 활용하여 1024차원 규격으로 입력 쿼리를 벡터라이징합니다.  
   * SilverSyncGuidelines 테이블을 코사인 유사도(Cosine Similarity) 알고리즘으로 스캔 매칭하여 최상위 ![][image1]개의 관련 의학 지침(CLINICAL\_GUIDELINE) 및 약물 정보(DUR, 노인주의)를 가져옵니다.  
5. **에이전트 토론 및 검증 (Advocates & Guardian)**:  
   * 위험도가 경계선일 경우 비대면/대면 Advocate 에이전트 간의 교차 토론이 가동됩니다.  
   * Guardian 에이전트가 복약 성분 매칭 스캔을 통해 DUR 약물 상호작용 위험 요소를 상시 교차 필터링합니다.  
6. **최종 판정 및 액션 플랜 (Judge & Action Orchestrator)**:  
   * 종합 위험도와 판단 확신도를 기준으로 의사결정을 최종 조율하여 등급 및 UI 레이아웃 모드(ui\_mode)를 반환합니다.

## **4\. S3 출력 및 저장 방식 (Output Storage)**

분석 완료와 동시에 모든 에이전트의 로깅 원본 및 구조화된 JSON 데이터가 AWS S3 버킷에 아카이빙 처리됩니다.

### **4.1 S3 버킷 명칭**

* silversync-results-YOUR\_AWS\_ACCOUNT\_ID (환경 변수 S3\_RESULT\_BUCKET 설정을 따름)

### **4.2 계층적 디렉토리 구조 (Object Key)**

환자 ID 및 실행 시점의 타임스탬프를 조합한 정렬 가능한 경로를 사용합니다.

* **저장 포맷**: results/{patient\_id}/{YYYYMMDD\_HHMMSS}.json  
* **실제 예시**: results/DUMMY-BORDERLINE-001/20260522\_151300.json

### **4.3 저장 데이터 구조 (JSON Payload 예시)**

DynamoDB 전용 데이터 타입인 Decimal은 파이썬 내장 float 및 int로 안전하게 다운캐스팅(Down-casting) 정제되어 업로드됩니다.

{  
  "message": "Success",  
  "s3\_path": "s3://silversync-results-YOUR\_AWS\_ACCOUNT\_ID/results/DUMMY-BORDERLINE-001/20260522\_151300.json",  
  "data": {  
    "curated\_case": {  
      "patient": {  
        "patient\_id": "DUMMY-BORDERLINE-001",  
        "name": "홍길동",  
        "age": 72,  
        "gender": "M",  
        "conditions": \["당뇨병", "고혈압"\],  
        "medications": \["아스피린", "메트포르민"\]  
      },  
      "data\_quality\_score": 92,  
      "signals": {  
        "latest\_systolic": 142,  
        "latest\_diastolic": 88,  
        "latest\_blood\_sugar": 195,  
        "latest\_hba1c": 8.1,  
        "blood\_sugar\_delta": 25.0  
      },  
      "curator\_notes": \[  
        "데이터 신뢰도 점수: 92/100",  
        "HbA1c 및 혈당 수치 동반 상승 추세 관찰됨."  
      \]  
    },  
    "reasoning": {  
      "routing": "full\_debate",  
      "debate\_necessity\_score": 65,  
      "summary": "72세 당뇨 및 고혈압 환자이며, 최근 혈당과 혈압 수치가 모두 경계 조절 영역을 벗어났습니다."  
    },  
    "guardian": {  
      "blocked": false,  
      "reasons": \["DUR 기반 약물 안전성 확인 필요"\],  
      "medication\_alerts": \["\[DUR\_ALERT\] 메트포르민 신기능 저하 환자 주의 필요"\]  
    },  
    "judge": {  
      "verdict\_level": "orange",  
      "consultation\_type": "대면",  
      "confidence": 75,  
      "risk\_score": 62,  
      "ui\_mode": "summary\_with\_agent\_evidence",  
      "rationale": "최근 조절 수치의 불안정 및 DUR 경고가 발견되어 안전한 추적을 위해 대면 진료 전환을 강력히 권고합니다."  
    },  
    "action\_plan": {  
      "doctor\_actions": \[  
        "대면 재진 예약을 권고하고 혈압/혈당 조절 악화 원인을 확인하세요."  
      \],  
      "patient\_messages": \[  
        "최근 수치 확인을 위해 병원 방문 상담이 권고됩니다."  
      \],  
      "next\_survey\_questions": \[  
        "최근 2주 동안 단 음식, 과식, 야식, 운동 감소가 있었나요?"  
      \]  
    }  
  }  
}

## **5\. 인프라 운영 및 보안 거버넌스**

### **5.1 S3 데이터 라이프사이클 정책 (Lifecycle Policy)**

안전한 환자 의료 이력 관리와 클라우드 비용 최적화를 위해 다음과 같은 S3 수명 주기 규칙을 적용할 것을 권장합니다:

* **Standard (Hot Data)**: 생성일로부터 **30일** 보관 (대시보드 실시간 조회 및 모니터링)  
* **S3 Standard-IA (Infrequent Access)**: **31일 \~ 90일** (저렴한 실시간 접근 보장)  
* **S3 Glacier Flexible Archive**: **91일 이후** 아카이브 아웃 처리 (최소 비용 장기 보관)

### **5.2 IAM 최소 권한 및 보안 통제**

* Lambda 함수는 지정된 S3 버킷에 대해서만 s3:PutObject 권한을 가집니다.  
* 모든 결과 JSON 데이터는 AWS S3 서버 측 암호화(**SSE-S3** 또는 **KMS**)가 적용되어 유출 시 데이터의 기밀성을 보장합니다.  
* 네트워크 보안을 위해 S3 및 DynamoDB는 인터넷 게이트웨이를 거치지 않는 VPC 엔드포인트(PrivateLink)를 통해 통신하도록 설계되었습니다.

*최종 개정일: 2026년 5월 22일* *Silver Sync 아키텍처 엔지니어링 팀*

[image1]: <data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABMAAAAaCAYAAABVX2cEAAABV0lEQVR4Xu2TPy8EURTFh02IRCSK6eZ/BsnQCI1CYhsKvfgCRKOi0ql8A1FQiIhSdCQ+gZ7EWlZEoZNYho7fzb6V52JIVJI9ycl779xzz955ees4LfwJvu+Ph2F4Aa9hzaznURRNNT3sV41ehZdBEGzYGZ9AwwHG1ziOJ3WN5kFqdTzbrGWkNu35AEx3MM+yrEPpZcKOYGLr3yJJkn6ZCh7bOucluOl5XpetF4JfnTNhK3J2Xbeb/Q6ftaC9P4LGXRM2xp0NsJ4SdKJ9vwLNt7DOhDOs+wRVJJzziPYWgvvoM1O90LyGVGJdNNqW9heCxnlplLfU1NI07ZFJYU691/YXgoY9CePxjip93Uy3bOuFCBvv64FtydYJHzJhNY7tdu1LYByWBj7lUNcE1M6kzhXM6to7KE6Ejf/jPXyGTwTesE5LnTvrZH8FH2VqmMOqo6ZvoYV/iTf/JV5quqKzMAAAAABJRU5ErkJggg==>