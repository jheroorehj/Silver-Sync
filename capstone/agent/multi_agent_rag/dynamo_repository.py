from __future__ import annotations

import os
from typing import Any

import boto3

from .config import SETTINGS
from .schemas import GuidelineEvidence, PatientSnapshot, VisitRecord
from .utils import to_float


class DynamoRepository:
    """
    클라우드 환경을 위한 리포지토리입니다.
    - 환자 데이터: AWS DynamoDB
    - RAG (가이드라인, DUR): Supabase
    """

    def __init__(self):
        # DynamoDB 클라이언트
        self.dynamodb = boto3.resource(
            "dynamodb",
            region_name=os.environ.get("BEDROCK_REGION", "ap-northeast-2")
        )
        self.table_name = os.environ.get("DYNAMODB_TABLE_NAME", "SilverSyncPatients")
        self.table = self.dynamodb.Table(self.table_name)

        # Supabase 클라이언트
        self._supabase = None
        self._embedding = None

    def load_patient_snapshot(self, patient_id: str) -> PatientSnapshot:
        if not patient_id:
            raise ValueError("DynamoDB에서 조회할 patient_id가 필요합니다.")

        print(f"Fetching patient '{patient_id}' from DynamoDB table '{self.table_name}'...")
        try:
            response = self.table.get_item(Key={"patient_id": patient_id})
        except Exception as e:
            raise RuntimeError(f"DynamoDB 통신 중 오류가 발생했습니다: {e}") from e

        item = response.get("Item")
        if not item:
            raise ValueError(f"DynamoDB에 ID가 '{patient_id}'인 환자 데이터가 없습니다.")

        return self._snapshot_from_db(item)

    def _snapshot_from_db(self, item: dict[str, Any]) -> PatientSnapshot:
        """DynamoDB의 dict 데이터를 PatientSnapshot 객체로 변환"""
        # records 내의 각 dict를 VisitRecord 객체로 변환
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
            query_embedding = self.embedding.embed_query(query)
            response = self.supabase.rpc(
                SETTINGS.supabase_match_fn,
                {
                    "query_embedding": query_embedding,
                    "match_count": top_k or SETTINGS.guideline_top_k,
                },
            ).execute()
            rows = response.data or []
        except Exception as e:
            print(f"Supabase RAG 검색 중 오류가 발생했습니다: {e}")
            return []

        evidence: list[GuidelineEvidence] = []
        for row in rows:
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            source = metadata.get("source_path") or metadata.get("source") or "supabase_knowledge_base"
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
            for med in medications:
                if not med or len(med) < 2:
                    continue
                response = (
                    self.supabase.table(SETTINGS.supabase_table)
                    .select("content, metadata")
                    .ilike("content", f"%{med}%")
                    .limit(3)
                    .execute()
                )
                for row in response.data or []:
                    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                    source = str(metadata.get("source", ""))
                    if "병용금기" in source or "DUR" in source or "drug" in source.lower():
                        alerts.append(str(row.get("content", ""))[:500])
        except Exception as e:
            print(f"Supabase DUR 검색 중 오류가 발생했습니다: {e}")
            return alerts
        return list(dict.fromkeys(alerts))

    @property
    def supabase(self):
        if self._supabase is None:
            if not SETTINGS.supabase_url or not SETTINGS.supabase_key:
                raise RuntimeError("SUPABASE_URL 또는 SUPABASE_KEY가 설정되어 있지 않습니다.")
            from supabase import create_client

            self._supabase = create_client(SETTINGS.supabase_url, SETTINGS.supabase_key)
        return self._supabase

    @property
    def embedding(self):
        if self._embedding is None:
            from langchain_huggingface import HuggingFaceEmbeddings

            self._embedding = HuggingFaceEmbeddings(model_name=SETTINGS.embedding_model)
        return self._embedding
