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

# 1. 설정
MONGO_URI = "mongodb+srv://SilverSynk:JWT5PovJL7hI1Jrd@cluster0.hts55d7.mongodb.net/?appName=Cluster0"

# 2. 임베딩
embedding_func = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")

# 3. MongoDB 연결
client = MongoClient(MONGO_URI)

client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where()
)

knowledge_collection = client["silver_sync_db"]["knowledge_base"]
drug_collection = client["silver_sync_db"]["drug_interactions"]

# 4. 벡터 검색 엔진
vector_search = MongoDBAtlasVectorSearch(
    collection=knowledge_collection,
    embedding=embedding_func,
    index_name="vector_index"
)

# 5. LLM
llm = OllamaLLM(model="gemma3:4b", temperature=0.1)

# 6. 프롬프트
prompt = PromptTemplate(
    template="""당신은 어르신들의 건강 정보를 안내하는 '실버 싱크' 도우미입니다.
아래 제공된 의학 정보를 바탕으로 질문에 친절하게 답변하세요.
모르는 내용은 지어내지 말고 정중히 모른다고 답하세요.
의사의 진단이나 처방을 대신하지 않으며, 전문의 상담을 권유하세요.
어르신이 이해하기 쉽도록 쉬운 말로 설명하세요.

[참고 정보]
{context}

[질문]
{question}

[답변]:""",
    input_variables=["context", "question"]
)

# 7. retriever
retriever = vector_search.as_retriever(search_kwargs={"k": 5})


def format_docs(docs):
    """검색된 문서를 하나의 텍스트로 합치기"""
    return "\n\n".join(doc.page_content for doc in docs)


# 8. LCEL 체인 (RetrievalQA 대체)
rag_chain = (
    {
        "context": retriever | format_docs,
        "question": RunnablePassthrough()
    }
    | prompt
    | llm
    | StrOutputParser()
)

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

    # 중복 제거
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

def ask(query):
    """질문 유형에 따라 적절한 검색 수행"""

    # 병용금기 관련 질문
    if is_drug_interaction_query(query):
        drug_results = search_drug_interactions(query)

        if drug_results:
            drug_info = "\n".join([
                f"- {r['성분명A']} + {r['성분명B']}: {r['상세정보']}"
                for r in drug_results
            ])

            drug_prompt = f"""당신은 어르신들의 건강 정보를 안내하는 '실버 싱크' 도우미입니다.
아래 병용금기 정보를 바탕으로 친절하게 답변하세요.
반드시 전문의 상담을 권유하세요.

[병용금기 정보]
{drug_info}

[질문]
{query}

[답변]:"""

            response = llm.invoke(drug_prompt)
            return response, ["drug_interactions 컬렉션"]

    # 일반 진료지침 질문
    # 출처 문서도 함께 가져오기
    docs = retriever.invoke(query)
    sources = [doc.metadata.get("source", "알 수 없음") for doc in docs]
    response = rag_chain.invoke(query)

    return response, sources


def format_sources(sources):
    """출처 정보 포맷팅"""
    if not sources:
        return ""

    unique_sources = list(set(sources))
    source_text = "\n📚 참고 자료:"
    for src in unique_sources:
        filename = src.split("\\")[-1].split("/")[-1]
        source_text += f"\n  - {filename}"
    return source_text


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("    실버 싱크 건강 정보 서비스")
    print("=" * 50)
    print("건강 정보를 안내해 드립니다.")
    print("종료하려면 'q'를 입력하세요.\n")

    while True:
        user_input = input("궁금하신 점을 말씀해 주세요: ").strip()

        if not user_input:
            continue
        if user_input.lower() == "q":
            print("이용해 주셔서 감사합니다.")
            break

        try:
            print("\n답변을 준비 중입니다...\n")
            response, sources = ask(user_input)

            print(f"실버 싱크: {response}")
            print(format_sources(sources))
            print("-" * 50)

        except Exception as e:
            print(f"오류가 발생했습니다: {e}")