from __future__ import annotations
import os
import sys
import json
import boto3
from datetime import datetime
from decimal import Decimal

# 람다 환경 최적화 설정 (PYTHONDONTWRITEBYTECODE는 .zip 배포에도 유효)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1" 


def convert_decimal(obj):
    """DynamoDB에서 읽어온 Decimal 객체들을 파이썬 내장 데이터 타입으로 안전하게 변환합니다."""
    if isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    return obj


class DecimalEncoder(json.JSONEncoder):
    """JSON 직렬화 중 발생할 수 있는 Decimal 에러를 방지하는 엔코더입니다."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 else int(obj)
        return super(DecimalEncoder, self).default(obj)

# --- (이 아래부터 원래 작성하신 import json 등 기존 코드 시작) ---

from agent.multi_agent_rag.pipeline import MultiAgentRevisitPipeline
from agent.multi_agent_rag.schemas import to_jsonable
from agent.multi_agent_rag.dynamo_repository import DynamoRepository

print("Initializing MultiAgentRevisitPipeline for Lambda...")
# 리포지토리와 파이프라인 인스턴스를 핸들러 외부(Global)에서 한 번만 생성하여 Warm Start 효율 극대화
repository = DynamoRepository()
pipeline = MultiAgentRevisitPipeline(repository=repository)
s3_client = boto3.client("s3")

RESULT_BUCKET = os.environ.get("S3_RESULT_BUCKET", "silversync-results-YOUR_AWS_ACCOUNT_ID") # YOUR_AWS_ACCOUNT_ID로 변경
print(f"Pipeline initialized. Target S3 Bucket: {RESULT_BUCKET}")

def handler(event: dict, context) -> dict:
    print(f"Received event: {json.dumps(event)}")

    try:
        # API Gateway 연동 또는 직접 호출 이벤트에 따른 바디 파싱 리스크 방어
        if "body" in event and isinstance(event["body"], str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", event)  # 직결 호출일 경우 event 자체가 body일 수 있음

        patient_id = body.get("patient_id")

        if not patient_id:
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps({"error": "patient_id is required in the request body"}),
            }

        # 멀티 에이전트 재진 추론 파이프라인 구동
        result = pipeline.run(patient_search=patient_id)
        
        # 소수점 데이터 정제 및 JSON 변환
        cleaned_result = convert_decimal(result)
        json_result = to_jsonable(cleaned_result)

        # 저장용 타임스탬프 파일명 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_key = f"results/{patient_id}/{timestamp}.json"
        
        # 히스토리 추적을 위해 S3 버킷에 추론 결과 업로드
        try:
            s3_client.put_object(
                Bucket=RESULT_BUCKET,
                Key=file_key,
                Body=json.dumps(json_result, cls=DecimalEncoder, ensure_ascii=False, indent=2),
                ContentType="application/json; charset=utf-8"
            )
            print(f"Successfully uploaded result to s3://{RESULT_BUCKET}/{file_key}")
        except Exception as s3_err:
            print(f"🚨 S3 Upload Failed: {s3_err}")

        # 정상 응답 반환 (CORS 헤더 포함)
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json; charset=utf-8",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "message": "Success",
                "s3_path": f"s3://{RESULT_BUCKET}/{file_key}",
                "data": json_result
            }, cls=DecimalEncoder, ensure_ascii=False, indent=2),
        }

    except Exception as e:
        error_message = f"An internal server error occurred: {type(e).__name__}: {e}"
        print(f"🚨 Handler Exception: {error_message}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"error": error_message}),
        }