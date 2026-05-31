# main.py - 최종 통합 코드

import ssl
import os
import certifi
from pymongo import MongoClient
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_ollama import OllamaLLM
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from datetime import datetime
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경 변수 읽기
api_key = os.getenv("GEMMA_API_KEY")

# 설정
MONGO_URI = os.getenv("MONGO_URI")

# 임베딩 모델
embedding_func = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")

# MongoDB 연결
client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where()
)

db = client[os.getenv("DB_NAME", "silver_sync_db")]
knowledge_collection = db["knowledge_base"]
drug_collection = db["drug_interactions"]
patients_collection = db["patients"]
visit_records_collection = db["visit_records"]

# 벡터 검색
vector_search = MongoDBAtlasVectorSearch(
    collection=knowledge_collection,
    embedding=embedding_func,
    index_name="vector_index"
)

# LLM
llm = OllamaLLM(model="gemma3:4b", temperature=0.1)

# Retriever
retriever = vector_search.as_retriever(search_kwargs={"k": 5})


def search_patient(search_input):
    """환자 ID 또는 이름으로 검색"""
    patient = patients_collection.find_one({"patient_id": search_input})

    if not patient:
        patient = patients_collection.find_one(
            {"name": {"$regex": search_input, "$options": "i"}}
        )

    return patient


def get_patient_context(patient_id):
    """환자 데이터 + 진료 이력을 context로 변환"""
    patient = patients_collection.find_one({"patient_id": patient_id})

    if not patient:
        return None, None

    # 최근 10개 진료 이력 조회
    records = list(
        visit_records_collection.find(
            {"patient_id": patient_id}
        ).sort("visit_date", -1).limit(10)
    )

    # 기본 정보 포맷팅
    patient_info = f"""
[환자 기본 정보]
- 환자 ID: {patient.get('patient_id', 'N/A')}
- 이름: {patient.get('name', 'N/A')}
- 나이: {patient.get('age', 'N/A')}세
- 성별: {patient.get('gender', 'N/A')}
- 주요 질환: {', '.join(patient.get('conditions', []))}
- 현재 복용 약물: {', '.join(patient.get('medications', []))}
"""

    # 진료 이력 포맷팅
    if records:
        patient_info += "\n[최근 진료 이력 (최신순)]"
        for i, record in enumerate(records, 1):
            visit_date = record.get('visit_date', 'N/A').strftime('%Y-%m-%d')
            chief_complaint = record.get('chief_complaint', 'N/A')
            blood_sugar = record.get('vital_signs', {}).get('blood_sugar', 'N/A')
            blood_pressure = record.get('vital_signs', {}).get('blood_pressure', 'N/A')
            notes = record.get('notes', '')

            patient_info += f"\n{i}. {visit_date} - {chief_complaint}"
            patient_info += f"\n   혈당: {blood_sugar} mg/dL, 혈압: {blood_pressure} mmHg"
            if notes:
                patient_info += f"\n   비고: {notes}"
    else:
        patient_info += "\n[진료 이력]"
        patient_info += "\n등록된 진료 이력이 없습니다."

    return patient, patient_info


def search_drug_interactions(query):
    """병용금기 검색"""
    keywords = [word for word in query.split() if len(word) >= 2]

    results = []
    for keyword in keywords:
        found = list(drug_collection.find(
            {
                "$or": [
                    {"성분명A": {"$regex": keyword, "$options": "i"}},
                    {"성분명B": {"$regex": keyword, "$options": "i"}}
                ]
            },
            {"_id": 0, "성분명A": 1, "성분명B": 1, "상세정보": 1},
            limit=5
        ))
        results.extend(found)

    seen = set()
    unique_results = []
    for r in results:
        key = f"{r['성분명A']}_{r['성분명B']}"
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    return unique_results


def is_drug_interaction_query(query):
    """병용금기 관련 질문인지 판단"""
    keywords = ["같이", "함께", "병용", "동시에", "먹어도", "복용해도", "금기", "위험"]
    return any(kw in query for kw in keywords)


def get_diagnosis(patient_id, custom_query=None):
    """환자의 AI 진단 결과 생성"""

    patient, patient_context = get_patient_context(patient_id)

    if not patient:
        return None, "환자를 찾을 수 없습니다.", None

    if not patient_context:
        return patient, "환자 정보를 로드할 수 없습니다.", None

    # 기본 진단 쿼리
    if custom_query:
        query = f"{custom_query} (환자: {patient.get('name')})"
    else:
        conditions = ", ".join(patient.get('conditions', []))
        query = f"{conditions} 환자의 최근 상태 평가 및 진료 권고"

    # 의료 지침 검색
    docs = retriever.invoke(query)
    kb_context = "\n\n".join(doc.page_content for doc in docs)
    sources = [doc.metadata.get("source", "알 수 없음") for doc in docs]

    # 진단 프롬프트 (비대면/대면 판정 + 위험도 포함)
    diagnosis_prompt = PromptTemplate(
        template="""당신은 경험 많은 의료 AI 어시스턴트입니다.
아래 환자의 정보와 진료지침을 바탕으로 객관적인 진료 평가를 제공하세요.

[환자 정보]
{patient_context}

[참고 의료 지침]
{kb_context}

[분석 요청]
{query}

다음 형식으로 정확히 답변하세요:

[진단 및 권고사항]

1. 현재 상태 평가:
(환자의 현재 건강 상태를 평가하세요)

2. 주요 우려사항:
(환자의 주요 건강상 우려사항을 나열하세요)

3. 진료 권고사항:
(구체적인 진료 권고를 제시하세요)

4. 약물 상호작용 확인 필요 여부:
(필요/불필요)

5. 추가 검사 권고:
(필요한 추가 검사를 나열하세요)

6. 위험도 점수:
(0~100 사이의 숫자로만 표기. 예: 35)

7. 진료 방식 판정:
(다음 중 하나: 비대면/대면)

8. 판정 근거:
(비대면 또는 대면으로 판정한 이유를 설명하세요)
""",
        input_variables=["patient_context", "kb_context", "query"]
    )

    chain = (
            diagnosis_prompt
            | llm
            | StrOutputParser()
    )

    diagnosis_result = chain.invoke({
        "patient_context": patient_context,
        "kb_context": kb_context,
        "query": query
    })

    return patient, diagnosis_result, sources


def format_diagnosis_output(patient, diagnosis_result, sources):
    """진단 결과를 보기 좋게 포맷팅"""

    # 진단 결과에서 위험도와 진료 방식 추출
    risk_score = extract_risk_score(diagnosis_result)
    consultation_type = extract_consultation_type(diagnosis_result)

    output = f"""
{'=' * 70}
                        AI 진료 진단 결과
{'=' * 70}

[환자 정보]
ID: {patient.get('patient_id')}
이름: {patient.get('name')}
나이: {patient.get('age')}세
주요 질환: {', '.join(patient.get('conditions', []))}

{'=' * 70}

[AI 진단 결과]
{diagnosis_result}

{'=' * 70}

[진료 판정]
위험도: {risk_score}/100
진료 방식: {get_consultation_display(consultation_type)}

{'=' * 70}

[참고 자료]
"""

    if sources:
        unique_sources = list(set(sources))
        for src in unique_sources:
            filename = src.split("\\")[-1].split("/")[-1]
            output += f"\n- {filename}"

    output += f"\n\n생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    output += f"\n{'=' * 70}\n"

    return output


def extract_risk_score(diagnosis_result):
    """진단 결과에서 위험도 점수 추출"""
    import re

    # "위험도 점수:" 또는 "위험도:" 다음의 숫자 찾기
    patterns = [
        r'위험도\s*점수\s*:\s*(\d+)',
        r'위험도\s*:\s*(\d+)',
        r'6\.\s*위험도\s*점수\s*:\s*(\d+)',
        r'위험도.*?:\s*(\d+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, diagnosis_result)
        if match:
            return match.group(1)

    return "계산 중"


def extract_consultation_type(diagnosis_result):
    """진단 결과에서 진료 방식 추출"""
    import re

    # "진료 방식 판정:" 또는 "진료 판정:" 다음의 비대면/대면 찾기
    patterns = [
        r'진료\s*방식\s*판정\s*:\s*(비대면|대면)',
        r'진료\s*판정\s*:\s*(비대면|대면)',
        r'7\.\s*진료\s*방식\s*판정\s*:\s*(비대면|대면)',
        r'진료.*?:\s*(비대면|대면)'
    ]

    for pattern in patterns:
        match = re.search(pattern, diagnosis_result)
        if match:
            return match.group(1)

    return "미판정"


def get_consultation_display(consultation_type):
    """진료 방식 표시"""
    if consultation_type == "비대면":
        return "🟢 비대면 진료 가능"
    elif consultation_type == "대면":
        return "🔴 대면 진료 필요"
    else:
        return "⚠️ 미판정"


def check_drug_interactions_for_patient(patient_id):
    """환자의 현재 복용 약물 간 상호작용 확인"""
    patient = patients_collection.find_one({"patient_id": patient_id})

    if not patient:
        return None, "환자를 찾을 수 없습니다."

    medications = patient.get('medications', [])

    if not medications:
        return patient, "등록된 약물이 없습니다."

    interaction_info = f"현재 복용 약물: {', '.join(medications)}\n\n"

    for med in medications:
        results = search_drug_interactions(med)
        if results:
            interaction_info += f"\n[{med}와의 상호작용]\n"
            for r in results:
                interaction_info += f"- {r['성분명A']} + {r['성분명B']}: {r['상세정보']}\n"

    return patient, interaction_info


def main():
    """메인 프로그램"""
    print("\n" + "=" * 70)
    print("           실버 싱크 - AI 환자 진료 진단 시스템")
    print("=" * 70)
    print("\n사용 방법:")
    print("1. 환자 ID 또는 이름을 입력하면 AI 진단 결과를 보여드립니다.")
    print("2. 추가 질문이 있으시면 입력해주세요.")
    print("3. 'q'를 입력하면 종료됩니다.\n")

    while True:
        search_input = input("환자 ID 또는 이름을 입력하세요: ").strip()

        if not search_input:
            continue
        if search_input.lower() == 'q':
            print("\n프로그램을 종료합니다. 감사합니다.")
            break

        try:
            # 환자 검색
            patient = search_patient(search_input)

            if not patient:
                print(f"\n❌ '{search_input}'에 해당하는 환자를 찾을 수 없습니다.\n")
                continue

            print(f"\n✓ 환자 '{patient.get('name')}' (ID: {patient.get('patient_id')})을(를) 찾았습니다.")
            print("진단을 분석 중입니다...\n")

            # AI 진단 수행
            patient, diagnosis_result, sources = get_diagnosis(patient['patient_id'])

            # 결과 출력
            if diagnosis_result:
                output = format_diagnosis_output(patient, diagnosis_result, sources)
                print(output)
            else:
                print("❌ 진단 결과를 생성할 수 없습니다.\n")
                continue

            # 약물 상호작용 확인
            print("\n약물 상호작용을 확인 중입니다...\n")
            patient, interaction_info = check_drug_interactions_for_patient(patient['patient_id'])

            if interaction_info != "등록된 약물이 없습니다.":
                print("=" * 70)
                print("[약물 상호작용 정보]")
                print("=" * 70)
                print(interaction_info)
                print("=" * 70 + "\n")

            # 추가 질문 옵션
            while True:
                follow_up = input("추가로 궁금한 점이 있으신가요? (또는 'n'/'q'를 입력): ").strip()

                # q 입력 시 프로그램 전체 종료
                if follow_up.lower() == 'q':
                    print("\n프로그램을 종료합니다. 감사합니다.")
                    return

                # n 입력 시 다음 환자 검색
                if follow_up.lower() == 'n' or not follow_up:
                    print("\n다음 환자를 검색합니다.\n")
                    break

                print("\n추가 분석을 진행 중입니다...\n")

                try:
                    patient_result, custom_diagnosis, sources = get_diagnosis(
                        patient['patient_id'],
                        custom_query=follow_up
                    )

                    if patient_result and custom_diagnosis:
                        custom_output = format_diagnosis_output(patient_result, custom_diagnosis, sources)
                        print(custom_output)
                    else:
                        print("❌ 진단 결과를 생성할 수 없습니다.\n")

                except Exception as e:
                    print(f"❌ 오류 발생: {e}\n")

        except Exception as e:
            print(f"\n❌ 오류 발생: {e}\n")


if __name__ == "__main__":
    main()