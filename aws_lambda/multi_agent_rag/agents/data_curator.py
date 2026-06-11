from __future__ import annotations

from ..config import SETTINGS
from ..llm import LLMClient, extract_json_object
from ..personas import DATA_CURATOR_PERSONA
from ..repository import MongoRepository, sample_diabetes_hypertension_patient
from ..schemas import CuratedCase, PatientSnapshot
from ..utils import contains_any, latest_numeric, parse_blood_pressure, trend_delta_desc


class DataCurator:
    """Collects raw patient data and turns it into a reliable working memory."""

    def __init__(self, repository: MongoRepository):
        self.repository = repository
        self.llm = LLMClient(model=SETTINGS.worker_model)

    def run(self, search_input: str | None = None, use_sample: bool = False) -> CuratedCase:
        patient = (
            sample_diabetes_hypertension_patient()
            if use_sample
            else self.repository.load_patient_snapshot(search_input or "")
        )
        return self._curate(patient)

    def curate_deterministic(self, patient: PatientSnapshot) -> CuratedCase:
        """LLM 호출 없이 *결정론적*으로 CuratedCase 생성.
        signals/missing/notes만 생성하고 model_quality_note는 생략.
        single_llm_cds 같은 *LLM 회수 최소화* arm에서 사용.
        """
        return self._build_curated(patient, llm_quality_note=False)

    def _curate(self, patient: PatientSnapshot) -> CuratedCase:
        return self._build_curated(patient, llm_quality_note=True)

    def _build_curated(self, patient: PatientSnapshot, llm_quality_note: bool) -> CuratedCase:
        condition_texts = patient.conditions
        has_diabetes = contains_any(condition_texts, ["당뇨", "diabetes", "dm"])
        has_hypertension = contains_any(condition_texts, ["고혈압", "hypertension", "htn"])

        bp_values = [parse_blood_pressure(record.blood_pressure) for record in patient.records]
        systolic_values = [bp[0] for bp in bp_values]
        diastolic_values = [bp[1] for bp in bp_values]
        sugar_values = [record.blood_sugar for record in patient.records]
        hba1c_values = [record.hba1c for record in patient.records]
        # chief_complaint + notes + structured symptoms 리스트까지 모두 합쳐
        # CDS/Reasoner가 어느 입력 채널에서도 증상 단서를 놓치지 않게.
        def _record_text(rec):
            parts = [rec.chief_complaint or "", rec.notes or ""]
            if getattr(rec, "symptoms", None):
                parts.append(" / ".join(str(s) for s in rec.symptoms if s))
            return " ".join(p for p in parts if p)
        symptom_texts = [_record_text(record) for record in patient.records[:3]]

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

        # 순수 데이터 추출만 (파생 플래그·룰 점수 없음). LLM이 RAG와 함께 해석.
        signals = {
            "latest_systolic": latest_systolic,
            "latest_diastolic": latest_diastolic,
            "latest_blood_sugar": latest_sugar,
            "latest_hba1c": latest_hba1c,
            "systolic_delta": trend_delta_desc(systolic_values),
            "diastolic_delta": trend_delta_desc(diastolic_values),
            "blood_sugar_delta": trend_delta_desc(sugar_values),
            "record_count": len(patient.records),
            "recent_symptom_text": " / ".join(symptom_texts),
            "has_doctor_override": bool(patient.overrides),
            # LLM agent들이 같은 컨텍스트로 추론할 수 있게 원시 데이터 노출 (룰 아님, 정보 전달)
            "medications": list(patient.medications),
            "diagnoses": [d.get("name", "") for d in patient.diagnoses],
            "medication_adherence_days": patient.medication_adherence_days,
            "regular_care": patient.regular_care,
        }

        notes = [
            "당뇨와 고혈압을 동시에 가진 재진 환자만 본 파이프라인의 1차 대상입니다.",
            f"데이터 신뢰도 점수: {data_quality_score}/100",
        ]
        if patient.overrides:
            notes.append("과거 의사 오버라이드가 있어 에피소드 메모리를 추론에 반영합니다.")

        # llm_quality_note=False면 LLM 호출 스킵 — 결정론적 curate.
        # single_llm_cds 같은 "단일 LLM + CDS" arm이 추가 LLM 비용 없이 deterministic
        # signal/symptom_text + CDS만 받게 하기 위해.
        if llm_quality_note:
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
