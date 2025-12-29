FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies
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
RUN pip install --no-cache-dir -r requirements.txt

# Install development dependencies if they exist
# The wildcard * prevents the COPY from failing if the file is missing
COPY requirements-dev.txt* .
RUN if [ -f requirements-dev.txt ]; then \
        pip install --no-cache-dir -r requirements-dev.txt; \
    fi

# Copy application code
COPY . .

# Create non-root user and fix permissions
# We do this AFTER copying the code so the user owns the files
RUN useradd -m -u 1000 aquila && \
    chown -R aquila:aquila /app

USER aquila

# Default port (API Gateway standard)
EXPOSE 8000

# Fallback command - most services will override this in docker-compose.yml
CMD ["uvicorn", "services.api_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]