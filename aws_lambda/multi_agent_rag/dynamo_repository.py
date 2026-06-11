from __future__ import annotations

import json
import math
import os
from decimal import Decimal
from typing import Any

import boto3

from .config import PACKAGE_DIR, SETTINGS
from .schemas import GuidelineEvidence, PatientSnapshot, VisitRecord
from .utils import _to_int, normalize_date, to_float


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _to_float_list(value: Any) -> list[float] | None:
    if not value:
        return None
    try:
        return [float(x) for x in value]
    except (TypeError, ValueError):
        return None


class DynamoRepository:
    def __init__(self):
        self._dynamo = None
        self._bedrock = None
        self.offline = False
        self.use_dummy_patients = False
        self.dummy_patients_path = PACKAGE_DIR / "dummy_patients.json"
        self.patients_table = os.environ.get("DYNAMODB_TABLE_NAME", "SilverSyncPatients")
        self.knowledge_base_table = os.environ.get(
            "DYNAMODB_GUIDELINES_TABLE_NAME", "SilverSyncGuidelines"
        )
        self.embedding_model_id = os.environ.get(
            "EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0"
        )

    @property
    def dynamo(self):
        if self._dynamo is None:
            self._dynamo = boto3.resource("dynamodb", region_name=SETTINGS.bedrock_region)
        return self._dynamo

    @property
    def bedrock(self):
        if self._bedrock is None:
            self._bedrock = boto3.client(
                "bedrock-runtime", region_name=SETTINGS.bedrock_region
            )
        return self._bedrock

    def _embed(self, text: str) -> list[float]:
        response = self.bedrock.invoke_model(
            modelId=self.embedding_model_id,
            body=json.dumps({"inputText": text[:8000]}),
            contentType="application/json",
            accept="application/json",
        )
        body = json.loads(response["body"].read())
        return body["embedding"]

    def find_patient(self, search_input: str) -> dict[str, Any] | None:
        table = self.dynamo.Table(self.patients_table)
        response = table.get_item(Key={"patient_id": search_input})
        return response.get("Item")

    def get_visit_records(self, patient_id: str, limit: int = 10) -> list[dict[str, Any]]:
        patient = self.find_patient(patient_id)
        if not patient:
            return []
        records = patient.get("visit_records") or patient.get("records") or []
        return list(records)[:limit]

    def load_patient_snapshot(self, search_input: str) -> PatientSnapshot:
        if self.offline:
            from .repository import sample_diabetes_hypertension_patient
            return sample_diabetes_hypertension_patient()
        if self.use_dummy_patients:
            return self.load_dummy_patient_snapshot(search_input)
        patient = self.find_patient(search_input)
        if not patient:
            raise ValueError(f"환자를 찾을 수 없습니다: {search_input}")
        raw_records = patient.get("visit_records") or patient.get("records") or []
        records = [self._record_from_item(row) for row in raw_records]
        return PatientSnapshot(
            patient_id=str(patient.get("patient_id", "")),
            name=str(patient.get("name", "")),
            age=_dynamo_int(patient.get("age")),
            gender=patient.get("gender"),
            conditions=list(patient.get("conditions") or []),
            medications=list(patient.get("medications") or []),
            records=records,
            overrides=list(patient.get("overrides") or patient.get("disagreement_events") or []),
            diagnoses=list(patient.get("diagnoses") or []),
            medication_adherence_days=_dynamo_int(patient.get("medication_adherence_days")),
            regular_care=patient.get("regular_care"),
            raw=dict(patient),
        )

    def retrieve_guidelines(self, query: str, top_k: int | None = None) -> list[GuidelineEvidence]:
        if self.offline:
            return [
                GuidelineEvidence(
                    source="offline_sample_guideline",
                    content=(
                        "당뇨병과 고혈압을 동반한 고령 환자는 최근 혈당, HbA1c, "
                        "혈압 추세, 증상, 복약 순응도, 약물 상호작용을 함께 검토해야 한다."
                    ),
                )
            ]
        k = top_k or SETTINGS.guideline_top_k
        try:
            query_embedding = self._embed(query)
            table = self.dynamo.Table(self.knowledge_base_table)
            items: list[dict] = []
            scan_kwargs: dict[str, Any] = {
                "ProjectionExpression": "content, #src, metadata, embedding",
                "ExpressionAttributeNames": {"#src": "source"},
            }
            response = table.scan(**scan_kwargs)
            items.extend(response.get("Items", []))
            while "LastEvaluatedKey" in response and len(items) < 2000:
                scan_kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
                response = table.scan(**scan_kwargs)
                items.extend(response.get("Items", []))

            scored: list[tuple[float, dict]] = []
            for item in items:
                emb = _to_float_list(item.get("embedding"))
                if not emb:
                    continue
                score = _cosine_similarity(query_embedding, emb)
                scored.append((score, item))
            scored.sort(key=lambda x: x[0], reverse=True)

            evidence: list[GuidelineEvidence] = []
            for _, item in scored[:k]:
                metadata = item.get("metadata") or {}
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except Exception:
                        metadata = {}
                source = (
                    metadata.get("source_path")
                    or metadata.get("source")
                    or item.get("source")
                    or "dynamodb_knowledge_base"
                )
                evidence.append(
                    GuidelineEvidence(
                        source=str(source),
                        content=str(item.get("content", ""))[:1200],
                    )
                )
            return evidence
        except Exception:
            return []

    def search_drug_interactions_for_meds(self, medications: list[str]) -> list[str]:
        if self.offline or len(medications) < 2:
            return []
        alerts: list[str] = []
        try:
            table = self.dynamo.Table(self.knowledge_base_table)
            for med in medications[:3]:
                if not med or len(med) < 2:
                    continue
                response = table.scan(
                    FilterExpression="contains(content, :med)",
                    ExpressionAttributeValues={":med": med},
                    Limit=5,
                )
                for item in response.get("Items", []):
                    content = str(item.get("content", ""))
                    metadata = item.get("metadata") or {}
                    if isinstance(metadata, str):
                        try:
                            metadata = json.loads(metadata)
                        except Exception:
                            metadata = {}
                    source = str(metadata.get("source", ""))
                    if (
                        "병용금기" in source
                        or "DUR" in source
                        or "drug" in source.lower()
                        or "상호작용" in content
                    ):
                        alerts.append(content[:500])
        except Exception:
            pass
        return list(dict.fromkeys(alerts))

    def load_dummy_patient_snapshot(self, search_input: str) -> PatientSnapshot:
        patients = json.loads(self.dummy_patients_path.read_text(encoding="utf-8"))
        normalized = search_input.lower()
        for patient in patients:
            if (
                str(patient.get("patient_id", "")).lower() == normalized
                or str(patient.get("name", "")).lower() == normalized
            ):
                return self._snapshot_from_dummy(patient)
        available = ", ".join(p.get("patient_id", "") for p in patients)
        raise ValueError(f"더미 환자를 찾을 수 없습니다: {search_input}. 사용 가능: {available}")

    def _snapshot_from_dummy(self, patient: dict[str, Any]) -> PatientSnapshot:
        records = [
            self._record_from_item(r)
            for r in patient.get("visit_records") or patient.get("records") or []
        ]
        return PatientSnapshot(
            patient_id=str(patient.get("patient_id", "")),
            name=str(patient.get("name", "")),
            age=patient.get("age"),
            gender=patient.get("gender"),
            conditions=list(patient.get("conditions") or []),
            medications=list(patient.get("medications") or []),
            records=records,
            overrides=list(patient.get("overrides") or []),
            diagnoses=list(patient.get("diagnoses") or []),
            medication_adherence_days=patient.get("medication_adherence_days"),
            regular_care=patient.get("regular_care"),
            raw=patient,
        )

    def _record_from_item(self, row: dict[str, Any]) -> VisitRecord:
        vitals = row.get("vital_signs") or {}

        def pick(key: str) -> Any:
            return vitals.get(key) if vitals.get(key) is not None else row.get(key)

        fasting = to_float(pick("fasting_glucose"))
        postprandial = to_float(pick("postprandial_glucose"))
        blood_sugar = to_float(pick("blood_sugar"))
        return VisitRecord(
            visit_date=normalize_date(row.get("visit_date")),
            chief_complaint=str(row.get("chief_complaint", "")),
            blood_pressure=vitals.get("blood_pressure") or row.get("blood_pressure"),
            blood_sugar=blood_sugar if blood_sugar is not None else fasting,
            hba1c=to_float(vitals.get("hba1c") or vitals.get("HbA1c") or row.get("hba1c")),
            notes=str(row.get("notes", "")),
            pulse=_to_int(pick("pulse")),
            fasting_glucose=fasting,
            postprandial_glucose=postprandial,
            bmi=to_float(pick("bmi")),
            waist_circumference=to_float(pick("waist_circumference")),
            total_cholesterol=to_float(pick("total_cholesterol")),
            triglyceride=to_float(pick("triglyceride")),
            hdl=to_float(pick("hdl")),
            ldl=to_float(pick("ldl")),
            symptoms=list(row.get("symptoms") or vitals.get("symptoms") or []),
            raw=row,
        )


def _dynamo_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
