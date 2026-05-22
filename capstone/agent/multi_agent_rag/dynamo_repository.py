from __future__ import annotations

from typing import Any
import json
import numpy as np
import boto3
from boto3.dynamodb.conditions import Attr
import os

from .config import SETTINGS
from .schemas import GuidelineEvidence, PatientSnapshot, VisitRecord
from .utils import to_float


class DynamoRepository:
    def __init__(self):
        self.aws_region = os.environ.get("BEDROCK_REGION", "ap-northeast-2")
        self.dynamodb = boto3.resource("dynamodb", region_name=self.aws_region)
        self.dynamodb_client = boto3.client("dynamodb", region_name=self.aws_region)
        self.bedrock_client = boto3.client("bedrock-runtime", region_name=self.aws_region)

        self.table_name = os.environ.get("DYNAMODB_TABLE_NAME", "SilverSyncPatients")
        self.table = self.dynamodb.Table(self.table_name)

        self.guidelines_table_name = os.environ.get("DYNAMODB_GUIDELINES_TABLE_NAME", "SilverSyncGuidelines")
        self.guidelines_table = self.dynamodb.Table(self.guidelines_table_name)

    def load_patient_snapshot(self, patient_id: str) -> PatientSnapshot:
        if not patient_id:
            raise ValueError("DynamoDB에서 조회할 patient_id가 필요합니다.")

        try:
            response = self.table.get_item(Key={"patient_id": patient_id})
        except Exception as e:
            raise RuntimeError(f"DynamoDB 통신 중 오류가 발생했습니다: {e}") from e

        item = response.get("Item")
        if not item:
            raise ValueError(f"DynamoDB에 ID가 '{patient_id}'인 환자 데이터가 없습니다.")

        return self._snapshot_from_db(item)

    def _snapshot_from_db(self, item: dict[str, Any]) -> PatientSnapshot:
        raw_records = item.get("records", [])
        converted_records = [
            VisitRecord(
                visit_date=str(r.get("visit_date", "N/A")),
                chief_complaint=str(r.get("chief_complaint", "")),
                blood_pressure=r.get("blood_pressure"),
                blood_sugar=to_float(r.get("blood_sugar")),
                hba1c=to_float(r.get("hba1c")),
                notes=str(r.get("notes", "")),
                raw=r
            ) for r in raw_records
        ]

        return PatientSnapshot(
            patient_id=str(item.get("patient_id", "")),
            name=str(item.get("name", "")),
            age=int(item.get("age")) if item.get("age") else None,
            gender=item.get("gender"),
            conditions=list(item.get("conditions", [])),
            medications=list(item.get("medications", [])),
            records=converted_records,
            overrides=list(item.get("overrides", [])),
            raw=item
        )

    def retrieve_guidelines(self, query: str, top_k: int | None = None) -> list[GuidelineEvidence]:
        try:
            query_embedding = self._get_bedrock_embedding(query)
            
            # 카테고리 필터링 스캔으로 탐색 효율 유지
            response = self.guidelines_table.scan(
                FilterExpression=Attr('category').is_in(['CLINICAL_GUIDELINE', 'DUR_CONTRAINDICATION', 'ELDERLY_CAUTION']),
                ProjectionExpression="item_id,content, embedding, metadata"
            )   
            items = response.get("Items", [])   

            scored_items = []
            for item in items:
                if "embedding" in item and "content" in item:
                    try:
                        stored_embedding_raw = item["embedding"]
                        
                        if isinstance(stored_embedding_raw, str):
                            stored_embedding = json.loads(stored_embedding_raw)
                        elif isinstance(stored_embedding_raw, list):
                            # Decimal 데이터 포맷을 순수 float 리스트로 완벽 강제 다운캐스팅 처리
                            stored_embedding = [float(x) for x in stored_embedding_raw]
                        else:
                            continue
                        
                        similarity = self._cosine_similarity(query_embedding, stored_embedding)
                        scored_items.append((similarity, item))
                    except Exception as inner_e:
                        print(f"        [RAG Debug] 임베딩 파싱/유사도 계산 중 오류: {inner_e}, 항목: {item.get('guideline_id', 'N/A')}")
                        continue
                else:
                    print(f"        [RAG Debug] 항목에 'embedding' 또는 'content' 필드 누락: {item.keys()} for item: {item.get('item_id', 'N/A')}")

            
            scored_items.sort(key=lambda x: x[0], reverse=True)
            top_k_limit = top_k or SETTINGS.guideline_top_k
            top_k_items = scored_items[:top_k_limit]
            rows = [item for similarity, item in top_k_items]
            
        except Exception as e:
            print(f"DynamoDB RAG 검색 실패: {e}")
            return []

        evidence: list[GuidelineEvidence] = []
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            source = metadata.get("source_path") or metadata.get("source") or "dynamodb_guidelines"
            evidence.append(
                GuidelineEvidence(
                    source=str(source),
                    content=str(row.get("content", ""))[:1200],
                )
            )
        return evidence

    def search_drug_interactions_for_meds(self, medications: list[str]) -> list[str]:
        alerts: list[str] = []
        if len(medications) < 2:
            return alerts

        try:
            response = self.guidelines_table.scan(
                FilterExpression=Attr('category').is_in(['DUR_CONTRAINDICATION', 'ELDERLY_CAUTION']),
                ProjectionExpression="content, ingredient, metadata"
            )
            dur_items = response.get("Items", [])

            for med in medications:
                if not med or len(med) < 2: continue
                
                for item in dur_items:
                    content_str = str(item.get("content", ""))
                    ing_str = str(item.get("ingredient", ""))
                    
                    if med.lower() in content_str.lower() or med.lower() in ing_str.lower():
                        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
                        source = str(metadata.get("source", ""))
                        alerts.append(f"[{source or 'DUR_ALERT'}] {content_str[:500]}")
                        
        except Exception as e:
            print(f"DynamoDB DUR 검색 오류: {e}")
            return alerts
            
        return list(dict.fromkeys(alerts))
    
    def _cosine_similarity(self, vec1: list[float] | np.ndarray, vec2: list[float] | np.ndarray) -> float:
        # 데이터 정밀도 형변환 예외 차단 (float 타입 강제)
        v1 = np.array(vec1, dtype=float)
        v2 = np.array(vec2, dtype=float)
        dot_product = np.dot(v1, v2)
        norm_a = np.linalg.norm(v1)
        norm_b = np.linalg.norm(v2)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot_product / (norm_a * norm_b))

    def _get_bedrock_embedding(self, text: str) -> list[float]:
        input_text = text.strip() if text and text.strip() else "Empty query"
        body = json.dumps({
            "inputText": input_text,
            "dimensions": 1024
        }).encode("utf-8")
        
        # config.py에 설정된 모델 ID(예: amazon.titan-embed-text-v2:0)를 사용하여 호출
        response = self.bedrock_client.invoke_model(
            body=body,
            modelId=SETTINGS.embedding_model,
            accept="application/json",
            contentType="application/json"
        )
        
        response_body = json.loads(response.get("body").read())

        # Titan 임베딩 모델 토큰 사용량 추출 및 즉시 출력
        input_tokens = response_body.get("inputTextTokenCount", 0)
        if input_tokens > 0:
            print(f"    └── [Titan 임베딩 토큰] 입력: {input_tokens:,}", flush=True)

        embedding = response_body.get("embedding")
        return [float(x) for x in embedding]