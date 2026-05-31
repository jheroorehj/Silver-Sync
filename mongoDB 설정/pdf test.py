import json
import glob
import pandas as pd
from pymongo import MongoClient
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

embedding_func = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")

MONGO_URI = "mongodb+srv://SilverSynk:JWT5PovJL7hI1Jrd@cluster0.hts55d7.mongodb.net/?appName=Cluster0"
DB_NAME = "silver_sync_db"
COLLECTION_NAME = "knowledge_base"

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)


def load_json_to_documents(json_path):
    """OCR 결과 JSON 파일 로드"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    documents = []
    for item in data:
        doc = Document(
            page_content=item["content"],
            metadata={
                "source": json_path,
                "page": item["page"],
                "total_pages": item["total_pages"],
                "file_type": "pdf"
            }
        )
        documents.append(doc)

    print(f"  [JSON] 로드 완료: {len(documents)}페이지")
    return documents


def load_csv_to_documents(csv_path):
    """CSV 파일 로드"""
    try:
        # 인코딩 자동 감지 (utf-8 → cp949 순서로 시도)
        try:
            df = pd.read_csv(csv_path, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="cp949")

        print(f"  [CSV] 컬럼 목록: {df.columns.tolist()}")
        print(f"  [CSV] 총 행 수: {len(df)}")

        documents = []
        for idx, row in df.iterrows():
            # 모든 컬럼을 "컬럼명: 값" 형태로 합치기
            content = "\n".join([
                f"{col}: {val}"
                for col, val in row.items()
                if pd.notna(val) and str(val).strip()
            ])

            if content.strip():
                doc = Document(
                    page_content=content,
                    metadata={
                        "source": csv_path,
                        "row": idx + 1,
                        "file_type": "csv"
                    }
                )
                documents.append(doc)

        print(f"  [CSV] 로드 완료: {len(documents)}행")
        return documents

    except Exception as e:
        print(f"  [CSV] 실패: {e}")
        return []


def upload_to_mongodb(docs, collection):
    """MongoDB 배치 업로드"""
    if not docs:
        print("  [SKIP] 업로드할 문서 없음")
        return

    batch_size = 50
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i + batch_size]
        MongoDBAtlasVectorSearch.from_documents(
            documents=batch,
            embedding=embedding_func,
            collection=collection,
            index_name="vector_index"
        )
        print(f"  배치 {i // batch_size + 1} 업로드 ({len(batch)}개)")


def ingest_all_data():
    client = MongoClient(MONGO_URI)
    collection = client[DB_NAME][COLLECTION_NAME]

    # JSON 파일 처리 (OCR 결과)
    json_files = glob.glob("./data_csv/*.json")
    print(f"발견된 JSON 파일 수: {len(json_files)}")

    for json_file in json_files:
        print(f"\n처리 중: {json_file}")
        pages = load_json_to_documents(json_file)

        if not pages:
            print(f"  [SKIP] 내용 없음")
            continue

        docs = text_splitter.split_documents(pages)
        print(f"  청크 수: {len(docs)}")
        print(f"  미리보기: {docs[0].page_content[:100]}")

        upload_to_mongodb(docs, collection)
        print(f"  [{json_file}] 완료!")

    # CSV 파일 처리
    csv_files = glob.glob("./data_csv/*.csv")
    print(f"\n발견된 CSV 파일 수: {len(csv_files)}")

    for csv_file in csv_files:
        print(f"\n처리 중: {csv_file}")
        pages = load_csv_to_documents(csv_file)

        if not pages:
            print(f"  [SKIP] 내용 없음")
            continue

        # CSV는 행이 짧으므로 chunk_size 조정
        csv_splitter = RecursiveCharacterTextSplitter(
            chunk_size=300,
            chunk_overlap=30
        )
        docs = csv_splitter.split_documents(pages)
        print(f"  청크 수: {len(docs)}")
        print(f"  미리보기: {docs[0].page_content[:100]}")

        upload_to_mongodb(docs, collection)
        print(f"  [{csv_file}] 완료!")


if __name__ == "__main__":
    ingest_all_data()