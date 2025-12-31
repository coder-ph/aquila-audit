FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies
# Added dependencies often needed for PDF generation/Report imaging
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    libffi-dev \
    curl \
    make \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
# If you have a specific reporting requirements file, copy it too
COPY requirements-reporting.txt* . 

RUN pip install --no-cache-dir -r requirements.txt
RUN if [ -f requirements-reporting.txt ]; then \
        pip install --no-cache-dir -r requirements-reporting.txt; \
    fi

# Copy application code
COPY . .

# Create necessary directories for the Reporting Service
# These are the directories mentioned in your reporting-specific Dockerfile
RUN mkdir -p /app/data/reports/tenants \
    && mkdir -p /app/data/certificates \
    && mkdir -p /app/services/reporting_service/templates \
    && mkdir -p /app/services/reporting_service/assets

# Create non-root user and fix permissions
RUN useradd -m -u 1000 aquila && \
    chown -R aquila:aquila /app

USER aquila

# Default port (can be overridden by service)
EXPOSE 8000

# Default command (usually overridden in docker-compose)
CMD ["uvicorn", "services.api_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]