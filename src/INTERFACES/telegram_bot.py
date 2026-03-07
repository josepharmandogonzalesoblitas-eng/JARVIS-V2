import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv

from src.core.orquestador import Orquestador
from src.core.repositories import JSONDataRepository, ChromaVectorRepository, DefaultToolsRepository
from src.core.conversation_state import conversation_state_manager
from src.utils.sanitizador import Sanitizador

logger = logging.getLogger("telegram_interface")
load_dotenv()

# ─── INSTANCIA GLOBAL DEL ORQUESTADOR ────────────────────────────────────────
jarvis_core = Orquestador(
    data_repo=JSONDataRepository(),
    vector_repo=ChromaVectorRepository(),
    tools_repo=DefaultToolsRepository()
)

# ─── SEGURIDAD ZERO-TRUST ─────────────────────────────────────────────────────
_user_id_raw = os.getenv("TELEGRAM_USER_ID", "")
ALLOWED_USER_ID = int(_user_id_raw) if _user_id_raw.isdigit() else 0


async def seguridad_middleware(update: Update) -> bool:
    if not update.effective_user:
        return False
    user_id = update.effective_user.id
    if user_id != ALLOWED_USER_ID:
        logger.warning(f"🚨 INTRUSO: {user_id} ({update.effective_user.username})")
        await update.message.reply_text("⛔ ACCESO DENEGADO.")
        return False
    return True


# ─── HELPER: ENVIAR RESPUESTA CON TTS OPCIONAL ───────────────────────────────

async def _enviar_respuesta(update: Update, texto: str):
    """
    Envía la respuesta de texto al usuario.
    Si TTS está activo, también genera y envía el audio de voz.
    Si hay adjunto pendiente (gráfico), lo envía como foto.
    """
    # 1. Enviar texto principal
    await update.message.reply_text(texto, parse_mode="Markdown")

    # 2. Enviar adjunto (gráfico/imagen) si hay uno pendiente
    if jarvis_core._pending_attachment:
        path = jarvis_core._pending_attachment
        jarvis_core._pending_attachment = None
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    await update.message.reply_photo(photo=f, caption="📊 Aquí está tu gráfico")
            except Exception as e:
                logger.error(f"Error enviando adjunto: {e}")
            finally:
                try:
                    os.remove(path)
                except Exception:
                    pass

    # 3. TTS: Generar y enviar audio si está activado
    if conversation_state_manager.tts_activo:
        try:
            from src.TOOLS.tool_tts import texto_a_audio
            audio_path = await __import__('asyncio').to_thread(texto_a_audio, texto)
            if audio_path and os.path.exists(audio_path):
                with open(audio_path, "rb") as f:
                    await update.message.reply_voice(voice=f)
                os.remove(audio_path)
        except Exception as e:
            logger.error(f"Error generando TTS: {e}")


# ─── COMANDOS ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    await update.message.reply_text(
        "🟢 *JARVIS V2 EN LÍNEA*\n"
        "Núcleo: Activo ✅ | Memoria: Cargada ✅\n\n"
        "Usa /ayuda para ver todos los comandos disponibles.",
        parse_mode="Markdown"
    )


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    texto = (
        "🤖 *COMANDOS DISPONIBLES*\n\n"
        "━━━━━━ *VOZ Y MODOS* ━━━━━━\n"
        "🔊 /tts — Activar/desactivar respuestas en voz\n"
        "🎙️ /escucha — Modo escucha profunda (empatía)\n"
        "🧠 /foco [min] — Modo trabajo profundo (ej: /foco 90)\n"
        "🔕 /silencio [min] — Modo silencioso (sin notif.)\n"
        "🌿 /terapeuta — Sesión de reflexión guiada\n"
        "✅ /normal — Volver al modo normal\n\n"
        "━━━━━━ *DATOS Y PROGRESO* ━━━━━━\n"
        "📊 /progreso — Gráfico de energía (últimos 7 días)\n"
        "📅 /mes — Resumen visual del mes actual\n"
        "🌡️ /clima — Clima actual y sugerencia\n\n"
        "━━━━━━ *SISTEMA* ━━━━━━\n"
        "ℹ️ /estado — Estado de modo y TTS actual\n"
        "🚀 /start — Reiniciar sesión\n\n"
        "_También puedes enviar fotos 📷 para que JARVIS las analice con Vision AI._"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")


async def cmd_tts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    nuevo_estado = conversation_state_manager.toggle_tts()
    emoji = "🔊" if nuevo_estado else "🔇"
    estado_txt = "activado" if nuevo_estado else "desactivado"
    await update.message.reply_text(
        f"{emoji} *Modo voz {estado_txt}.*\n"
        f"{'JARVIS responderá con texto Y audio a partir de ahora.' if nuevo_estado else 'Solo respuestas de texto.'}",
        parse_mode="Markdown"
    )


async def cmd_escucha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    tema = " ".join(context.args) if context.args else None
    conversation_state_manager.activar_modo("escucha_profunda", tema=tema)
    await update.message.reply_text(
        f"🎙️ *Modo Escucha Profunda activado.*\n"
        f"{'Tema: ' + tema if tema else 'Estoy completamente presente para escucharte.'}\n\n"
        f"Habla sin filtros. Tendrás toda mi atención durante los próximos 5 intercambios.",
        parse_mode="Markdown"
    )


async def cmd_foco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    try:
        minutos = int(context.args[0]) if context.args else 90
    except (ValueError, IndexError):
        minutos = 90

    conversation_state_manager.activar_modo("trabajo_profundo", duracion_minutos=minutos)
    await update.message.reply_text(
        f"🧠 *Modo Trabajo Profundo: {minutos} minutos*\n\n"
        f"🔕 No enviaré notificaciones ni interrupciones.\n"
        f"⏰ Te avisaré cuando termine el tiempo.\n"
        f"💡 Te preguntaré qué lograste al final.\n\n"
        f"_¡A concentrarse! 💪_",
        parse_mode="Markdown"
    )


async def cmd_silencio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    try:
        minutos = int(context.args[0]) if context.args else None
    except (ValueError, IndexError):
        minutos = None

    conversation_state_manager.activar_modo("silencioso", duracion_minutos=minutos)
    duracion_txt = f" por {minutos} minutos" if minutos else ""
    await update.message.reply_text(
        f"🔕 *Modo Silencioso activado{duracion_txt}.*\n"
        f"No enviaré mensajes proactivos. Puedes seguir escribiéndome si necesitas algo.",
        parse_mode="Markdown"
    )


async def cmd_terapeuta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    conversation_state_manager.activar_modo("terapeuta")
    primera_pregunta = conversation_state_manager.siguiente_pregunta_terapeuta()

    intro = (
        "🌿 *Sesión de Reflexión Guiada*\n\n"
        "Vamos a hacer un ejercicio de 5 preguntas para conectar contigo mismo/a. "
        "No hay respuestas correctas o incorrectas. Solo reflexión honesta.\n"
        "Tómate el tiempo que necesites con cada pregunta.\n\n"
    )
    await update.message.reply_text(
        intro + primera_pregunta,
        parse_mode="Markdown"
    )


async def cmd_normal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    modo_anterior = conversation_state_manager.desactivar_modo()
    await update.message.reply_text(
        f"✅ *Modo {modo_anterior.value} desactivado.*\n"
        f"Regresando al modo normal. ¿En qué te puedo ayudar?",
        parse_mode="Markdown"
    )


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    estado_conv = conversation_state_manager.get_estado_str()
    tts_estado = "🔊 Activo" if conversation_state_manager.tts_activo else "🔇 Inactivo"
    await update.message.reply_text(
        f"📋 *Estado actual de JARVIS*\n\n"
        f"🎭 Conversación: `{estado_conv}`\n"
        f"🔊 Voz (TTS): {tts_estado}",
        parse_mode="Markdown"
    )


async def cmd_progreso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    await update.message.reply_text("📊 Generando tu gráfico de energía...", parse_mode="Markdown")
    try:
        from src.TOOLS.tool_graphs import generar_grafico_energia
        import asyncio
        path = await asyncio.to_thread(generar_grafico_energia, 7)
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption="⚡ Tu nivel de energía — últimos 7 días\n🟢 Alta (7-10) 🟡 Media (4-6) 🔴 Baja (1-3)"
                )
            os.remove(path)
        else:
            await update.message.reply_text(
                "📭 No hay suficientes datos de energía aún (mínimo 2 días registrados).\n"
                "Cuéntame cómo te sientes cada día para construir tu historial."
            )
    except Exception as e:
        logger.error(f"Error en /progreso: {e}")
        await update.message.reply_text("⚠️ Error generando el gráfico. Inténtalo de nuevo.")


async def cmd_mes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    await update.message.reply_text("📅 Generando resumen mensual...", parse_mode="Markdown")
    try:
        from src.TOOLS.tool_graphs import generar_resumen_mensual
        import asyncio
        path = await asyncio.to_thread(generar_resumen_mensual)
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                await update.message.reply_photo(
                    photo=f,
                    caption="📈 Resumen visual del mes — generado por JARVIS"
                )
            os.remove(path)
        else:
            await update.message.reply_text(
                "📭 No hay datos del mes actual para generar el resumen."
            )
    except Exception as e:
        logger.error(f"Error en /mes: {e}")
        await update.message.reply_text("⚠️ Error generando el resumen. Inténtalo de nuevo.")


async def cmd_clima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update):
        return
    ciudad = " ".join(context.args) if context.args else None
    await update.message.reply_text("🌡️ Consultando el clima...", parse_mode="Markdown")
    try:
        from src.TOOLS.tool_weather import obtener_clima_actual, formatear_clima_mensaje, generar_sugerencia_clima
        import asyncio
        clima = await asyncio.to_thread(obtener_clima_actual, ciudad)
        mensaje = formatear_clima_mensaje(clima)
        sugerencia = generar_sugerencia_clima(clima) if "error" not in clima else None
        if sugerencia:
            mensaje += f"\n\n💡 *Sugerencia:* {sugerencia}"
        await update.message.reply_text(mensaje, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error en /clima: {e}")
        await update.message.reply_text("⚠️ Error consultando el clima.")


# ─── MANEJADOR DE MENSAJES DE TEXTO Y VOZ ────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador principal: texto y notas de voz."""
    if not await seguridad_middleware(update):
        return

    if not update.message or (
        not update.message.text
        and not update.message.voice
        and not update.message.audio
    ):
        return

    texto_usuario = update.message.text
    if texto_usuario and len(texto_usuario) > 2048:
        await update.message.reply_text("Tu mensaje es demasiado largo. Intenta ser más breve.")
        return

    texto_limpio = Sanitizador.limpiar_texto(texto_usuario) if texto_usuario else ""
    if texto_limpio and not Sanitizador.validar_seguridad(texto_limpio):
        logger.warning(f"Inyección bloqueada por usuario {ALLOWED_USER_ID}")
        await update.message.reply_text("⛔ Input rechazado por seguridad.")
        return

    audio_path = None

    if update.message.voice or update.message.audio:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="record_voice")
        try:
            archivo = await (update.message.voice or update.message.audio).get_file()
            os.makedirs("LOGS/temp", exist_ok=True)
            audio_path = os.path.join("LOGS/temp", f"audio_{update.message.message_id}.ogg")
            await archivo.download_to_drive(audio_path)
        except Exception as e:
            logger.error(f"Error descargando audio: {e}")
            await update.message.reply_text("No pude procesar el audio.")
            return
    else:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        respuesta = await jarvis_core.procesar_mensaje(
            str(ALLOWED_USER_ID), texto_limpio, audio_path
        )
        await _enviar_respuesta(update, respuesta)

    except Exception as e:
        logger.error(f"Error en handle_message: {e}")
        await update.message.reply_text("⚠️ Error de comunicación.")
    finally:
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except Exception:
                pass


# ─── MANEJADOR DE FOTOS (GEMINI VISION) ──────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Manejador de imágenes enviadas por el usuario.
    Descarga la foto y la pasa a Gemini Vision para análisis.
    """
    if not await seguridad_middleware(update):
        return

    if not update.message or not update.message.photo:
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    image_path = None
    try:
        # Tomar la versión de mayor resolución
        foto = update.message.photo[-1]
        archivo = await foto.get_file()
        os.makedirs("LOGS/temp", exist_ok=True)
        image_path = os.path.join("LOGS/temp", f"img_{update.message.message_id}.jpg")
        await archivo.download_to_drive(image_path)
        logger.info(f"Imagen descargada: {image_path}")

        # Obtener caption si hay alguno
        caption = update.message.caption or ""
        texto_contexto = f"[Imagen enviada por el usuario] {caption}".strip()

        # Procesar con Gemini Vision
        respuesta = await jarvis_core.procesar_mensaje(
            str(ALLOWED_USER_ID),
            texto_contexto,
            audio_path=None,
            image_path=image_path
        )
        await _enviar_respuesta(update, respuesta)

    except Exception as e:
        logger.error(f"Error procesando imagen: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ No pude procesar la imagen. Asegúrate de que es una foto válida."
        )
    finally:
        if image_path and os.path.exists(image_path):
            try:
                os.remove(image_path)
            except Exception:
                pass


# ─── MANEJADOR DE DOCUMENTOS (PDFs, archivos de texto) ───────────────────────

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador básico de documentos: imágenes enviadas como archivos."""
    if not await seguridad_middleware(update):
        return

    doc = update.message.document
    if not doc:
        return

    # Solo procesar imágenes enviadas como documento
    if doc.mime_type and doc.mime_type.startswith("image/"):
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        image_path = None
        try:
            archivo = await doc.get_file()
            os.makedirs("LOGS/temp", exist_ok=True)
            ext = doc.file_name.split(".")[-1] if doc.file_name else "jpg"
            image_path = os.path.join("LOGS/temp", f"doc_{update.message.message_id}.{ext}")
            await archivo.download_to_drive(image_path)

            caption = update.message.caption or ""
            texto_contexto = f"[Imagen enviada como documento] {caption}".strip()

            respuesta = await jarvis_core.procesar_mensaje(
                str(ALLOWED_USER_ID),
                texto_contexto,
                audio_path=None,
                image_path=image_path
            )
            await _enviar_respuesta(update, respuesta)
        except Exception as e:
            logger.error(f"Error procesando documento imagen: {e}")
            await update.message.reply_text("⚠️ No pude procesar el archivo.")
        finally:
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                except Exception:
                    pass
    else:
        await update.message.reply_text(
            "📎 Recibí un documento, pero por ahora solo proceso imágenes. "
            "¿Puedes decirme qué contiene y en qué te puedo ayudar?"
        )


# ─── PUNTO DE ENTRADA ─────────────────────────────────────────────────────────

def iniciar_bot():
    """Entry Point de la interfaz de Telegram."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.critical("No se encontró TELEGRAM_TOKEN en .env")
        return

    application = ApplicationBuilder().token(token).build()

    # ── Comandos ─────────────────────────────────────────────
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ayuda", cmd_ayuda))
    application.add_handler(CommandHandler("help", cmd_ayuda))
    application.add_handler(CommandHandler("tts", cmd_tts))
    application.add_handler(CommandHandler("escucha", cmd_escucha))
    application.add_handler(CommandHandler("foco", cmd_foco))
    application.add_handler(CommandHandler("silencio", cmd_silencio))
    application.add_handler(CommandHandler("terapeuta", cmd_terapeuta))
    application.add_handler(CommandHandler("normal", cmd_normal))
    application.add_handler(CommandHandler("estado", cmd_estado))
    application.add_handler(CommandHandler("progreso", cmd_progreso))
    application.add_handler(CommandHandler("mes", cmd_mes))
    application.add_handler(CommandHandler("clima", cmd_clima))

    # ── Mensajes ─────────────────────────────────────────────
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.VOICE | filters.AUDIO) & ~filters.COMMAND,
            handle_message
        )
    )
    # Fotos enviadas directamente
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    # Documentos (imágenes enviadas como archivo)
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("🤖 JARVIS V2 Telegram Interface lista (V2 — Vision + TTS + Modos)")

    async def _post_init(app):
        from src.core.cron import iniciar_cron
        iniciar_cron()

    application.post_init = _post_init

    try:
        application.run_polling()
    finally:
        from src.core.cron import detener_cron
        detener_cron()
