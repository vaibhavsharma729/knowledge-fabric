FROM --platform=linux/amd64 python:3.11-slim

# Install Node.js 20 + nginx (nginx proxies WebSocket connections to Streamlit)
RUN apt-get update && apt-get install -y curl nginx && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Credentials come from AWS Secrets Manager via the task IAM role.
# Non-sensitive config is passed as environment variables.
ENV COPILOT_ENDPOINT=https://models.inference.ai.azure.com \
    COPILOT_MODEL=gpt-4o

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
  CMD curl -f http://localhost:8501/_stcore/health || exit 1

RUN chmod +x /app/start.sh

# nginx listens on 8501 (App Runner's port) and proxies WebSocket to Streamlit on 8502
CMD ["/app/start.sh"]
