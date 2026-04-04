FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/blogger/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared modules and service code
COPY shared/ /app/shared/
COPY config/ /app/config/
COPY data/agents/blogger/ /app/data/agents/blogger/
COPY services/blogger/ /app/services/blogger/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8103

CMD ["python", "-m", "services.blogger.main"]
