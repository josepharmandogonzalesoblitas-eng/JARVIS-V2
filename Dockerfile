# ==========================================
# ETAPA 1: BUILDER (Compilación de dependencias)
# ==========================================
FROM python:3.12-slim AS builder

# Configuración básica para el instalador
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Instalar dependencias del sistema necesarias para compilar librerías en C/C++ (ej. ChromaDB/Numpy)
# ffmpeg: requerido para gTTS (conversión de audio para Telegram Voice)
# libgomp1: requerido para ChromaDB/numpy en ARM64
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Configurar entorno virtual para aislar dependencias
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copiar solo el requirements primero para cachear la instalación
COPY requirements.txt .

# Instalar dependencias como ruedas compiladas
RUN pip install --no-cache-dir pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# ==========================================
# ETAPA 2: RUNNER (Imagen final de Producción)
# ==========================================
FROM python:3.12-slim AS runner

# Variables de entorno
# MPLBACKEND=Agg: fuerza a matplotlib a usar backend no-interactivo (sin pantalla)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    MPLBACKEND=Agg

# Instalar solo certificados y dependencias dinámicas si fuera necesario, sin compiladores
# ffmpeg: requerido en runtime para gTTS (TTS de voz)
# libgomp1: requerido por chromadb/numpy en ARM64
# fonts-dejavu: para que matplotlib genere gráficos correctamente
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    ffmpeg \
    libgomp1 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Crear usuario no root por seguridad (Least Privilege Principle)
RUN useradd --create-home appuser

# Copiar el entorno virtual ya compilado de la Etapa 1
COPY --from=builder /opt/venv /opt/venv

# Copiar el código fuente
COPY --chown=appuser:appuser src/ src/
COPY --chown=appuser:appuser main.py .

# Poka-Yoke: Asegurar la creación de volúmenes requeridos con permisos correctos
RUN mkdir -p /app/MEMORIA /app/LOGS && \
    chown -R appuser:appuser /app/MEMORIA /app/LOGS

# Cambiar a usuario sin privilegios
USER appuser

# Entrypoint seguro
CMD ["python", "main.py"]
