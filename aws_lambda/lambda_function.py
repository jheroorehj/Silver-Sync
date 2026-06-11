from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3


class _DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, cls=_DecimalEncoder)


# multi_agent_rag 패키지가 agent/ 하위에 있으므로 런타임 경로에 추가
_agent_path = os.path.join(os.path.dirname(__file__), 'agent')
if _agent_path not in sys.path:
    sys.path.insert(0, _agent_path)

KST = timezone(timedelta(hours=9))


def lambda_handler(event, context):
    # 비동기 백그라운드 실행 — Lambda가 자기 자신을 async로 호출한 경우
    if event.get("_async_run"):
        return _run_pipeline(event)

    body = event.get("body", "{}")
    if isinstance(body, str):
        body = json.loads(body)

    # API Gateway 직접 호출 여부: requestContext가 있으면 API Gateway
    from_api_gateway = "requestContext" in event
    http_method = event.get("httpMethod", "")
    path = event.get("path", "")

    # GET /result — S3에서 결과 조회
    if from_api_gateway and http_method == "GET" and path.startswith("/result"):
        return _get_result(event)

    # GET /patient — DynamoDB에서 환자 기본 정보 조회
    if from_api_gateway and http_method == "GET" and path.startswith("/patient"):
        return _get_patient(event)

    # Lambda 직접 호출 — 동기 실행 후 즉시 결과 반환
    if not from_api_gateway:
        patient_id = (body.get("patient_id") or event.get("patient_id", ""))
        if not patient_id:
            return _error(400, "patient_id is required")
        visit_vitals = body.get("visit_vitals") or event.get("visit_vitals")
        bucket = os.environ.get("S3_RESULT_BUCKET", "")
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        job_id = uuid.uuid4().hex[:12]
        s3_key = f"results/{patient_id}/{timestamp}_{job_id}.json"
        return _run_pipeline({
            "patient_id": patient_id,
            "s3_key": s3_key,
            "bucket": bucket,
            "visit_vitals": visit_vitals,
        })

    # API Gateway로부터 온 동기 요청 — 즉시 202 반환 후 백그라운드 실행
    try:
        patient_id = body.get("patient_id", "")
        if not patient_id:
            return _error(400, "patient_id is required")

        visit_vitals = body.get("visit_vitals")  # 간호사 측정값
        bucket = os.environ["S3_RESULT_BUCKET"]
        job_id = uuid.uuid4().hex[:12]
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        s3_key = f"results/{patient_id}/{timestamp}_{job_id}.json"

        boto3.client("lambda", region_name=os.environ.get("BEDROCK_REGION", "ap-northeast-2")).invoke(
            FunctionName=context.function_name,
            InvocationType="Event",
            Payload=json.dumps(
                {
                    "_async_run": True,
                    "patient_id": patient_id,
                    "s3_key": s3_key,
                    "bucket": bucket,
                    "visit_vitals": visit_vitals,  # 비동기 실행에 전달
                }
            ).encode(),
        )

        return {
            "statusCode": 202,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {"patient_id": patient_id, "s3_key": s3_key, "s3_bucket": bucket, "status": "processing"},
                ensure_ascii=False,
            ),
        }
    except KeyError as exc:
        return _error(500, f"환경변수 누락: {exc}")
    except Exception:
        return _error(500, traceback.format_exc())


def _upsert_visit(patient_id: str, visit_vitals: dict) -> None:
    """간호사 측정값을 오늘 날짜 방문 기록으로 upsert.

    DynamoRepository._snapshot_from_db 가 읽는 필드명/구조에 맞춤:
      - DynamoDB 필드: "records"  (※ visit_records 아님)
      - 레코드 내 vitals 는 루트 레벨 flat 구조  (blood_pressure, blood_sugar)
    """
    today = datetime.now(tz=KST).strftime("%Y-%m-%d")

    systolic = visit_vitals.get("systolic")
    diastolic = visit_vitals.get("diastolic")
    blood_sugar = visit_vitals.get("blood_sugar")

    note_parts = []
    med = visit_vitals.get("medication_status")
    if med == "missed":
        note_parts.append("복약 누락 있음")
    elif med == "well":
        note_parts.append("복약 정상")
    raw_notes = (visit_vitals.get("notes") or "").strip()
    if raw_notes:
        note_parts.append(raw_notes)

    observations = list(visit_vitals.get("observations") or [])

    # DynamoRepository 가 읽는 flat 구조
    new_record: dict = {
        "visit_date": today,
        "chief_complaint": "방문 간호 기록",
        "notes": " / ".join(note_parts) if note_parts else "",
    }
    if systolic and diastolic:
        new_record["blood_pressure"] = f"{int(systolic)}/{int(diastolic)}"
    if blood_sugar:
        new_record["blood_sugar"] = Decimal(str(blood_sugar))
    if observations:
        new_record["symptoms"] = observations

    table_name = os.environ.get("DYNAMODB_TABLE_NAME", "SilverSyncPatients")
    region = os.environ.get("BEDROCK_REGION", "ap-northeast-2")
    table = boto3.resource("dynamodb", region_name=region).Table(table_name)

    # 기존 records + visit_records 모두 조회
    resp = table.get_item(
        Key={"patient_id": patient_id},
        ProjectionExpression="#r, visit_records",
        ExpressionAttributeNames={"#r": "records"},
    )
    item = resp.get("Item", {})
    records = list(item.get("records") or [])

    # records 가 비어있으면 visit_records 를 레포지토리 형식으로 변환해서 채움
    if not records:
        for vr in (item.get("visit_records") or []):
            vs = vr.get("vital_signs") or {}
            rec: dict = {
                "visit_date": str(vr.get("visit_date", "")),
                "chief_complaint": str(vr.get("chief_complaint", "")),
                "notes": str(vr.get("notes", "")),
            }
            bp = vs.get("blood_pressure")
            if bp:
                rec["blood_pressure"] = str(bp)
            bs = vs.get("blood_sugar") or vs.get("fasting_glucose")
            if bs:
                rec["blood_sugar"] = Decimal(str(bs))
            hba1c = vs.get("hba1c")
            if hba1c:
                rec["hba1c"] = Decimal(str(hba1c))
            syms = vr.get("symptoms")
            if syms:
                rec["symptoms"] = list(syms)
            records.append(rec)

    # 오늘 날짜 레코드가 있으면 덮어쓰기, 없으면 맨 앞에 삽입
    for i, rec in enumerate(records):
        if str(rec.get("visit_date", "")) == today:
            records[i] = new_record
            break
    else:
        records.insert(0, new_record)

    table.update_item(
        Key={"patient_id": patient_id},
        UpdateExpression="SET #r = :records",
        ExpressionAttributeNames={"#r": "records"},
        ExpressionAttributeValues={":records": records},
    )


def _run_pipeline(event: dict) -> dict:
    patient_id = event.get("patient_id", "")
    s3_key = event.get("s3_key", "")
    bucket = event.get("bucket", os.environ.get("S3_RESULT_BUCKET", ""))
    visit_vitals = event.get("visit_vitals")

    try:
        # 간호사 측정값이 있으면 파이프라인 실행 전 DynamoDB에 먼저 반영
        if visit_vitals and patient_id:
            _upsert_visit(patient_id, visit_vitals)

        os.environ.setdefault("LLM_PROVIDER", "bedrock")

        from multi_agent_rag.dynamo_repository import DynamoRepository
        from multi_agent_rag.pipeline import MultiAgentRevisitPipeline
        from multi_agent_rag.schemas import to_jsonable

        repo = DynamoRepository()
        pipeline = MultiAgentRevisitPipeline(repository=repo)
        result = pipeline.run(patient_search=patient_id)

        result_data = to_jsonable(result)
        judge = result.judge

        meta = {
            "patient_id": patient_id,
            "consultation_type": judge.consultation_type.value,
            "verdict_level": judge.verdict_level.value,
            "risk_score": judge.risk_score,
            "confidence": judge.confidence,
            "status": "done",
        }
        payload = {**result_data, "_meta": meta}

        if bucket and s3_key:
            boto3.client("s3").put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=_dumps(payload).encode("utf-8"),
                ContentType="application/json; charset=utf-8",
            )

        return {"statusCode": 200, "body": _dumps(meta)}
    except Exception:
        try:
            boto3.client("s3").put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=json.dumps(
                    {"_meta": {"status": "error", "patient_id": patient_id, "detail": traceback.format_exc()}},
                    ensure_ascii=False,
                ).encode("utf-8"),
                ContentType="application/json; charset=utf-8",
            )
        except Exception:
            pass
        return {"statusCode": 500}


def _get_result(event: dict) -> dict:
    params = event.get("queryStringParameters") or {}
    s3_key = params.get("s3_key", "")
    if not s3_key:
        return _error(400, "s3_key query parameter is required")
    bucket = os.environ["S3_RESULT_BUCKET"]
    try:
        obj = boto3.client("s3").get_object(Bucket=bucket, Key=s3_key)
        data = json.loads(obj["Body"].read())
        meta = data.get("_meta", {})
        status = meta.get("status", "processing")
        if status == "done":
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps(meta, ensure_ascii=False),
            }
        return {
            "statusCode": 202,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps(meta, ensure_ascii=False),
        }
    except Exception as exc:
        if "NoSuchKey" in str(exc):
            return {
                "statusCode": 202,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"status": "processing"}, ensure_ascii=False),
            }
        return _error(500, str(exc))


def _get_patient(event: dict) -> dict:
    params = event.get("queryStringParameters") or {}
    patient_id = params.get("patient_id", "")
    if not patient_id:
        return _error(400, "patient_id is required")
    try:
        table_name = os.environ.get("DYNAMODB_TABLE_NAME", "SilverSyncPatients")
        region = os.environ.get("BEDROCK_REGION", "ap-northeast-2")
        table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        resp = table.get_item(Key={"patient_id": patient_id})
        patient = resp.get("Item")
        if not patient:
            return _error(404, f"Patient not found: {patient_id}")
        result = {
            "patient_id": str(patient.get("patient_id", "")),
            "name": str(patient.get("name", "")),
            "age": int(patient.get("age", 0)),
            "gender": str(patient.get("gender", "")),
            "conditions": [str(c) for c in (patient.get("conditions") or [])],
            "medications": [str(m) for m in (patient.get("medications") or [])],
        }
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps(result, ensure_ascii=False),
        }
    except Exception as exc:
        return _error(500, str(exc))


def _error(status: int, message: str) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"error": message}, ensure_ascii=False),
    }
