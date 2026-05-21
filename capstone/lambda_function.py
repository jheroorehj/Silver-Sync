from __future__ import annotations
import os
import sys

# 1. 람다 읽기 전용 에러 원천 차단
os.environ["PYTHONDONTWRITEBYTECODE"] = "1" 
os.environ["TRANSFORMERS_CACHE"] = "/tmp"
os.environ["HF_HOME"] = "/tmp"

print("--- [디버그] PyTorch Import 시도 ---")
try:
    import torch
    print(f"✅ PyTorch 로드 성공: {torch.__version__}")
except Exception as e:
    print(f"🚨 PyTorch 로드 실패: {e}")
    sys.exit(1) # 여기서 강제로 멈춥니다!

print("--- [디버그] SentenceTransformers Import 시도 ---")
try:
    import sentence_transformers
    print(f"✅ SentenceTransformers 로드 성공: {sentence_transformers.__version__}")
except Exception as e:
    print(f"🚨 SentenceTransformers 로드 실패: {e}")
    sys.exit(1)

# --- (이 아래부터 원래 작성하신 import json 등 기존 코드 시작) ---
import json
#import os
import boto3
from datetime import datetime
from decimal import Decimal

from agent.multi_agent_rag.pipeline import MultiAgentRevisitPipeline
from agent.multi_agent_rag.schemas import to_jsonable
from agent.multi_agent_rag.dynamo_repository import DynamoRepository

print("Initializing MultiAgentRevisitPipeline for Lambda...")
repository = DynamoRepository()
pipeline = MultiAgentRevisitPipeline(repository=repository)
s3_client = boto3.client("s3")

RESULT_BUCKET = os.environ.get("S3_RESULT_BUCKET", "silversync-results-379995600109")
print(f"Pipeline initialized. Target S3 Bucket: {RESULT_BUCKET}")

def convert_decimal(obj):
    if isinstance(obj, list):
        return [convert_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    return obj

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 else int(obj)
        return super(DecimalEncoder, self).default(obj)

def handler(event: dict, context) -> dict:
    print(f"Received event: {json.dumps(event)}")

    try:
        body = json.loads(event.get("body", "{}"))
        patient_id = body.get("patient_id")

        if not patient_id:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "patient_id is required in the request body"}),
            }

        # 🚨 [수술 완료] pipeline.py 명세서에 적힌 그대로 'patient_search' 이름표를 붙여줍니다!
        result = pipeline.run(patient_search=patient_id)
        
        cleaned_result = convert_decimal(result)
        json_result = to_jsonable(cleaned_result)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_key = f"results/{patient_id}/{timestamp}.json"
        
        try:
            s3_client.put_object(
                Bucket=RESULT_BUCKET,
                Key=file_key,
                Body=json.dumps(json_result, cls=DecimalEncoder, ensure_ascii=False, indent=2),
                ContentType="application/json"
            )
            print(f"Successfully uploaded result to s3://{RESULT_BUCKET}/{file_key}")
        except Exception as s3_err:
            print(f"S3 Upload Failed: {s3_err}")

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
        print(error_message)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": error_message}),
        }