# Strategy Container - Python Trading Engine
FROM python:3.11-slim

LABEL maintainer="Trading Strategy"
LABEL description="Trading Strategy Runner Engine"

# Set timezone
ENV TZ=Asia/Kolkata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Set Python environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY run_strategy.py .
COPY export_dashboard_data.py .
COPY core ./core
COPY strategies ./strategies
COPY frontend ./frontend
COPY pytest.ini .
COPY .env.example .env.example

# Create necessary directories (logs will be mounted as volume)
RUN mkdir -p logs data

# Environment defaults
ENV STRATEGY=ema21 \
    MODE=live \
    SCRIPT=NIFTY

# Run strategy
CMD ["sh", "-c", "exec python3 run_strategy.py --script $SCRIPT --strategy $STRATEGY --mode $MODE"]
