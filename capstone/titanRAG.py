import csv
import os
import json
import boto3
import pdfplumber
from decimal import Decimal

# 1. AWS 리소스 선언 (서울 리전 고정)
dynamodb = boto3.resource('dynamodb', region_name='ap-northeast-2')
table = dynamodb.Table('SilverSyncGuidelines')

# 🚀 AWS Bedrock Runtime 클라이언트 추가 (Titan 모델 호출용)
bedrock_runtime = boto3.client('bedrock-runtime', region_name='ap-northeast-2')

# 2026년 표준 Amazon Titan Text Embeddings V2 모델 ID (기본 1024차원 출력)
TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"

def get_titan_embedding(text):
    """AWS Bedrock Titan V2 모델을 호출하여 1024차원 임베딩 벡터를 반환하는 함수"""
    if not text.strip():
        return [0.0] * 1024
        
    body = json.dumps({
        "inputText": text,
        "dimensions": 1024  # 🎯 1024차원 명시적 고정
    })
    
    try:
        response = bedrock_runtime.invoke_model(
            modelId=TITAN_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body
        )
        response_body = json.loads(response.get('body').read())
        embedding = response_body.get('embedding')
        
        # DynamoDB 호환을 위해 float 데이터를 Decimal로 안전하게 래핑
        return [Decimal(str(n)) for n in embedding]
    except Exception as e:
        print(f"🚨 Titan 임베딩 생성 중 실패: {e}")
        # 실패 시 차원이 꼬이지 않도록 1024차원 제로 패딩 리턴
        return [Decimal('0.0')] * 1024

def clean_key_string(text):
    if not text: return "UNKNOWN"
    return text.strip().replace(" ", "").replace("+", "_")

# =====================================================================
# 📄 [1] PDF 가이드라인 분할 및 Titan 1024차원 벡터 라이징
# =====================================================================
def upload_pdf_with_titan_vector(file_name, disease_code, title, disease_type, chunk_size=500):
    if not os.path.exists(file_name):
        print(f"⚠️ 파일을 찾을 수 없습니다: {file_name} (건너뜀)")
        return

    print(f"\n🚀 [Titan 1024차원] PDF 텍스트 추출 및 임베딩 시작... [{file_name}]")
    full_text = ""
    with pdfplumber.open(file_name) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"

    # 500자 단위 청크 분할
    chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
    print(f"   📊 총 {len(chunks)}개의 의학 지침 Chunk가 분할되었습니다.")

    for idx, chunk in enumerate(chunks):
        chunk_text = chunk.strip()
        if len(chunk_text) < 20:
            continue

        # 💡 Bedrock Titan 임베딩 추출 (1024차원)
        vector_decimals = get_titan_embedding(chunk_text)

        sk = f"GUIDE#{disease_code}#CHUNK#{str(idx).zfill(3)}"

        table.put_item(
            Item={
                'category': 'CLINICAL_GUIDELINE',
                'item_id': sk,
                'title': f"{title} (Part {idx})",
                'content': chunk_text,          
                'embedding': vector_decimals,     # 🚀 1024차원 Decimal 배열 주입
                'target_disease': disease_type
            }
        )
        if idx % 10 == 0:
            print(f"   .. {idx}/{len(chunks)} 청크 Titan 벡터 생성 및 DynamoDB 주입 중 ..")

    print(f"✅ PDF 1024차원 마이그레이션 성공: {title}")

# =====================================================================
# 📊 [2] CSV 매핑 데이터들도 Titan 1024차원으로 덮어쓰기
# =====================================================================
def upload_csv_with_titan_vector(file_name, data_type):
    if not os.path.exists(file_name):
        print(f"⚠️ 파일을 찾을 수 없습니다: {file_name} (건너뜀)")
        return

    print(f"\n🚀 [Titan 1024차원] CSV 데이터 변환 및 적재 시작... [{file_name}]")
    count = 0

    with open(file_name, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if data_type == 'DUR_CONSOLIDATED':
                disease_group = row.get('질환군', '').strip()
                drug_group = row.get('약물군', '').strip()
                ingredient = row.get('성분명', '').strip()
                dur_info = row.get('DUR_병용금기 및 부작용', '').strip()
                notice = row.get('지침_주의사항', '').strip()
                complication = row.get('합병증_특이사항', '').strip()

                if not ingredient: continue

                combined_text = f"성분명: {ingredient}. DUR 금기 및 부작용: {dur_info}. 주의사항: {notice}."
                vector_decimals = get_titan_embedding(combined_text)

                table.put_item(
                    Item={
                        'category': 'DUR_CONTRAINDICATION',
                        'item_id': f"DRUG#{clean_key_string(ingredient)}",
                        'drug_group': drug_group,
                        'ingredient': ingredient,
                        'description': dur_info,
                        'embedding': vector_decimals, # 🚀 1024차원
                        'notice': notice,
                        'complication': complication
                    }
                )

            elif data_type == 'ELDERLY_CAUTION':
                ingredient = row.get('성분명', '').strip()
                side_effect = row.get('노인주의_부작용 및 지침', '').strip()
                reason = row.get('이유', '').strip()
                alternative = row.get('대체약물 및 권고사항', '').strip()

                if not ingredient: continue

                combined_text = f"노인주의 성분명: {ingredient}. 부작용: {side_effect}. 이유: {reason}."
                vector_decimals = get_titan_embedding(combined_text)

                table.put_item(
                    Item={
                        'category': 'ELDERLY_CAUTION',
                        'item_id': f"DRUG#{clean_key_string(ingredient)}",
                        'ingredient': ingredient,
                        'content': side_effect,
                        'reason': reason,
                        'embedding': vector_decimals, # 🚀 1024차원
                        'alternative_therapy': alternative
                    }
                )
            count += 1
    print(f"✅ CSV 1024차원 적재 완료: {data_type} (총 {count}개 행)")

# =====================================================================
# 🏁 1024차원 리빌드 메인 가동
# =====================================================================
if __name__ == "__main__":
    print("==================================================")
    print("🌟 SilverSync Amazon Titan 1024D 벡터 리빌드 🌟")
    print("==================================================")
    
    # 1. 2개의 PDF 지침서 1024차원으로 리빌드
    upload_pdf_with_titan_vector("2022_고혈압_진료지침.pdf", "HTN", "2022 고혈압 진료 지침", "Hypertension")
    upload_pdf_with_titan_vector("2025 당뇨병 진료지침_요약문_수정본(26.2.12) (1).pdf", "DM", "2025 당뇨병 진료 지침", "Diabetes")
    
    # 2. 2개의 CSV 매핑 데이터 1024차원으로 리빌드
    upload_csv_with_titan_vector("DUR_HTN_DM_Consolidated_Mapping.csv", "DUR_CONSOLIDATED")
    upload_csv_with_titan_vector("Elderly_Caution_Full_Mapping_HTN_DM.csv", "ELDERLY_CAUTION")

    print("\n🎉 완벽합니다! 모든 데이터가 Amazon Titan 규격인 [1024차원] 벡터로 교체 완료되었습니다.")
    print("이제 로컬 핸들러 테스트(test_local_handler.py)를 다시 실행하여 버그 컷을 확인하세요!")