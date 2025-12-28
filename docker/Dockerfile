FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install development dependencies if in dev mode
# Added a check to ensure the file exists before COPY to prevent build failure
COPY requirements-dev.txt* . 
RUN if [ -f requirements-dev.txt ]; then pip install --no-cache-dir -r requirements-dev.txt; fi

# Copy application code
COPY . .

# Ensure the app directory is in the python path
ENV PYTHONPATH=/app

# Create non-root user and set permissions
RUN useradd -m -u 1000 aquila && \
    chown -R aquila:aquila /app
USER aquila

EXPOSE 8000

# This default CMD acts as a fallback for the API Gateway, 
# but will be overridden by the 'command' in docker-compose for other services.
CMD ["uvicorn", "services.api_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]