import os
import torch
from dotenv import load_dotenv
import ollama
from sentence_transformers import SentenceTransformer
from supabase import create_client, Client
from typing import List, Dict
from enum import Enum

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
embedder = SentenceTransformer("jhgan/ko-sroberta-multitask")


class Stage(Enum):
    GATE = "Stage 1: Gate Agent"
    RESEARCHER = "Stage 2: Researcher & Agent"
    JUDGE = "Stage 3: Judge Agent"
    ORCHESTRATOR = "Stage 4: Orchestrator Agent"


class GateAgent:
    """의료 질문 분류 및 라우팅"""

    def __init__(self):
        self.model = "mistral"

    def classify(self, query: str) -> Dict:
        """질문을 의료 정보 조회/진단 판단으로 분류"""
        prompt = f"""다음 질문을 분류하세요.
질문: {query}

분류:
1. 의료정보조회 - 질병/약물/치료법 정보 조회
2. 진단판단 - 증상 기반 진단/판단 요청

JSON 응답:
{{"type": "의료정보조회" 또는 "진단판단", "confidence": 0~1, "reason": "분류 이유"}}"""

        response = ollama.generate(model=self.model, prompt=prompt, stream=False)
        return response["response"]


class ResearcherAgent:
    """의료 정보 검색 및 요약"""

    def __init__(self):
        self.model = "mistral"

    def search_knowledge_base(self, query: str, top_k: int = 3) -> List[Dict]:
        """지식베이스에서 관련 문서 검색"""
        query_embedding = embedder.encode(query).tolist()

        try:
            response = supabase.rpc(
                "match_documents",
                {"query_embedding": query_embedding, "match_count": top_k}
            ).execute()
            return response.data if response.data else []
        except:
            response = supabase.table("knowledge_base").select(
                "id, content, metadata"
            ).limit(top_k).execute()
            return response.data if response.data else []

    def summarize(self, documents: List[Dict]) -> str:
        """검색된 문서 요약"""
        if not documents:
            return "관련 정보 없음"

        context = "\n".join([doc['content'][:500] for doc in documents])
        prompt = f"""다음 의료 정보를 3문장으로 요약하세요:
{context}"""

        response = ollama.generate(model=self.model, prompt=prompt, stream=False)
        return response["response"]


class DiagnosisSubAgent:
    """증상 기반 진단 전문"""

    def __init__(self):
        self.model = "mistral"

    def analyze_symptoms(self, query: str, context: str) -> str:
        """증상 분석 및 진단"""
        prompt = f"""의료 정보를 바탕으로 증상을 분석하세요.
[의료 정보]
{context}

[증상]
{query}

[분석]"""

        response = ollama.generate(model=self.model, prompt=prompt, stream=False)
        return response["response"]


class JudgeAgent:
    """최종 검증 및 판단"""

    def __init__(self):
        self.model = "mistral"

    def verify(self, query: str, analysis: str) -> Dict:
        """분석 결과 검증"""
        prompt = f"""다음 의료 분석을 검증하세요.
[질문]
{query}

[분석]
{analysis}

검증 결과 (신뢰도, 안전성, 추가 주의사항):"""

        response = ollama.generate(model=self.model, prompt=prompt, stream=False)
        return {
            "verified_analysis": analysis,
            "verification": response["response"]
        }


class OrchestratorAgent:
    """전체 워크플로우 조율"""

    def __init__(self):
        self.gate = GateAgent()
        self.researcher = ResearcherAgent()
        self.diagnosis = DiagnosisSubAgent()
        self.judge = JudgeAgent()

    def process(self, query: str) -> Dict:
        """멀티 에이전트 파이프라인"""
        print(f"\n{'=' * 60}")
        print(f"🏥 SilverSync Multi-Agent RAG System")
        print(f"{'=' * 60}")

        # Stage 1: Gate Agent - 질문 분류
        print(f"\n[Stage 1: Gate Agent] 질문 분류 중...")
        gate_result = self.gate.classify(query)
        print(f"분류 결과: {gate_result}")

        # Stage 2: Researcher & Sub-agents
        print(f"\n[Stage 2: Researcher Agent] 지식베이스 검색 중...")
        docs = self.researcher.search_knowledge_base(query, top_k=3)
        print(f"📄 {len(docs)}개 문서 검색됨")

        if not docs:
            summary = "관련 정보를 찾을 수 없습니다."
        else:
            summary = self.researcher.summarize(docs)

        print(f"요약: {summary[:200]}...")

        # Sub-agent: Diagnosis (진단 필요 시)
        if "진단" in gate_result.lower():
            print(f"\n[Sub-Agent: Diagnosis] 증상 분석 중...")
            diagnosis = self.diagnosis.analyze_symptoms(query, summary)
            analysis = diagnosis
        else:
            analysis = summary

        # Stage 3: Judge Agent - 검증
        print(f"\n[Stage 3: Judge Agent] 결과 검증 중...")
        verification = self.judge.verify(query, analysis)

        # Stage 4: Final Output
        print(f"\n[Stage 4: Final Output] 최종 결과")
        print(f"{'=' * 60}")

        sources = []
        for doc in docs:
            if isinstance(doc.get('metadata'), dict):
                sources.append(doc['metadata'].get('source', 'Unknown'))
            else:
                sources.append('Unknown')

        return {
            "query": query,
            "stage_1_classification": gate_result,
            "stage_2_research": {
                "documents_found": len(docs),
                "summary": summary
            },
            "stage_3_analysis": analysis,
            "stage_3_verification": verification["verification"],
            "sources": sources
        }


def main():
    orchestrator = OrchestratorAgent()

    print("=" * 60)
    print("🏥 SilverSync Multi-Agent RAG (4-Stage System)")
    print("=" * 60)
    print("💡 'exit'를 입력하면 종료\n")

    while True:
        query = input("❓ 의료 질문을 입력하세요: ").strip()

        if query.lower() in ["exit", "quit"]:
            print("프로그램 종료")
            break

        if not query:
            continue

        result = orchestrator.process(query)

        print(f"\n📌 출처:")
        for source in result["sources"]:
            print(f"  - {source}")

        print(f"\n🤖 최종 답변:")
        print("-" * 60)
        print(result["stage_3_analysis"])
        print(f"\n✅ 검증 결과:")
        print(result["stage_3_verification"])
        print("=" * 60)


if __name__ == "__main__":
    main()