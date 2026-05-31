import json
import boto3
from decimal import Decimal
import os
from pathlib import Path

# DynamoDB는 Python의 float을 바로 받지 못하므로 Decimal로 변환하는 헬퍼 함수
def json_to_decimal(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: json_to_decimal(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [json_to_decimal(v) for v in obj if v is not None]
    return obj

def create_table_if_not_exists(dynamodb_client, table_name: str):
    """DynamoDB 테이블이 존재하지 않으면 생성하고 활성화될 때까지 기다립니다."""
    try:
        dynamodb_client.describe_table(TableName=table_name)
        print(f"테이블 '{table_name}'이 이미 존재합니다.")
    except dynamodb_client.exceptions.ResourceNotFoundException:
        print(f"테이블 '{table_name}'을 찾을 수 없습니다. 새로 생성합니다...")
        dynamodb_client.create_table(
            TableName=table_name,
            KeySchema=[{"AttributeName": "patient_id", "KeyType": "HASH"}],  # 파티션 키
            AttributeDefinitions=[{"AttributeName": "patient_id", "AttributeType": "S"}], # S = String
            BillingMode="PAY_PER_REQUEST",  # 사용한 만큼만 지불하는 온디맨드 모드
        )
        print(f"테이블 '{table_name}' 생성 중... 활성화될 때까지 기다립니다.")
        waiter = dynamodb_client.get_waiter("table_exists")
        waiter.wait(TableName=table_name)
        print(f"테이블 '{table_name}'이 성공적으로 생성 및 활성화되었습니다.")

def main():
    # 1. AWS 리전 및 DynamoDB 테이블 설정
    region = os.environ.get("BEDROCK_REGION", "ap-northeast-2")
    table_name = os.environ.get("DYNAMODB_TABLE_NAME", "SilverSyncPatients")
    
    # 테이블 생성 및 관리를 위한 client와 데이터 조작을 위한 resource를 모두 사용
    dynamodb_client = boto3.client("dynamodb", region_name=region)
    dynamodb_resource = boto3.resource("dynamodb", region_name=region)

    # 테이블이 없으면 자동으로 생성
    create_table_if_not_exists(dynamodb_client, table_name)
    table = dynamodb_resource.Table(table_name)
    
    # 2. 로컬 dummy_patients.json 파일 읽기
    file_path = Path("agent/multi_agent_rag/dummy_patients.json")
    if not file_path.exists():
        print(f"파일을 찾을 수 없습니다: {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        patients = json.load(f)

    # 3. 데이터 구조 변환 및 업로드
    print(f"총 {len(patients)}명의 환자 데이터를 {table_name} 테이블에 업로드합니다...")
    
    for p in patients:
        # 기존 visit_records 구조를 평탄화된 records 구조로 변환
        records = []
        for vr in p.get("visit_records", []):
            vitals = vr.get("vital_signs", {})
            record = {
                "visit_date": vr.get("visit_date"),
                "chief_complaint": vr.get("chief_complaint"),
                "notes": vr.get("notes"),
                "blood_pressure": vitals.get("blood_pressure") or vr.get("blood_pressure"),
                "blood_sugar": vitals.get("blood_sugar") or vr.get("blood_sugar"),
                "hba1c": vitals.get("hba1c") or vr.get("hba1c")
            }
            records.append(record)
            
        # DynamoDB용 아이템 생성
        item = {
            "patient_id": p.get("patient_id"),
            "name": p.get("name"),
            "age": p.get("age"),
            "gender": p.get("gender"),
            "conditions": p.get("conditions", []),
            "medications": p.get("medications", []),
            "overrides": p.get("overrides", []),
            "records": records
        }
        
        # float -> Decimal 변환 (boto3 필수 규칙)
        item = json_to_decimal(item)

        # DynamoDB에 쓰기
        try:
            table.put_item(Item=item)
            print(f"✅ 환자 업로드 성공: {item['name']} ({item['patient_id']})")
        except Exception as e:
            print(f"❌ 업로드 실패 ({item['patient_id']}): {e}")

    print("모든 업로드가 완료되었습니다!")

if __name__ == "__main__":
    main()
