import os
import glob
from pymongo import MongoClient
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_community.document_loaders import PyMuPDFLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings

embedding_func = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")

MONGO_URI = "mongodb+srv://SilverSynk:JWT5PovJL7hI1Jrd@cluster0.hts55d7.mongodb.net/?appName=Cluster0"
DB_NAME = "silver_sync_db"
COLLECTION_NAME = "knowledge_base"

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)

def load_pdf(file_path):
    """여러 로더를 순서대로 시도"""
    # 방법 1: PyMuPDF
    try:
        loader = PyMuPDFLoader(file_path)
        pages = loader.load()
        if pages and any(p.page_content.strip() for p in pages):
            print(f"  [PyMuPDF] 성공: {len(pages)}페이지")
            return pages
        else:
            print(f"  [PyMuPDF] 텍스트 없음, 다음 로더 시도...")
    except Exception as e:
        print(f"  [PyMuPDF] 실패: {e}")

    # 방법 2: PyPDF
    try:
        loader = PyPDFLoader(file_path)
        pages = loader.load()
        if pages and any(p.page_content.strip() for p in pages):
            print(f"  [PyPDF] 성공: {len(pages)}페이지")
            return pages
        else:
            print(f"  [PyPDF] 텍스트 없음")
    except Exception as e:
        print(f"  [PyPDF] 실패: {e}")

    return []


def ingest_all_data():
    client = MongoClient(MONGO_URI)
    collection = client[DB_NAME][COLLECTION_NAME]

    pdf_files = glob.glob("./data_plus/*.pdf")
    print(f"발견된 PDF 파일 수: {len(pdf_files)}")

    for pdf_file in pdf_files:
        print(f"\n처리 중: {pdf_file}")

        # PDF 로드
        pages = load_pdf(pdf_file)

        if not pages:
            print(f"  [SKIP] {pdf_file} - 텍스트 추출 실패")
            continue

        # 텍스트 분할
        docs = text_splitter.split_documents(pages)
        print(f"  청크 수: {len(docs)}")

        if not docs:
            print(f"  [SKIP] 분할된 문서 없음")
            continue

        # 내용 확인 (디버그)
        print(f"  첫 번째 청크 미리보기: {docs[0].page_content[:100]}")

        # MongoDB 업로드 (배치 처리, 한 번에 너무 많으면 오류 가능)
        batch_size = 50
        for i in range(0, len(docs), batch_size):
            batch = docs[i:i + batch_size]
            MongoDBAtlasVectorSearch.from_documents(
                documents=batch,
                embedding=embedding_func,
                collection=collection,
                index_name="vector_index"
            )
            print(f"  배치 {i // batch_size + 1} 업로드 완료 ({len(batch)}개)")

        print(f"  [{pdf_file}] 완료!")


if __name__ == "__main__":
    ingest_all_data()