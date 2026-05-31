from pymongo import MongoClient
import pandas as pd

MONGO_URI = "mongodb+srv://SilverSynk:JWT5PovJL7hI1Jrd@cluster0.hts55d7.mongodb.net/?appName=Cluster0"
DB_NAME = "silver_sync_db"

client = MongoClient(MONGO_URI)


def check_all_collections():
    """전체 컬렉션 현황 확인"""
    print("=== 전체 컬렉션 현황 ===")
    db = client[DB_NAME]
    for col_name in db.list_collection_names():
        count = db[col_name].count_documents({})
        print(f"  {col_name}: {count}개")


def step1_delete_drug_interactions():
    """중간에 실패한 drug_interactions 전체 삭제"""
    dur_collection = client[DB_NAME]["drug_interactions"]
    count = dur_collection.count_documents({})
    print(f"drug_interactions 현재: {count}개")

    dur_collection.delete_many({})
    print(f"삭제 완료")
    print(f"남은 수: {dur_collection.count_documents({})}")


def step2_upload_dur_slim():
    """필요한 컬럼만 골라서 저장 (용량 최소화)"""
    dur_collection = client[DB_NAME]["drug_interactions"]

    try:
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

        # 전체 컬럼 확인
        print(f"전체 컬럼: {df.columns.tolist()}")
        print(f"총 행 수: {len(df)}")
        print(f"\n데이터 미리보기:")
        print(df.head(3).to_string())

    except Exception as e:
        print(f"CSV 로드 실패: {e}")


if __name__ == "__main__":
    # 현황 확인
    check_all_collections()

    # 1단계: 실패한 drug_interactions 삭제
    print("\n=== drug_interactions 삭제 ===")
    step1_delete_drug_interactions()

    # 2단계: 컬럼 확인 (어떤 컬럼이 있는지 먼저 파악)
    print("\n=== CSV 컬럼 확인 ===")
    step2_upload_dur_slim()