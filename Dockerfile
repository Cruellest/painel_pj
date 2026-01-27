# Stage 1: Build Frontend
FROM node:20-slim AS builder

WORKDIR /app

# Copy necessary directories for build
COPY frontend/ ./frontend/
COPY sistemas/ ./sistemas/

# Install dependencies and build
WORKDIR /app/frontend
RUN npm install
RUN npm run build

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy built frontend assets from builder stage
# This ensures that even if local sistemas/ folder is empty of JS, the image has them.
# Note: If mounting volumes in docker-compose, local files might override this.
COPY --from=builder /app/sistemas ./sistemas

# Expose port
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
