import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv

# --- MODULARIDAD: Conexión limpia con el núcleo ---
from src.core.orquestador import Orquestador

# --- TRAZABILIDAD ---
# Logger específico para la interfaz
logger = logging.getLogger("telegram_interface")
load_dotenv()

# Instancia Global del Orquestador (Singleton Pattern simplificado)
# Se inicia una vez y se reutiliza.
jarvis_core = Orquestador()

# Configuración de Seguridad (Zero-Trust) - Poka-Yoke para parseo de enteros
_user_id_raw = os.getenv("TELEGRAM_USER_ID", "0")
ALLOWED_USER_ID = int(_user_id_raw) if _user_id_raw and _user_id_raw.isdigit() else 0

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

    texto_usuario = update.message.text
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
        # Delegamos toda la lógica al Orquestador.
        respuesta = await jarvis_core.procesar_mensaje(str(ALLOWED_USER_ID), texto_usuario, audio_path)
        
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
    application.run_polling()