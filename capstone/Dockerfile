FROM public.ecr.aws/lambda/python:3.11

WORKDIR ${LAMBDA_TASK_ROOT}

# 1. 시스템 라이브러리 설치
RUN dnf install -y gcc gcc-c++ libgomp openblas-devel mesa-libGL || yum install -y gcc gcc-c++ libgomp openblas-devel mesa-libGL

# 2. 람다 환경 극복을 위한 환경변수 (joblib 및 모든 캐시를 /tmp로 완벽 우회)
ENV PIP_PREFER_BINARY=1
ENV HF_HOME=/tmp/huggingface
ENV TRANSFORMERS_CACHE=/tmp/huggingface
ENV TORCH_HOME=/tmp/torch
ENV JOBLIB_TEMP_FOLDER=/tmp
ENV MPLCONFIGDIR=/tmp
ENV NUMBA_CACHE_DIR=/tmp
ENV TMPDIR=/tmp
ENV XDG_CACHE_HOME=/tmp
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .

# 3. [핵심 수술 🚨] 제가 걸어두었던 torch==2.2.2 족쇄를 해제하고 최신 버전(2.4 이상)을 받도록 수정했습니다!
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "numpy<2.0" scipy scikit-learn && \
    pip install --no-cache-dir torch sentence-transformers langchain-huggingface && \
    pip install --no-cache-dir -r requirements.txt

COPY . ${LAMBDA_TASK_ROOT}/

CMD [ "lambda_function.handler" ]