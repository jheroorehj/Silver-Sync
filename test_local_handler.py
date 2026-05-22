import sys
import os
import json

# Local development fix: Add the 'capstone' directory to the Python path.
# This allows Python to find the 'agent' module as a top-level package, 
# mimicking the directory structure of the AWS Lambda task root.
capstone_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'capstone')
if capstone_dir not in sys.path:
    sys.path.insert(0, capstone_dir)

from capstone.lambda_function import handler

def test_pipeline():
    # 1. 테스트용 Mock 이벤트 생성 (DUMMY-BORDERLINE-001 환자 기준)
    mock_event = {
        "body": json.dumps({
            "patient_id": "DUMMY-BORDERLINE-001"
        })
    }
    
    print("=== 로컬 파이프라인 테스트 시작 ===")
    
    # 2. 람다 핸들러 직접 호출
    # 로컬 환경 변수에 BEDROCK_REGION, DYNAMODB_TABLE_NAME 등이 설정되어 있어야 합니다.
    response = handler(mock_event, None)
    
    # 3. 결과 출력
    status_code = response.get("statusCode")
    body = json.loads(response.get("body", "{}"))
    
    if status_code == 200:
        print(f"\n✅ 테스트 성공! (상태 코드: {status_code})")
        print(f"📂 S3 저장 경로: {body.get('s3_path')}")
        
        # 주요 결과 요약 출력
        data = body.get("data", {})
        judge = data.get("judge", {})
        print(f"\n[최종 판정]: {judge.get('consultation_type')} ({judge.get('verdict_level')})")
        print(f"[신뢰도]: {judge.get('confidence')}%")
        print(f"[판정 근거]: {judge.get('rationale')}")
    else:
        print(f"\n❌ 테스트 실패 (상태 코드: {status_code})")
        print(f"에러 메시지: {body.get('error')}")

if __name__ == "__main__":
    test_pipeline()
