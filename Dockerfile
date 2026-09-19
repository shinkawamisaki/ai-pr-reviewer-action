# ベースイメージはパッチバージョンまで固定（更新は README の「依存の更新」参照）
FROM python:3.11.16-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
# requirements.txt は全推移依存をバージョンとハッシュで固定した生成物（requirements.in から生成）。
# --require-hashes により、固定したハッシュと一致しない配布物はインストールできない。
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# Copy application code and the bundled default prompt template
COPY reviewer.py .
COPY prompts/ ./prompts/

# Execute the reviewer script
ENTRYPOINT ["python", "/app/reviewer.py"]
