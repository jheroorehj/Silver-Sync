"""단일 LLM 베이스라인 arm (어블레이션 A1 / A2).

토론·Guardian·다단계 없이 **LLM 한 번 호출**로 비대면/대면을 판정한다.
- A1: RAG 없음 (`use_rag=False`)
- A2: RAG 근거 주입 (`use_rag=True`)

멀티에이전트(A3)와 동일한 LLM 백엔드(JUDGE_MODEL)를 사용해 공정 비교한다.
반환 ConsultationType은 에이전트·베이스라인과 같은 라벨 공간.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import SETTINGS
from ..llm import LLMClient, evidence_block, extract_json_object
from ..repository import MongoRepository
from ..schemas import ConsultationType, PatientSnapshot
from ..utils import latest_numeric, parse_blood_pressure

CT = ConsultationType


def _map_consultation(text: str | None) -> ConsultationType | None:
    t = (text or "").strip()
    if "긴급" in t or "응급" in t:
        return CT.EMERGENCY
    if "비대면" in t:
        return CT.REMOTE
    if "불충분" in t or "데이터" in t:
        return CT.DATA_INSUFFICIENT
    if "대면" in t:
        return CT.IN_PERSON
    return None


@dataclass
class SingleLLMDecision:
    consultation_type: ConsultationType
    risk_score: int | None
    rationale: str
    used_rag: bool
    parsed_ok: bool
    model_used: str | None = None
    model_output: str | None = None
    model_error: str | None = None


def _patient_block(p: PatientSnapshot) -> str:
    sys_v = latest_numeric([parse_blood_pressure(r.blood_pressure)[0] for r in p.records])
    dia_v = latest_numeric([parse_blood_pressure(r.blood_pressure)[1] for r in p.records])
    fasting = latest_numeric([r.fasting_glucose for r in p.records])
    post = latest_numeric([r.postprandial_glucose for r in p.records])
    generic = latest_numeric([r.blood_sugar for r in p.records])
    hba1c = latest_numeric([r.hba1c for r in p.records])
    symptoms: list[str] = []
    notes: list[str] = []
    for r in p.records:
        symptoms += r.symptoms
        if r.notes:
            notes.append(r.notes)
    lines = [
        f"나이={p.age}, 성별={p.gender}",
        f"동반질환={p.conditions}",
        f"진단상세={p.diagnoses}" if p.diagnoses else "",
        f"약물={p.medications}",
        f"복약 월복용일수={p.medication_adherence_days}" if p.medication_adherence_days is not None else "",
        f"최근 혈압={sys_v}/{dia_v}",
        f"최근 공복혈당={fasting}, 식후혈당={post}, 혈당={generic}, HbA1c={hba1c}",
        f"증상={symptoms}" if symptoms else "증상=특이사항 없음",
        f"메모={' / '.join(notes)}" if notes else "",
    ]
    return "\n".join(line for line in lines if line)


class SingleLLMTriage:
    def __init__(self, repository: MongoRepository | None = None, use_rag: bool = False):
        self.repository = repository or MongoRepository()
        self.use_rag = use_rag
        self.llm = LLMClient(model=SETTINGS.judge_model)

    def run(self, patient: PatientSnapshot) -> SingleLLMDecision:
        block = _patient_block(patient)
        evidence_text = ""
        if self.use_rag:
            query = (
                "65세 이상 당뇨병 고혈압 동반 환자 재진 혈압 혈당 조절 비대면 대면 "
                "위험도 DUR 약물 안전 신기능 합병증 증상"
            )
            try:
                evidence = self.repository.retrieve_guidelines(query)
            except Exception:
                evidence = []
            if evidence:
                evidence_text = "\n\n[참고 진료지침 근거]\n" + evidence_block(evidence)

        prompt = f"""당신은 당뇨+고혈압 동반 고령 환자의 재진을 비대면(화상진료)으로 할지 대면(내원)으로 할지 판단하는 의료 보조 AI입니다.
환자 정보를 종합해 한 번에 판정하세요. 진단·처방을 확정하지 말고 의사 보조 판단으로 작성하세요.
위험 신호(약물 상호작용, 신기능 저하, 합병증 증상, 동반질환 등)를 놓치지 마세요.

[환자]
{block}{evidence_text}

JSON으로만 답하세요:
{{"consultation_type": "비대면 | 대면 | 긴급내원", "risk_score": 0, "rationale": "판단 근거 2문장"}}"""

        out = self.llm.invoke(prompt)
        parsed = extract_json_object(out)
        ct = _map_consultation(str((parsed or {}).get("consultation_type", "")))
        risk_raw = (parsed or {}).get("risk_score")
        risk = int(risk_raw) if isinstance(risk_raw, (int, float)) else None
        return SingleLLMDecision(
            consultation_type=ct or CT.IN_PERSON,  # 파싱 실패 시 보수적으로 대면(메트릭에서 FP로 드러남)
            risk_score=risk,
            rationale=str((parsed or {}).get("rationale", "")),
            used_rag=self.use_rag,
            parsed_ok=ct is not None,
            model_used=self.llm.model if (out or self.llm.last_error) else None,
            model_output=out,
            model_error=self.llm.last_error,
        )
