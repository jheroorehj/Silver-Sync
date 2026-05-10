import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def verify_data():
    print("📡 Supabase 데이터 연결 확인 중...")
    try:
        # 데이터 5개만 샘플로 가져오기
        response = supabase.table("knowledge_base").select("content, metadata, embedding").limit(5).execute()

        if not response.data:
            print("❌ 데이터가 비어있습니다. 적재 과정을 다시 확인하세요.")
            return

        print(f"✅ 샘플 데이터를 찾았습니다. (총 적재량 확인은 SQL 쿼리 권장)\n")
        for i, row in enumerate(response.data):
            source = row['metadata'].get('source', 'N/A')
            content_preview = row['content'][:50].replace('\n', ' ') + "..."
            has_embedding = "있음" if row.get('embedding') else "없음"

            print(f"[{i + 1}] 소스: {source}")
            print(f"    내용: {content_preview}")
            print(f"    임베딩: {has_embedding}")
            print("-" * 30)

    except Exception as e:
        print(f"❌ DB 연결 오류: {e}")


if __name__ == "__main__":
    verify_data()