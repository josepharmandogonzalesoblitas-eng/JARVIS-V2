#!/bin/bash
# ==============================================================================
# SCRIPT DE INICIALIZACIÓN DE SERVIDOR - ORACLE CLOUD ARM64 (Ubuntu 24.04)
# Principios: Idempotencia, Zero-Trust, Fail-Safe
# ==============================================================================

set -e # Fail-fast: Detiene la ejecución en caso de error

echo "🚀 Iniciando aprovisionamiento del servidor (Ubuntu 24.04 ARM64)..."

# 1. Configurar Swap de 4GB (Fail-Safe)
# ------------------------------------------------------------------------------
# Evita caídas por picos de memoria (OOM Kills), especialmente útil para Jarvis.
if [ ! -f /swapfile ]; then
    echo "⚙️ Configurando Swap de 4GB..."
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab
    echo "✅ Swap de 4GB configurado exitosamente."
else
    echo "✅ Swap ya configurado. Operación Idempotente: Omitiendo."
fi

# 2. Configurar Firewall (Zero-Trust)
# ------------------------------------------------------------------------------
# Solo permitimos puertos esenciales.
echo "🛡️ Configurando UFW (Firewall)..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp  # SSH
ufw allow 80/tcp  # HTTP
ufw allow 443/tcp # HTTPS
ufw allow 81/tcp  # Nginx Proxy Manager (Panel de Administración)
ufw --force enable
echo "✅ UFW configurado exitosamente."

# 3. Instalar Docker y Docker Compose (Multi-arch ARM64)
# ------------------------------------------------------------------------------
if ! command -v docker &> /dev/null; then
    echo "🐳 Instalando Docker (Optimizado para ARM64)..."
    apt-get update
    apt-get install -y ca-certificates curl gnupg lsb-release

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    echo "✅ Docker instalado exitosamente."
else
    echo "✅ Docker ya está instalado. Operación Idempotente: Omitiendo."
fi

# Asegurar que el servicio está activo
systemctl enable docker
systemctl start docker

# 4. Crear Red Externa (Low-Coupling)
# ------------------------------------------------------------------------------
# Red para que Nginx Proxy Manager se comunique con Jarvis y Buho.
if ! docker network ls | grep -q "proxy_net"; then
    echo "🌐 Creando red de docker 'proxy_net'..."
    docker network create proxy_net
    echo "✅ Red 'proxy_net' creada."
else
    echo "✅ Red 'proxy_net' ya existe. Operación Idempotente: Omitiendo."
fi

echo "=============================================================================="
echo "🎉 APROVISIONAMIENTO COMPLETADO."
echo "Servidor listo para recibir contenedores ARM64."
echo "=============================================================================="
