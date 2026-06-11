from __future__ import annotations

import json
from typing import Any

from .config import PACKAGE_DIR, SETTINGS
from .schemas import GuidelineEvidence, PatientSnapshot, VisitRecord
from .utils import _to_int, normalize_date, to_float


class MongoRepository:
    def __init__(self):
        self._client = None
        self._db = None
        self._retriever = None
        self._supabase = None
        self._embedding = None
        self.offline = False
        self.use_dummy_patients = False
        self.dummy_patients_path = PACKAGE_DIR / "dummy_patients.json"

    @property
    def db(self):
        if self._db is None:
            if not SETTINGS.mongo_uri:
                raise RuntimeError("MONGO_URI가 설정되어 있지 않습니다.")
            import certifi
            from pymongo import MongoClient

            self._client = MongoClient(
                SETTINGS.mongo_uri,
                tls=True,
                tlsCAFile=certifi.where(),
            )
            self._db = self._client[SETTINGS.db_name]
        return self._db

    def find_patient(self, search_input: str) -> dict[str, Any] | None:
        patient = self.db["patients"].find_one({"patient_id": search_input})
        if not patient:
            patient = self.db["patients"].find_one(
                {"name": {"$regex": search_input, "$options": "i"}}
            )
        return patient

    def get_visit_records(self, patient_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return list(
            self.db["visit_records"]
            .find({"patient_id": patient_id})
            .sort("visit_date", -1)
            .limit(limit)
        )

    def load_patient_snapshot(self, search_input: str) -> PatientSnapshot:
        if self.offline:
            return sample_diabetes_hypertension_patient()
        if self.use_dummy_patients:
            return self.load_dummy_patient_snapshot(search_input)
        patient = self.find_patient(search_input)
        if not patient:
            raise ValueError(f"환자를 찾을 수 없습니다: {search_input}")
        records = [self._record_from_mongo(row) for row in self.get_visit_records(patient["patient_id"])]
        return PatientSnapshot(
            patient_id=str(patient.get("patient_id", "")),
            name=str(patient.get("name", "")),
            age=patient.get("age"),
            gender=patient.get("gender"),
            conditions=list(patient.get("conditions", [])),
            medications=list(patient.get("medications", [])),
            records=records,
            overrides=list(patient.get("overrides", patient.get("disagreement_events", []))),
            diagnoses=list(patient.get("diagnoses", [])),
            medication_adherence_days=patient.get("medication_adherence_days"),
            regular_care=patient.get("regular_care"),
            raw=patient,
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
        if SETTINGS.rag_backend == "supabase":
            return self._retrieve_supabase_guidelines(query, top_k)
        try:
            if self._retriever is None:
                from langchain_huggingface import HuggingFaceEmbeddings
                from langchain_mongodb import MongoDBAtlasVectorSearch

                embeddings = HuggingFaceEmbeddings(model_name=SETTINGS.embedding_model)
                vector_search = MongoDBAtlasVectorSearch(
                    collection=self.db["knowledge_base"],
                    embedding=embeddings,
                    index_name=SETTINGS.vector_index_name,
                )
                self._retriever = vector_search.as_retriever(
                    search_kwargs={"k": top_k or SETTINGS.guideline_top_k}
                )
            docs = self._retriever.invoke(query)
            return [
                GuidelineEvidence(
                    source=str(doc.metadata.get("source", "knowledge_base")),
                    content=doc.page_content[:1200],
                )
                for doc in docs
            ]
        except Exception:
            return []

    def search_drug_interactions_for_meds(self, medications: list[str]) -> list[str]:
        alerts: list[str] = []
        if self.offline:
            return alerts
        if len(medications) < 2:
            return alerts
        if SETTINGS.rag_backend == "supabase":
            return self._search_supabase_drug_rows(medications)
        try:
            collection = self.db["drug_interactions"]
            for med in medications:
                if not med or len(med) < 2:
                    continue
                rows = list(
                    collection.find(
                        {
                            "$or": [
                                {"성분명A": {"$regex": med, "$options": "i"}},
                                {"성분명B": {"$regex": med, "$options": "i"}},
                            ]
                        },
                        {"_id": 0, "성분명A": 1, "성분명B": 1, "상세정보": 1},
                        limit=3,
                    )
                )
                for row in rows:
                    alerts.append(
                        f"{row.get('성분명A')} + {row.get('성분명B')}: {row.get('상세정보')}"
                    )
        except Exception:
            return alerts
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
        available = ", ".join(patient.get("patient_id", "") for patient in patients)
        raise ValueError(f"더미 환자를 찾을 수 없습니다: {search_input}. 사용 가능: {available}")

    def _snapshot_from_dummy(self, patient: dict[str, Any]) -> PatientSnapshot:
        records = [
            self._record_from_mongo(record)
            for record in patient.get("visit_records", patient.get("records", []))
        ]
        return PatientSnapshot(
            patient_id=str(patient.get("patient_id", "")),
            name=str(patient.get("name", "")),
            age=patient.get("age"),
            gender=patient.get("gender"),
            conditions=list(patient.get("conditions", [])),
            medications=list(patient.get("medications", [])),
            records=records,
            overrides=list(patient.get("overrides", [])),
            diagnoses=list(patient.get("diagnoses", [])),
            medication_adherence_days=patient.get("medication_adherence_days"),
            regular_care=patient.get("regular_care"),
            raw=patient,
        )

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

    def _retrieve_supabase_guidelines(
        self,
        query: str,
        top_k: int | None = None,
    ) -> list[GuidelineEvidence]:
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
        except Exception:
            try:
                response = (
                    self.supabase.table(SETTINGS.supabase_table)
                    .select("content, metadata")
                    .limit(top_k or SETTINGS.guideline_top_k)
                    .execute()
                )
                rows = response.data or []
            except Exception:
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

    def _search_supabase_drug_rows(self, medications: list[str]) -> list[str]:
        alerts: list[str] = []
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
        except Exception:
            return alerts
        return list(dict.fromkeys(alerts))

    def _record_from_mongo(self, row: dict[str, Any]) -> VisitRecord:
        vitals = row.get("vital_signs", {}) or {}

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
            symptoms=list(row.get("symptoms", vitals.get("symptoms", [])) or []),
            raw=row,
        )


def sample_diabetes_hypertension_patient() -> PatientSnapshot:
    records = [
        VisitRecord("2026-05-01", "정기 재진", "148/92", 168, 7.6, "운동 감소, 식이 불규칙"),
        VisitRecord("2026-04-24", "자가 측정 확인", "142/88", 156, None, ""),
        VisitRecord("2026-04-17", "정기 재진", "136/84", 146, 7.4, ""),
        VisitRecord("2026-04-10", "정기 재진", "132/82", 141, None, ""),
    ]
    return PatientSnapshot(
        patient_id="SAMPLE-DMHTN-001",
        name="샘플환자",
        age=72,
        gender="F",
        conditions=["당뇨병", "고혈압"],
        medications=["메트포르민", "암로디핀", "로수바스타틴"],
        records=records,
        overrides=[
            {
                "event": "doctor_override",
                "ai_recommendation": "대면",
                "doctor_decision": "비대면 유지",
                "doctor_reason": "명절 이후 식이 변화로 판단",
            }
        ],
    )
