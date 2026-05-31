import os
import pandas as pd
import json
from dotenv import load_dotenv
from supabase import create_client
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from pathlib import Path
import time

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


def batch_clear_knowledge_base():
    """배치 방식으로 데이터 삭제 (타임아웃 방지)"""
    print("🗑️  기존 데이터 배치 삭제 중...")
    try:
        batch_size = 500
        deleted_count = 0

        while True:
            # 500개씩 가져오기
            result = supabase.table("knowledge_base").select("id").limit(batch_size).execute()

            if not result.data:
                break

            # ID 리스트
            ids = [row['id'] for row in result.data]

            # ID를 문자열로 변환하여 OR 조건으로 삭제
            for id_val in ids:
                supabase.table("knowledge_base").delete().eq("id", id_val).execute()

            deleted_count += len(ids)
            print(f"   ✅ {deleted_count}개 행 삭제")

            time.sleep(0.5)  # API 요청 제한 방지

        print(f"✅ 총 {deleted_count}개 데이터 삭제 완료\n")

    except Exception as e:
        print(f"❌ 삭제 중 오류: {e}\n")


def insert_to_supabase(data):
    """중복 방지(upsert) 기능이 포함된 통합 삽입 함수"""
    if not data:
        return

    try:
        supabase.table("knowledge_base").upsert(
            data,
            on_conflict='content'
        ).execute()
    except Exception as e:
        if "23505" in str(e):  # PostgreSQL 중복 키 에러 코드
            pass
        else:
            print(f"❌ Supabase 처리 오류: {e}")


def process_pdf_folder(folder_path):
    """./data 폴더 내 모든 PDF 처리"""
    if not os.path.exists(folder_path):
        print(f"⚠️  {folder_path} 폴더를 찾을 수 없습니다.\n")
        return

    pdf_files = list(Path(folder_path).glob("*.pdf"))

    if not pdf_files:
        print(f"⚠️  {folder_path}에 PDF 파일이 없습니다.\n")
        return

    print(f"--- PDF 처리 시작: {folder_path} ({len(pdf_files)}개 파일) ---")

    total_chunks = 0
    for pdf_file in pdf_files:
        try:
            loader = PyPDFLoader(str(pdf_file))
            pages = loader.load()
            chunks = text_splitter.split_documents(pages)

            for chunk in chunks:
                payload = {
                    "content": clean_text(chunk.page_content),
                    "embedding": embeddings.embed_query(clean_text(chunk.page_content)),
                    "metadata": {**chunk.metadata, "source": pdf_file.name}
                }
                insert_to_supabase(payload)

            total_chunks += len(chunks)
            print(f"✅ 완료: {pdf_file.name} ({len(chunks)}개 청크)")

        except Exception as e:
            print(f"❌ {pdf_file.name} 처리 중 오류: {e}")

    print(f"📊 PDF 총 {total_chunks}개 청크 임베딩 완료\n")


def process_csv_folder(folder_path):
    """CSV 처리를 벌크 방식으로 전환"""
    if not os.path.exists(folder_path):
        print(f"⚠️  {folder_path} 폴더를 찾을 수 없습니다.\n")
        return

    csv_files = list(Path(folder_path).glob("*.csv"))

    if not csv_files:
        print(f"⚠️  {folder_path}에 CSV 파일이 없습니다.\n")
        return

    print(f"--- CSV 벌크 처리 시작: {folder_path} ({len(csv_files)}개 파일) ---")

    total_rows = 0
    for csv_file in csv_files:
        # 인코딩 시도
        for encoding in ['utf-8', 'cp949', 'euc-kr']:
            try:
                df = pd.read_csv(str(csv_file), encoding=encoding, low_memory=False).head(5000)
                print(f"✅ {encoding} 로드 성공: {csv_file.name} (총 {len(df)}행)")

                bulk_data = []
                for i, (_, row) in enumerate(df.iterrows()):
                    content = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                    clean_content = clean_text(content)

                    if not clean_content:
                        continue

                    embedding = embeddings.embed_query(clean_content)
                    bulk_data.append({
                        "content": clean_content,
                        "embedding": embedding,
                        "metadata": {"source": csv_file.name}
                    })

                    # 50개씩 묶어서 전송
                    if len(bulk_data) >= 50:
                        insert_to_supabase(bulk_data)
                        bulk_data = []
                        if i % 100 == 0:
                            print(f"   ㄴ 진행 중... {i}/{len(df)} 행 완료")

                # 남은 데이터 전송
                if bulk_data:
                    insert_to_supabase(bulk_data)

                total_rows += len(df)
                print(f"✅ 적재 완료: {csv_file.name} ({len(df)}행)\n")
                break

            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"❌ {csv_file.name} 처리 중 오류: {e}\n")
                break


def process_json_folder(folder_path):
    """JSON 처리"""
    if not os.path.exists(folder_path):
        print(f"⚠️  {folder_path} 폴더를 찾을 수 없습니다.\n")
        return

    json_files = list(Path(folder_path).glob("*.json"))

    if not json_files:
        print(f"⚠️  {folder_path}에 JSON 파일이 없습니다.\n")
        return

    print(f"--- JSON 처리 시작: {folder_path} ({len(json_files)}개 파일) ---")

    total_items = 0
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

                if isinstance(data, list):
                    for item in data:
                        content = json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
                        payload = {
                            "content": clean_text(content),
                            "embedding": embeddings.embed_query(clean_text(content)),
                            "metadata": {"source": json_file.name, "type": "json_update"}
                        }
                        insert_to_supabase(payload)

                    total_items += len(data)
                    print(f"✅ 완료: {json_file.name} ({len(data)}개 항목)")

                else:
                    content = json.dumps(data, ensure_ascii=False)
                    payload = {
                        "content": clean_text(content),
                        "embedding": embeddings.embed_query(clean_text(content)),
                        "metadata": {"source": json_file.name, "type": "json_update"}
                    }
                    insert_to_supabase(payload)

                    total_items += 1
                    print(f"✅ 완료: {json_file.name} (1개 항목)")

        except Exception as e:
            print(f"❌ {json_file.name} 처리 중 오류: {e}")

    print(f"📊 JSON 총 {total_items}개 항목 임베딩 완료\n")


def main():
    """메인 함수"""
    print("\n" + "=" * 70)
    print("🔄 Supabase 데이터 초기화 및 재임베딩")
    print("=" * 70 + "\n")

    # 1. 기존 데이터 삭제 (배치 방식)
    batch_clear_knowledge_base()

    # 2. 데이터 적재 실행
    process_pdf_folder("../data")
    process_csv_folder("../data_csv")
    process_json_folder("../data_plus")

    print("=" * 70)
    print("✅ 모든 의료 지식 데이터가 Supabase에 통합되었습니다.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()