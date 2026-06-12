from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, extract_json_object
from ..personas import DATA_CURATOR_PERSONA
from ..schemas import CuratedCase, PatientSnapshot
from ..utils import contains_any, latest_numeric, parse_blood_pressure, trend_delta_desc
from typing import Any


class DataCurator:
    """Collects raw patient data and turns it into a reliable working memory."""

    def __init__(self, repository: Any):
        self.repository = repository
        self.llm = LLMClient(model=SETTINGS.worker_model)

    def run(self, search_input: str | None = None) -> CuratedCase:
        # 람다 환경에서는 항상 실제 리포지토리(DynamoDB)를 통해 데이터를 가져옵니다.
        patient = self.repository.load_patient_snapshot(search_input or "")
        return self._curate(patient)

    def _curate(self, patient: PatientSnapshot) -> CuratedCase:
        condition_texts = patient.conditions
        has_diabetes = contains_any(condition_texts, ["당뇨", "diabetes", "dm"])
        has_hypertension = contains_any(condition_texts, ["고혈압", "hypertension", "htn"])

        bp_values = [parse_blood_pressure(record.blood_pressure) for record in patient.records]
        systolic_values = [bp[0] for bp in bp_values]
        diastolic_values = [bp[1] for bp in bp_values]
        sugar_values = [record.blood_sugar for record in patient.records]
        hba1c_values = [record.hba1c for record in patient.records]
        symptom_texts = [record.chief_complaint + " " + record.notes for record in patient.records[:3]]

        latest_systolic = latest_numeric(systolic_values)
        latest_diastolic = latest_numeric(diastolic_values)
        latest_sugar = latest_numeric(sugar_values)
        latest_hba1c = latest_numeric(hba1c_values)

        missing_items: list[str] = []
        if not has_diabetes:
            missing_items.append("당뇨병 진단명")
        if not has_hypertension:
            missing_items.append("고혈압 진단명")
        if len(patient.records) < 3:
            missing_items.append("최근 바이탈 3회 이상")
        if latest_systolic is None or latest_diastolic is None:
            missing_items.append("최근 혈압")
        if latest_sugar is None and latest_hba1c is None:
            missing_items.append("최근 혈당 또는 HbA1c")

        data_quality_score = 100
        data_quality_score -= len(missing_items) * 18
        if len(patient.records) < 5:
            data_quality_score -= 8
        if not patient.medications:
            data_quality_score -= 10
        data_quality_score = max(0, min(100, data_quality_score))

        signals = {
            "latest_systolic": latest_systolic,
            "latest_diastolic": latest_diastolic,
            "latest_blood_sugar": latest_sugar,
            "latest_hba1c": latest_hba1c,
            "systolic_delta": trend_delta_desc(systolic_values),
            "diastolic_delta": trend_delta_desc(diastolic_values),
            "blood_sugar_delta": trend_delta_desc(sugar_values),
            "record_count": len(patient.records),
            "medication_count": len(patient.medications),
            "recent_symptom_text": " / ".join(symptom_texts),
            "has_doctor_override": bool(patient.overrides),
        }

        notes = [
            "당뇨와 고혈압을 동시에 가진 재진 환자만 본 파이프라인의 1차 대상입니다.",
            f"데이터 신뢰도 점수: {data_quality_score}/100",
        ]
        if patient.overrides:
            notes.append("과거 의사 오버라이드가 있어 에피소드 메모리를 추론에 반영합니다.")

        model_output = self._model_data_quality_note(patient, signals, missing_items)
        parsed = extract_json_object(model_output)
        if parsed and isinstance(parsed.get("curator_notes"), list):
            notes.extend(str(item) for item in parsed["curator_notes"][:3])
        elif model_output:
            notes.append(model_output[:500])
        elif self.llm.last_error:
            notes.append(f"Data Curator 모델 호출 실패: {self.llm.last_error}")

        return CuratedCase(
            patient=patient,
            has_diabetes=has_diabetes,
            has_hypertension=has_hypertension,
            data_quality_score=data_quality_score,
            missing_items=missing_items,
            signals=signals,
            curator_notes=notes,
        )

    def _model_data_quality_note(
        self,
        patient: PatientSnapshot,
        signals: dict[str, object],
        missing_items: list[str],
    ) -> str | None:
        prompt = f"""{DATA_CURATOR_PERSONA}

65세 이상 당뇨+고혈압 재진 판단을 위한 데이터 품질을 검토하세요.
진단이나 처방을 하지 말고, 누락/신뢰도/추세 해석에 필요한 메모만 작성하세요.

[환자]
나이={patient.age}, 질환={patient.conditions}, 약물={patient.medications}

[최근 신호]
{signals}

[누락 항목]
{missing_items}

JSON으로만 답하세요:
{{"curator_notes": ["메모1", "메모2"]}}"""
        return self.llm.invoke(prompt)
