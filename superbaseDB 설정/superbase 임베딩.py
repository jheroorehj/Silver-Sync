import os
import pandas as pd
import json
from dotenv import load_dotenv
from supabase import create_client
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings

# 1. 환경 변수 및 초기화
load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
embeddings = HuggingFaceEmbeddings(model_name="jhgan/ko-sroberta-multitask")
text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)


def clean_text(text):
    """PostgreSQL에서 허용하지 않는 NULL 문자와 불필요한 공백 제거"""
    if not text:
        return ""
    return text.replace("\x00", "").strip()


def insert_to_supabase(data):
    """중복 방지(upsert) 기능이 포함된 통합 삽입 함수"""
    if not data:
        return

    try:
        # on_conflict='content' : 내용이 겹치면 업데이트 수행
        supabase.table("knowledge_base").upsert(
            data,
            on_conflict='content'
        ).execute()
    except Exception as e:
        # 유니크 제약 조건에 걸려도 프로그램이 중단되지 않도록 처리
        if "23505" in str(e):  # PostgreSQL 중복 키 에러 코드
            pass
        else:
            print(f"❌ Supabase 처리 오류: {e}")


def process_pdf_folder(folder_path):
    """./data 폴더 내 모든 PDF 처리"""
    if not os.path.exists(folder_path): return
    print(f"--- PDF 처리 시작: {folder_path} ---")
    for filename in os.listdir(folder_path):
        if filename.endswith(".pdf"):
            loader = PyPDFLoader(os.path.join(folder_path, filename))
            pages = loader.load()
            chunks = text_splitter.split_documents(pages)

            for chunk in chunks:
                # [수정] 데이터를 딕셔너리 형태로 묶어서 '인자 1개'로 전달
                payload = {
                    "content": clean_text(chunk.page_content),
                    "embedding": embeddings.embed_query(clean_text(chunk.page_content)),
                    "metadata": {**chunk.metadata, "source": filename}
                }
                insert_to_supabase(payload)
            print(f"✅ 완료: {filename}")


def process_csv_folder(folder_path):
    """CSV 처리를 벌크 방식으로 전환"""
    if not os.path.exists(folder_path): return
    print(f"--- CSV 벌크 처리 시작: {folder_path} ---")

    for filename in os.listdir(folder_path):
        if filename.endswith(".csv"):
            file_path = os.path.join(folder_path, filename)

            # 인코딩 시도
            for encoding in ['utf-8', 'cp949', 'euc-kr']:
                try:
                    # low_memory=False로 DtypeWarning 방지
                    df = pd.read_csv(file_path, encoding=encoding, low_memory=False).head(5000)
                    print(f"✅ {encoding} 로드 성공: {filename} (총 {len(df)}행)")

                    bulk_data = []
                    for i, (_, row) in enumerate(df.iterrows()):
                        content = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                        clean_content = content.replace("\x00", "").strip()

                        if not clean_content: continue

                        # 데이터 준비
                        embedding = embeddings.embed_query(clean_content)
                        bulk_data.append({
                            "content": clean_content,
                            "embedding": embedding,
                            "metadata": {"source": filename}
                        })

                        # 50개씩 묶어서 전송 (너무 크면 타임아웃 발생 가능)
                        if len(bulk_data) >= 50:
                            insert_to_supabase(bulk_data)
                            bulk_data = []
                            if i % 100 == 0:
                                print(f"   ㄴ 진행 중... {i}/{len(df)} 행 완료")

                    # 남은 데이터 전송
                    insert_to_supabase(bulk_data)
                    print(f"✅ 적재 완료: {filename}")
                    break
                except UnicodeDecodeError:
                    continue


def process_json_folder(folder_path):
    """./data_plus 폴더 내 모든 JSON 처리 (딕셔너리 구조로 전달)"""
    if not os.path.exists(folder_path): return
    print(f"--- JSON 처리 시작: {folder_path} ---")

    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            file_path = os.path.join(folder_path, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)

                    # JSON이 리스트 형태인 경우 ([{...}, {...}])
                    if isinstance(data, list):
                        for item in data:
                            # 텍스트화 및 딕셔너리 구성
                            content = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
                            payload = {
                                "content": clean_text(content),
                                "embedding": embeddings.embed_query(clean_text(content)),
                                "metadata": {"source": filename, "type": "json_update"}
                            }
                            insert_to_supabase(payload)

                    # JSON이 단일 객체인 경우 ({...})
                    else:
                        content = json.dumps(data, ensure_ascii=False)
                        payload = {
                            "content": clean_text(content),
                            "embedding": embeddings.embed_query(clean_text(content)),
                            "metadata": {"source": filename, "type": "json_update"}
                        }
                        insert_to_supabase(payload)

                    print(f"✅ 완료: {filename}")
                except Exception as e:
                    print(f"❌ {filename} 처리 중 오류: {e}")


if __name__ == "__main__":
    # 각 폴더별 데이터 적재 실행
    #process_pdf_folder("./data")  # PDF 지침서
    #process_csv_folder("./data_csv")  # DUR 및 약물 정보
    process_json_folder("../data_plus")  # 심부전 지침 수정본 등

    print("\n🚀 모든 의료 지식 데이터가 Supabase에 통합되었습니다.")