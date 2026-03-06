# Guía de Despliegue en Oracle Cloud (ARM64)
# Principios: Low-Coupling, Zero-Trust, Big-O Efficiency

Esta guía detalla cómo desplegar las aplicaciones `JARVIS_V2` y `BUHO-SaaS` en una instancia Ampere ARM64 de Oracle Cloud (Ubuntu 24.04). Todo el sistema está orquestado mediante Nginx Proxy Manager en una red interna para minimizar vectores de ataque (Zero-Trust).

---

## 🚀 PASO 1: Generación de Imágenes Multi-Arch (Local)
Para no saturar la OCPU de Oracle Cloud durante la compilación y mantener la **Big-O Efficiency**, compilaremos las imágenes localmente y las empujaremos a un Registry (ej. Docker Hub o GitHub Container Registry).

### En tu PC local (x86_64/Windows/Mac):
Asegúrate de tener Docker Desktop o Buildx instalado.
Ejecuta esto en los respectivos repositorios:

```bash
# Compilar e inyectar JARVIS_V2
docker buildx create --use
docker buildx build --platform linux/arm64 -t tu_usuario/jarvis-v2:arm64-latest --push .

# Compilar e inyectar BUHO_SAAS
docker buildx build --platform linux/arm64 -t tu_usuario/buho-saas:arm64-latest --push .
```
*(Asegúrate de hacer login en docker `docker login` antes de lanzar los comandos)*

---

## 🚀 PASO 2: Sincronización al Servidor Oracle
Vamos a subir la estructura `DEPLOY_ORACLE` al servidor en la nube. Reemplaza `TU_IP` y asegúrate de tener la llave SSH (`.key` o `.pem`).

### Desde tu terminal local:
```bash
# Subir todo el directorio mediante scp recursivo
scp -i ruta/a/tu_llave.key -r ./DEPLOY_ORACLE ubuntu@TU_IP:/home/ubuntu/
```

---

## 🚀 PASO 3: Aprovisionamiento del Servidor
Conéctate por SSH y ejecuta el script de inicialización Idempotente.

### SSH y Setup:
```bash
# 1. Conectar al Servidor
ssh -i ruta/a/tu_llave.key ubuntu@TU_IP

# 2. Navegar al directorio copiado
cd /home/ubuntu/DEPLOY_ORACLE

# 3. Dar permisos de ejecución
chmod +x init_server.sh

# 4. Ejecutar como ROOT (o con sudo)
sudo ./init_server.sh
```

El script configurará Swap, Docker (ARM64), UFW, y la Red Externa `proxy_net`.

---

## 🚀 PASO 4: Configurar Variables de Entorno (Zero-Trust)
Nunca commitees los `.env`. Debemos configurarlos manualmente ahora:

```bash
# Navegar a Config
cd /home/ubuntu/DEPLOY_ORACLE/config

# Renombrar los examples y editarlos (usando nano o vi)
mv .env.jarvis.example .env.jarvis
mv .env.buho.example .env.buho

nano .env.jarvis
# Llena los datos como TELEGRAM_BOT_TOKEN...
```

---

## 🚀 PASO 5: Despliegue Secuencial (Low-Coupling)
Iniciaremos los servicios de forma individual usando sus respectivos `docker-compose.yml`.

```bash
# 1. Iniciar Nginx Proxy Manager (Punto de Entrada Centralizado)
cd /home/ubuntu/DEPLOY_ORACLE/app/nginx-proxy
sudo docker compose up -d

# 2. Iniciar JARVIS V2
cd /home/ubuntu/DEPLOY_ORACLE/app/jarvis-v2
sudo docker compose up -d

# 3. Iniciar BUHO SAAS
cd /home/ubuntu/DEPLOY_ORACLE/app/buho-saas
sudo docker compose up -d
```

---

## ✅ PASO 6: Configurar Dominios (Nginx Proxy Manager)
1. Ve a tu navegador y entra en: `http://TU_IP:81`
2. **Credenciales por defecto:**
   - Email: `admin@example.com`
   - Password: `changeme`
3. Configura tus "Proxy Hosts":
   - **Domain:** `tu-dominio.com` (o subdominio)
   - **Forward Hostname / IP:** `buho_saas` (nombre del contenedor)
   - **Forward Port:** `80` (o el que use internamente tu app)
   - Marca "Block Common Exploits"
   - Genera tu certificado SSL en la pestaña SSL.

¡LISTO! Tu entorno de producción Fail-Safe y Zero-Trust está activo.
