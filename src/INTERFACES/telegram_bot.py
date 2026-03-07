import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv

# --- MODULARIDAD: Conexión limpia con el núcleo ---
from src.core.orquestador import Orquestador
from src.core.repositories import JSONDataRepository, ChromaVectorRepository, DefaultToolsRepository
from src.utils.sanitizador import Sanitizador

# --- TRAZABILIDAD ---
# Logger específico para la interfaz
logger = logging.getLogger("telegram_interface")
load_dotenv()

# Instancia Global del Orquestador (Singleton Pattern simplificado)
# Se inicia una vez y se reutiliza inyectando las dependencias concretas.
jarvis_core = Orquestador(
    data_repo=JSONDataRepository(),
    vector_repo=ChromaVectorRepository(),
    tools_repo=DefaultToolsRepository()
)

# Configuración de Seguridad (Zero-Trust) - Poka-Yoke para parseo de enteros
_user_id_raw = os.getenv("TELEGRAM_USER_ID", "")
if not _user_id_raw or not _user_id_raw.isdigit():
    logger.critical("FATAL: TELEGRAM_USER_ID no configurado o inválido en .env.")
    ALLOWED_USER_ID = 0  # Evita que cualquiera pase. 0 no existe en Telegram.
else:
    ALLOWED_USER_ID = int(_user_id_raw)

async def seguridad_middleware(update: Update) -> bool:
    """
    Filtro de seguridad Zero-Trust.
    Verifica si el remitente es el Ingeniero autorizado.
    Retorna True si es seguro, False si es un intruso.
    """
    if not update.effective_user:
        return False
        
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        logger.warning(f"🚨 INTRUSO DETECTADO: Usuario {user_id} ({update.effective_user.username}) intentó acceder.")
        await update.message.reply_text("⛔ ACCESO DENEGADO. Protocolo de seguridad activado. Incidente reportado.")
        return False
    
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start: Reinicio de sesión."""
    if not await seguridad_middleware(update): return

    await update.message.reply_text(
        "🟢 **SISTEMA JARVIS V2 EN LÍNEA**\n"
        "Núcleo: Activo\n"
        "Memoria: Cargada\n"
        "Esperando instrucciones, Señor."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Manejador principal de mensajes de texto y notas de voz.
    Puente asíncrono hacia el Orquestador.
    """
    if not await seguridad_middleware(update): return

    # FAIL-SAFE: Ignorar tipos de mensaje no soportados (stickers, encuestas, etc.)
    if not update.message or (not update.message.text and not update.message.voice and not update.message.audio):
        logger.info("Ignorando mensaje no soportado (posiblemente sticker o vacío).")
        return
    
    # POKA-YOKE: Rechazar mensajes demasiado largos para evitar abuso/errores
    texto_usuario = update.message.text
    if texto_usuario and len(texto_usuario) > 2048:
        await update.message.reply_text("Tu mensaje es demasiado largo. Intenta ser más breve.")
        return

    # SANITIZACIÓN: Limpieza y validación PREVIA a cualquier procesamiento
    texto_limpio = Sanitizador.limpiar_texto(texto_usuario) if texto_usuario else ""
    if texto_limpio and not Sanitizador.validar_seguridad(texto_limpio):
        logger.warning(f"Intento de inyección bloqueado PREVIO al orquestador por usuario {ALLOWED_USER_ID}")
        await update.message.reply_text("⛔ Sistema de seguridad activado: Input rechazado.")
        return

    audio_path = None
    
    # Manejo de notas de voz o audios
    if update.message.voice or update.message.audio:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
        try:
            archivo_telegram = await (update.message.voice or update.message.audio).get_file()
            # Crear directorio temp si no existe
            os.makedirs("LOGS/temp", exist_ok=True)
            audio_path = os.path.join("LOGS/temp", f"audio_{update.message.message_id}.ogg")
            await archivo_telegram.download_to_drive(audio_path)
            logger.info(f"Audio descargado: {audio_path}")
        except Exception as e:
            logger.error(f"Error descargando audio: {e}")
            await update.message.reply_text("No pude procesar el archivo de audio.")
            return
    else:
        # Feedback inmediato para UX de texto
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # --- ACPLAMIENTO DÉBIL ---
        # Delegamos toda la lógica al Orquestador, pero ya con el texto limpio
        respuesta = await jarvis_core.procesar_mensaje(str(ALLOWED_USER_ID), texto_limpio, audio_path)
        
        # Respuesta al usuario
        await update.message.reply_text(respuesta)

    except Exception as e:
        logger.error(f"Error en interfaz Telegram: {e}")
        await update.message.reply_text("⚠️ Error de comunicación en la interfaz.")
    finally:
        # Limpieza de archivo temporal
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception as e:
                logger.error(f"No se pudo eliminar el archivo temporal {audio_path}: {e}")

def iniciar_bot():
    """Entry Point de la interfaz."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.critical("No se encontró TELEGRAM_TOKEN en .env")
        return

    # Construcción de la App (Builder Pattern)
    application = ApplicationBuilder().token(token).build()

    # Registro de Manejadores
    start_handler = CommandHandler('start', start)
    # Aceptamos tanto texto como voz/audio
    msg_handler = MessageHandler((filters.TEXT | filters.VOICE | filters.AUDIO) & (~filters.COMMAND), handle_message)

    application.add_handler(start_handler)
    application.add_handler(msg_handler)

    logger.info("🤖 Interfaz de Telegram lista y escuchando (Polling)...")
    
    # Ejecución Bloqueante (Main Loop)
    # Iniciamos el CRON justo después de que el loop asíncrono de Telegram arranca, 
    # utilizando el hook post_init de la aplicación.
    async def _post_init(app: ApplicationBuilder):
        from src.core.cron import iniciar_cron
        iniciar_cron()
        
    application.post_init = _post_init
    
    try:
        application.run_polling()
    finally:
        from src.core.cron import detener_cron
        detener_cron()
