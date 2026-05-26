import json
import boto3
import os
from botocore.exceptions import ClientError

# DynamoDB 연결 설정
dynamodb = boto3.resource('dynamodb')

def handler(event, context):
    print('받은 이벤트:', json.dumps(event))
    
    # 1. 테이블 이름 설정 (Amplify에서 만든 테이블명)
    # 보통 'PatientVitals-프로젝트ID-개발환경' 형태입니다.
    table_name = os.environ.get('STORAGE_PATIENTVITALS_NAME')
    table = dynamodb.Table(table_name)
    
    try:
        # 2. 프론트엔드에서 보낸 데이터 추출
        # REST API를 통해 들어온 데이터는 event['body']에 문자열로 담겨 있습니다.
        body = json.loads(event['body'])
        
        # 3. 데이터 구성 (우리가 설계한 Key들)
        item = {
            'patientCode': body['patientCode'],   # Partition Key
            'timestamp': body['timestamp'],       # Sort Key
            'systolic': body['systolic'],   # 수축기 ( 가장 높은 압력)
            'diastolic': body['diastolic'], # 이완기 ( 가장 낮은 압력))
            'bloodSugar': body.get('bloodSugar', 0), # 입력없을시 0으로 입력
            'note': body.get('note', '') 
        }
        
        # 4. DynamoDB에 저장
        table.put_item(Item=item)
        
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': '*'
            },
            'body': json.dumps({'message': '데이터 저장 성공!', 'data': item})
        }
        
    except Exception as e:
        print('에러 발생:', str(e))
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': '*'
            },
            'body': json.dumps({'error': str(e)})
        }