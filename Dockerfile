# AWS Expert Agent - AgentCore Runtime Container
# ARM64 (Graviton) architecture

FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.11-slim

WORKDIR /app

# System deps + AWS CLI v2 (ARM64)
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip && \
    curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o awscliv2.zip && \
    unzip -q awscliv2.zip && ./aws/install && \
    rm -rf aws awscliv2.zip /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code + bundled data
COPY agent_runtime.py .
COPY IDENTITY.md .
COPY skills/ /app/skills/

EXPOSE 8080

# Start with app.run() inside agent_runtime.py
CMD ["python", "agent_runtime.py"]
