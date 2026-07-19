# A1.Flex(ARM64) 노드에서 직접 빌드하므로 멀티아치 base 이미지면 충분하다.
FROM python:3.13-slim

WORKDIR /app

# 의존성만 먼저 복사해 레이어 캐시를 살린다(코드만 바뀌면 재설치 안 함).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# DB/업로드는 마운트된 볼륨(/data)에 둔다. compose에서 볼륨을 걸어 영속화한다.
ENV DATABASE_URL=sqlite:////data/app.db
ENV UPLOAD_DIR=/data/uploads

EXPOSE 8000

# 시작 시 테이블 생성+시드(멱등)를 먼저 돌리고 서버를 띄운다.
CMD ["sh", "-c", "python -m app.init_db && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
