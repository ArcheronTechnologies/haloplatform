FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Copy application code
COPY src/halo/ ./src/halo/
COPY scripts/ ./scripts/
COPY models/ ./models/

# Set Python path to include src
ENV PYTHONPATH=/app/src

# Create non-root user
RUN useradd -m -u 1000 halo && chown -R halo:halo /app
USER halo

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "halo.main:app", "--host", "0.0.0.0", "--port", "8000"]
