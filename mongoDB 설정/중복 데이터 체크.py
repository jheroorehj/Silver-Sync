from pymongo import MongoClient

MONGO_URI = "mongodb+srv://SilverSynk:JWT5PovJL7hI1Jrd@cluster0.hts55d7.mongodb.net/?appName=Cluster0"
DB_NAME = "silver_sync_db"
COLLECTION_NAME = "knowledge_base"

client = MongoClient(MONGO_URI)
collection = client[DB_NAME][COLLECTION_NAME]

# 현재 저장된 문서 수 확인
count = collection.count_documents({})
print(f"현재 저장된 문서 수: {count}")

# 중복 또는 불필요한 데이터 확인
# source별 문서 수 확인
pipeline = [
    {"$group": {"_id": "$source", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}}
]
for doc in collection.aggregate(pipeline):
    print(f"  {doc['_id']}: {doc['count']}개")