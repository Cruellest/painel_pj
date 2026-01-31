# ==============================================================================
# STAGE 1: Build Frontend (Node.js)
# ==============================================================================
FROM node:22-alpine AS frontend-builder

WORKDIR /app

# Copy apenas os arquivos necessários para build do frontend
COPY frontend/package*.json ./frontend/
COPY frontend/scripts/ ./frontend/scripts/
COPY frontend/src/ ./frontend/src/
COPY frontend/tsconfig.json ./frontend/
COPY sistemas/ ./sistemas/

# Install dependencies e build
WORKDIR /app/frontend
RUN npm ci && npm run build

# Limpa cache npm para reduzir tamanho
RUN rm -rf node_modules .npm

# ==============================================================================
# STAGE 2: Runtime
# ==============================================================================
FROM python:3.12-slim

WORKDIR /app

# Security: Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install runtime dependencies (libpq, não build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install Python dependencies (simples e direto)
COPY requirements_app.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements_app.txt

# Copy aplicação (último layer - muda frequentemente)
# Copia arquivos essenciais apenas (respeitando .dockerignore)
COPY --chown=appuser:appuser main.py config.py ./
COPY --chown=appuser:appuser admin/ ./admin/
COPY --chown=appuser:appuser auth/ ./auth/
COPY --chown=appuser:appuser database/ ./database/
COPY --chown=appuser:appuser middleware/ ./middleware/
COPY --chown=appuser:appuser services/ ./services/
COPY --chown=appuser:appuser sistemas/ ./sistemas/
COPY --chown=appuser:appuser users/ ./users/
COPY --chown=appuser:appuser utils/ ./utils/

# Copy frontend built assets (do estágio 1)
# Build output vai para ../sistemas/ (não para dist/)
COPY --from=frontend-builder --chown=appuser:appuser /app/sistemas/ ./sistemas/

# Create all directories with proper permissions BEFORE switching to non-root user
RUN mkdir -p frontend/templates frontend/static logs performance && \
    chmod 777 logs && \
    chmod 777 performance && \
    chmod 755 frontend && \
    chown -R appuser:appuser .

# Copy templates (HTML, CSS, JS estáticos)
COPY --chown=appuser:appuser frontend/templates/ ./frontend/templates/
COPY --chown=appuser:appuser frontend/static/ ./frontend/static/

# Copy logo and other static assets
COPY --chown=appuser:appuser logo/ ./logo/

# Security: Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
