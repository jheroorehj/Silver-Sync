from pymongo import MongoClient
import certifi

MONGO_URI = "mongodb+srv://SilverSynk:JWT5PovJL7hI1Jrd@cluster0.hts55d7.mongodb.net/?appName=Cluster0"

client = MongoClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
db = client["silver_sync_db"]

# 컬렉션별 용량 확인
for col_name in db.list_collection_names():
    stats = db.command("collstats", col_name)
    size_mb = stats["storageSize"] / (1024 * 1024)
    count = stats["count"]
    print(f"{col_name}: {count}개, {size_mb:.1f}MB")

# 전체 DB 용량
db_stats = db.command("dbstats")
total_mb = db_stats["storageSize"] / (1024 * 1024)
print(f"\n전체 DB 용량: {total_mb:.1f}MB / 512MB")