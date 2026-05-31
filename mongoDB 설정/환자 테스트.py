# 테스트
from pymongo import MongoClient
import certifi

client = MongoClient(
    "mongodb+srv://SilverSynk:JWT5PovJL7hI1Jrd@cluster0.hts55d7.mongodb.net/?appName=Cluster0",
    tls=True,
    tlsCAFile=certifi.where()
)

db = client["silver_sync_db"]

# 쿼리 테스트
patient = db.patients.find_one({"patient_id": "P001"})
print(f"환자: {patient['name']}")  # 김철수

records = db.visit_records.find({"patient_id": "P001"}).sort("visit_date", -1)
print(f"진료 이력: {list(records)}")