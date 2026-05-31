from pymongo import MongoClient

MONGO_URI = "mongodb+srv://SilverSynk:JWT5PovJL7hI1Jrd@cluster0.hts55d7.mongodb.net/?appName=Cluster0"
DB_NAME = "silver_sync_db"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

print("=== 현재 컬렉션 현황 ===")
for col_name in db.list_collection_names():
    count = db[col_name].count_documents({})
    print(f"  {col_name}: {count}개")

# knowledge_base source별 현황
print("\n=== knowledge_base 상세 ===")
collection = db["knowledge_base"]
pipeline = [
    {"$group": {"_id": "$source", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}}
]
for doc in collection.aggregate(pipeline):
    print(f"  {doc['_id']}: {doc['count']}개")