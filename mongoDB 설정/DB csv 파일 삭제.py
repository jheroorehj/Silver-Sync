from pymongo import MongoClient
import pandas as pd

MONGO_URI = "mongodb+srv://SilverSynk:JWT5PovJL7hI1Jrd@cluster0.hts55d7.mongodb.net/?appName=Cluster0"
DB_NAME = "silver_sync_db"

client = MongoClient(MONGO_URI)


def upload_dur_slim():
    dur_collection = client[DB_NAME]["drug_interactions"]

    # 기존 데이터 삭제
    existing = dur_collection.count_documents({})
    if existing > 0:
        dur_collection.delete_many({})
        print(f"기존 {existing}개 삭제 완료")

    # CSV 로드
    try:
        df = pd.read_csv(
            "../data_csv/의약품안전사용서비스(DUR)_병용금기 품목리스트 2025.6.csv",
            encoding="cp949",
            low_memory=False
        )
    except UnicodeDecodeError:
        df = pd.read_csv(
            "../data_csv/의약품안전사용서비스(DUR)_병용금기 품목리스트 2025.6.csv",
            encoding="utf-8",
            low_memory=False
        )

    print(f"원본 행 수: {len(df)}")

    # 핵심 컬럼만 선택 (용량 최소화)
    df_slim = df[["성분명A", "성분명B", "상세정보", "고시일자"]].copy()

    # 중복 제거 (성분명A + 성분명B 조합이 같은 것 제거)
    before = len(df_slim)
    df_slim = df_slim.drop_duplicates(subset=["성분명A", "성분명B"])
    after = len(df_slim)
    print(f"중복 제거: {before}행 → {after}행 ({before - after}개 제거)")

    # NaN 처리
    df_slim = df_slim.fillna("")

    # 배치 삽입
    records = df_slim.to_dict("records")
    batch_size = 1000
    total_batches = (len(records) - 1) // batch_size + 1

    print(f"총 {len(records)}개 삽입 시작")

    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        dur_collection.insert_many(batch)
        print(f"  배치 {i // batch_size + 1}/{total_batches} 완료 ({len(batch)}개)")

    # 인덱스 생성 (검색 속도 향상)
    dur_collection.create_index([("성분명A", 1)])
    dur_collection.create_index([("성분명B", 1)])
    print("인덱스 생성 완료")

    final_count = dur_collection.count_documents({})
    print(f"\n최종 저장: {final_count}개")

    # 전체 현황
    print("\n=== 전체 컬렉션 현황 ===")
    db = client[DB_NAME]
    for col_name in db.list_collection_names():
        count = db[col_name].count_documents({})
        print(f"  {col_name}: {count}개")


if __name__ == "__main__":
    upload_dur_slim()