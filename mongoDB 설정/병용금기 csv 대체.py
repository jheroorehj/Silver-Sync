from pymongo import MongoClient
import pandas as pd

MONGO_URI = "mongodb+srv://SilverSynk:JWT5PovJL7hI1Jrd@cluster0.hts55d7.mongodb.net/?appName=Cluster0"
DB_NAME = "silver_sync_db"

client = MongoClient(MONGO_URI)


def upload_dur_to_separate_collection():
    """병용금기는 별도 컬렉션에 일반 저장 (벡터 아님)"""

    # 별도 컬렉션 (knowledge_base 아님 → 용량 영향 없음)
    dur_collection = client[DB_NAME]["drug_interactions"]

    # 기존 데이터 있으면 삭제
    existing = dur_collection.count_documents({})
    if existing > 0:
        dur_collection.delete_many({})
        print(f"기존 데이터 {existing}개 삭제")

    # CSV 로드
    try:
        df = pd.read_csv(
            "../data_csv/의약품안전사용서비스(DUR)_병용금기 품목리스트 2025.6.csv",
            encoding="cp949"
        )
    except UnicodeDecodeError:
        df = pd.read_csv(
            "../data_csv/의약품안전사용서비스(DUR)_병용금기 품목리스트 2025.6.csv",
            encoding="utf-8"
        )

    print(f"컬럼: {df.columns.tolist()}")
    print(f"총 행 수: {len(df)}")

    # 배치로 나눠서 삽입 (한번에 너무 많으면 느림)
    records = df.to_dict("records")
    batch_size = 1000

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        dur_collection.insert_many(batch)
        print(f"  배치 {i // batch_size + 1}/{(len(records) - 1) // batch_size + 1} 완료 ({len(batch)}개)")

    print(f"\n저장 완료: {dur_collection.count_documents({})}개")
    print("컬렉션명: drug_interactions (별도 저장)")


if __name__ == "__main__":
    upload_dur_to_separate_collection()