#!/bin/bash
set -e

echo "🚀 [Silver Sync] 100% 리눅스 환경 강제 빌드 - ARM64 패키징을 시작합니다..."

# 1. 이전 빌드 및 오염된 폴더/압축파일 흔적도 없이 삭제
rm -rf deploy_lambda silversync_lambda.zip
mkdir deploy_lambda

# 2. 순수 소스 코드만 먼저 격리 폴더로 복사
cp lambda_function.py deploy_lambda/
cp -r agent deploy_lambda/

cd deploy_lambda

# 💡 [핵심] --implementation, --python-version, --platform을 조합하여
# 맥북 환경을 완전히 무시하고 오직 '리눅스 Python 3.11 ARM64' 규격만 강제 다운로드합니다.
echo "📥 PyPI 서버에서 리눅스 전용 바이너리 직접 추출 중..."
pip install \
    --target . \
    --implementation cp \
    --python-version 3.11 \
    --platform manylinux2014_aarch64 \
    --only-binary=:all: \
    --no-cache-dir \
    --force-reinstall \
    requests pydantic python-dotenv httpx numpy boto3

# 3. 압축 파일에 맥북용 찌꺼기가 절대 섞이지 않도록 정밀 청소
echo "🧹 맥북 특유의 메타데이터 및 캐시 정밀 청소 중..."
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type f -name ".DS_Store" -delete
rm -rf *.dist-info *.egg-info

# 4. 압축 진행
echo "🗜️ silversync_lambda.zip 압축 생성 중..."
zip -r -q ../silversync_lambda.zip .

cd ..
rm -rf deploy_lambda

echo "🎉 완벽합니다! 기존 오염도가 100% 세탁된 'silversync_lambda.zip'이 완성되었습니다."