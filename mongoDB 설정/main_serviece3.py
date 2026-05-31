import os
import certifi
import re
from datetime import datetime
from dotenv import load_dotenv

from pymongo import MongoClient
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_ollama import OllamaLLM
from langchain_huggingface import HuggingFaceEmbeddings
import langchainhub as hub

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
try:
    from langchain.agents import AgentExecutor, create_react_agent
except ImportError:
    # 위 경로가 실패할 경우를 대비한 하위 모듈 직접 참조
    from langchain.agents.agent import AgentExecutor
    from langchain.agents import create_react_agent
from langchain_core.tools import Tool

# 1. 환경 변수 로드
load_dotenv()


class SilverSyncSystem:
    def __init__(self):
        # [설정] 환경 변수 및 DB 연결
        self.mongo_uri = os.getenv("MONGO_URI")
        self.db_name = os.getenv("DB_NAME", "silver_sync_db")
        self.model_tag = os.getenv("GEMMA_MODEL", "gemma4:4b")

        # [임베딩] 한국어 최적화 모델 사용
        self.embedding_func = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")

        # [MongoDB] 연결 설정 (보안 인증서 포함)
        self.client = MongoClient(self.mongo_uri, tls=True, tlsCAFile=certifi.where())
        self.db = self.client[self.db_name]

        # [Collections]
        self.knowledge_col = self.db["knowledge_base"]
        self.drug_col = self.db["drug_interactions"]
        self.patients_col = self.db["patients"]
        self.visit_records_col = self.db["visit_records"]

        # [LLM] Gemma 4 추론 엔진
        self.llm = OllamaLLM(model=self.model_tag, temperature=0.1)

        # [Retriever] 메인 RAG (지침서 검색)
        self.vector_search = MongoDBAtlasVectorSearch(
            collection=self.knowledge_col,
            embedding=self.embedding_func,
            index_name="vector_index"
        )
        self.retriever = self.vector_search.as_retriever(search_kwargs={"k": 5})

    # --- 데이터 조회 로직 ---

    def search_patient(self, search_input):
        """환자 ID 또는 이름으로 검색"""
        patient = self.patients_col.find_one({"patient_id": search_input})
        if not patient:
            patient = self.patients_col.find_one({"name": {"$regex": search_input, "$options": "i"}})
        return patient

    def get_patient_context(self, patient_id):
        """서브 RAG: 환자 데이터 + 진료 이력을 context로 변환"""
        patient = self.patients_col.find_one({"patient_id": patient_id})
        if not patient: return None, None

        records = list(self.visit_records_col.find({"patient_id": patient_id}).sort("visit_date", -1).limit(5))

        context = f"[환자 기본 정보]\n- 이름: {patient.get('name')}\n- 나이: {patient.get('age')}세\n- 주요 질환: {', '.join(patient.get('conditions', []))}\n"
        if records:
            context += "\n[최근 진료 이력]"
            for r in records:
                v = r.get('vital_signs', {})
                context += f"\n- {r.get('visit_date').strftime('%Y-%m-%d')}: {r.get('chief_complaint')} (BP: {v.get('blood_pressure')}, BS: {v.get('blood_sugar')})"
        return patient, context

    def search_drug_interactions(self, meds):
        """병용 금기(DUR) 검색"""
        results = []
        for med in meds:
            found = list(self.drug_col.find({"$or": [{"성분명A": {"$regex": med}}, {"성분명B": {"$regex": med}}]}))
            results.extend(found)
        return results

    # --- AI 추론 및 판정 로직 ---

    def get_diagnosis(self, patient_id, custom_query=None):
        """Clinical Reasoner 기반 진단 수행"""
        patient, patient_context = self.get_patient_context(patient_id)
        if not patient: return None, "환자 없음", []

        query = custom_query if custom_query else f"{', '.join(patient.get('conditions', []))} 상태 평가 및 재진 판정"

        # 메인 RAG 검색
        docs = self.retriever.invoke(query)
        kb_context = "\n\n".join(doc.page_content for doc in docs)
        sources = [doc.metadata.get("source", "Unknown") for doc in docs]

        prompt = PromptTemplate(
            template="""당신은 Silver-Sync의 임상 추론기(Clinical Reasoner)입니다. 
가이드라인과 환자 이력을 대조하여 판정하세요.

[환자 이력]
{patient_context}

[의료 지침]
{kb_context}

[요청] {query}

형식:
1. 현재 상태 평가
2. 주요 쟁점 (가이드라인 vs 실제 이력 대조)
3. 위험도 점수 (0-100 숫자만)
4. 진료 방식 (비대면/대면)
5. 근거 요약""",
            input_variables=["patient_context", "kb_context", "query"]
        )

        chain = prompt | self.llm | StrOutputParser()
        return patient, chain.invoke(
            {"patient_context": patient_context, "kb_context": kb_context, "query": query}), sources

    # --- UI 및 실행 제어 ---

    def format_output(self, patient, result, sources):
        print("\n" + "=" * 70)
        print(f" AI 진단 레포트: {patient.get('name')} ({patient.get('patient_id')})")
        print("=" * 70)
        print(result)
        print("-" * 70)
        print(f"참조 지침: {', '.join(list(set([s.split('/')[-1] for s in sources])))}")
        print(f"생성 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)


def main():
    system = SilverSyncSystem()
    print("\n[Silver-Sync] Gemma 4 기반 의료 AI 가동 시작...")

    while True:
        search_input = input("\n🔍 환자 ID 또는 이름 (종료: q): ").strip()
        if search_input.lower() == 'q': break

        try:
            patient = system.search_patient(search_input)
            if not patient:
                print("❌ 환자를 찾을 수 없습니다.");
                continue

            print(f" 분석 중: {patient['name']}...")
            p_data, diag, srcs = system.get_diagnosis(patient['patient_id'])
            system.format_output(p_data, diag, srcs)

            # DUR 체크
            interactions = system.search_drug_interactions(patient.get('medications', []))
            if interactions:
                print("\n⚠️ [DUR 경고] 복용 약물 간 상호작용 주의!")
                for i in interactions:
                    print(f" - {i['성분명A']} + {i['성분명B']}: {i['상세정보']}")

        except Exception as e:
            print(f"🚨 오류: {e}")


if __name__ == "__main__":
    main()