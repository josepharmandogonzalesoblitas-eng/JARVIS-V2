import os
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)
from dotenv import load_dotenv

from src.core.orquestador import Orquestador, MENU_HERRAMIENTAS_MARKER
from src.core.repositories import JSONDataRepository, ChromaVectorRepository, DefaultToolsRepository
from src.core.conversation_state import conversation_state_manager
from src.utils.sanitizador import Sanitizador
from src.core.cron import cron_manager, iniciar_cron, detener_cron

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
        if update.message:
            await update.message.reply_text("⛔ ACCESO DENEGADO.")
        return False
    return True


# ─── MENÚ INTERACTIVO DE HERRAMIENTAS ────────────────────────────────────────

MENU_TECLADO = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📅 Agendar en Calendar", callback_data="tool:google_calendar"),
        InlineKeyboardButton("✅ Crear Tarea (Tasks)", callback_data="tool:google_tasks"),
    ],
    [
        InlineKeyboardButton("⏰ Poner Recordatorio", callback_data="tool:agendar_recordatorio"),
        InlineKeyboardButton("⏱️ Timer / Alarma Rápida", callback_data="tool:alarma_rapida"),
    ],
    [
        InlineKeyboardButton("🌐 Buscar en Web", callback_data="tool:buscar_web"),
        InlineKeyboardButton("🌤️ Clima Actual", callback_data="tool:clima_actual"),
    ],
    [
        InlineKeyboardButton("📊 Gráfico de Energía", callback_data="tool:generar_grafico_energia"),
        InlineKeyboardButton("🗂️ Gestionar Proyecto", callback_data="tool:gestionar_memoria"),
    ],
    [
        InlineKeyboardButton("📈 Resumen Mensual", callback_data="tool:generar_resumen_mensual"),
        InlineKeyboardButton("❌ Cancelar (Solo charla)", callback_data="tool:cancelar"),
    ],
])

_NOMBRES_HERRAMIENTAS = {
    "google_calendar": "📅 Google Calendar",
    "google_tasks": "✅ Google Tasks",
    "agendar_recordatorio": "⏰ Recordatorio",
    "alarma_rapida": "⏱️ Timer/Alarma",
    "buscar_web": "🌐 Búsqueda Web",
    "clima_actual": "🌤️ Clima Actual",
    "pronostico_clima": "🌦️ Pronóstico Clima",
    "generar_grafico_energia": "📊 Gráfico de Energía",
    "generar_resumen_mensual": "📈 Resumen Mensual",
    "generar_progreso_proyecto": "📉 Progreso de Proyecto",
    "gestionar_memoria": "🗂️ Gestionar Proyectos",
}


async def _mostrar_menu_herramientas(update: Update, context: ContextTypes.DEFAULT_TYPE, texto_ia: str):
    await update.message.reply_text(
        f"{texto_ia}\\n\\n"
        f"🤔 *No estoy seguro de qué herramienta necesitas.*\\n"
        f"Selecciona la acción correcta para continuar:",
        reply_markup=MENU_TECLADO,
        parse_mode="Markdown"
    )


async def handle_tool_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data or not query.data.startswith("tool:"):
        return

    tool_name = query.data[len("tool:"):]

    if tool_name == "cancelar":
        await query.edit_message_text("✅ Entendido, continuamos en modo conversación normal.")
        return

    mensaje_original = context.user_data.get("last_user_message", "")
    nombre_amigable = _NOMBRES_HERRAMIENTAS.get(tool_name, tool_name)

    await query.edit_message_text(
        f"🔧 Usando *{nombre_amigable}*...\\n"
        f'_Procesando: \\"{mensaje_original}\\"_',
        parse_mode="Markdown"
    )

    mensaje_forzado = f"[TOOL:{tool_name}] {mensaje_original}"
    try:
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action="typing")
        respuesta = await jarvis_core.procesar_mensaje(str(ALLOWED_USER_ID), mensaje_forzado)

        if respuesta.startswith(MENU_HERRAMIENTAS_MARKER):
            respuesta = respuesta[len(MENU_HERRAMIENTAS_MARKER):]

        if jarvis_core._pending_attachment:
            path = jarvis_core._pending_attachment
            jarvis_core._pending_attachment = None
            if os.path.exists(path):
                try:
                    with open(path, "rb") as f:
                        await context.bot.send_photo(
                            chat_id=query.message.chat_id, photo=f, caption=f"📊 {respuesta[:900]}"
                        )
                    os.remove(path)
                    return
                except Exception as e:
                    logger.error(f"Error enviando gráfico desde callback: {e}")

        await context.bot.send_message(chat_id=query.message.chat_id, text=respuesta, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error en callback de herramienta: {e}", exc_info=True)
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"⚠️ Error ejecutando {nombre_amigable}: {str(e)}")

async def _enviar_respuesta(update: Update, texto: str, context: ContextTypes.DEFAULT_TYPE = None):
    if texto.startswith(MENU_HERRAMIENTAS_MARKER):
        texto_ia = texto[len(MENU_HERRAMIENTAS_MARKER):]
        if context is not None:
            await _mostrar_menu_herramientas(update, context, texto_ia)
        else:
            await update.message.reply_text(texto_ia)
        return

    try:
        await update.message.reply_text(texto, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(texto)

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
                if os.path.exists(path): os.remove(path)

    if conversation_state_manager.tts_activo:
        try:
            from src.TOOLS.tool_tts import texto_a_audio
            audio_path = await asyncio.to_thread(texto_a_audio, texto)
            if audio_path and os.path.exists(audio_path):
                with open(audio_path, "rb") as f:
                    await update.message.reply_voice(voice=f)
                os.remove(audio_path)
        except Exception as e:
            logger.error(f"Error generando TTS: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    await update.message.reply_text(
        "🟢 *JARVIS V2 EN LÍNEA*\\nNúcleo: Activo ✅ | Memoria: Cargada ✅\\n\\nUsa /ayuda para ver todos los comandos disponibles.",
        parse_mode="Markdown"
    )

async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    texto = (
        "🤖 *COMANDOS DISPONIBLES*\\n\\n"
        "━━━━━━ *VOZ Y MODOS* ━━━━━━\\n"
        "🔊 /tts — Activar/desactivar respuestas en voz\\n"
        "🎙️ /escucha — Modo escucha profunda (empatía)\\n"
        "🧠 /foco [min] — Modo trabajo profundo (ej: /foco 90)\\n"
        "🔕 /silencio [min] — Modo silencioso (sin notif.)\\n"
        "🌿 /terapeuta — Sesión de reflexión guiada\\n"
        "✅ /normal — Volver al modo normal\\n\\n"
        "━━━━━━ *DATOS Y PROGRESO* ━━━━━━\\n"
        "📊 /progreso — Gráfico de energía (últimos 7 días)\\n"
        "📅 /mes — Resumen visual del mes actual\\n"
        "🌡️ /clima — Clima actual y sugerencia\\n\\n"
        "━━━━━━ *SISTEMA* ━━━━━━\\n"
        "ℹ️ /estado — Estado de modo y TTS actual\\n"
        "🧪 /test_cron — Disparar tareas del CRON manualmente (debug)\\n"
        "🚀 /start — Reiniciar sesión\\n\\n"
        "_También puedes enviar fotos 📷 para que JARVIS las analice con Vision AI._"
    )
    await update.message.reply_text(texto, parse_mode="Markdown")

async def cmd_tts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    nuevo_estado = conversation_state_manager.toggle_tts()
    emoji = "🔊" if nuevo_estado else "🔇"
    estado_txt = "activado" if nuevo_estado else "desactivado"
    await update.message.reply_text(
        f"{emoji} *Modo voz {estado_txt}.*\\n"
        f"{'JARVIS responderá con texto Y audio a partir de ahora.' if nuevo_estado else 'Solo respuestas de texto.'}",
        parse_mode="Markdown"
    )

async def cmd_escucha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    tema = " ".join(context.args) if context.args else None
    conversation_state_manager.activar_modo("escucha_profunda", tema=tema)
    await update.message.reply_text(
        f"🎙️ *Modo Escucha Profunda activado.*\\n"
        f"{'Tema: ' + tema if tema else 'Estoy completamente presente para escucharte.'}\\n\\n"
        f"Habla sin filtros. Tendrás toda mi atención durante los próximos 5 intercambios.",
        parse_mode="Markdown"
    )

async def cmd_foco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    minutos = int(context.args[0]) if context.args and context.args[0].isdigit() else 90
    conversation_state_manager.activar_modo("trabajo_profundo", duracion_minutos=minutos)
    await update.message.reply_text(
        f"🧠 *Modo Trabajo Profundo: {minutos} minutos*\\n\\n"
        f"🔕 No enviaré notificaciones ni interrupciones.\\n"
        f"⏰ Te avisaré cuando termine el tiempo.\\n"
        f"💡 Te preguntaré qué lograste al final.\\n\\n"
        f"_¡A concentrarse! 💪_",
        parse_mode="Markdown"
    )

async def cmd_silencio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    minutos = int(context.args[0]) if context.args and context.args[0].isdigit() else None
    conversation_state_manager.activar_modo("silencioso", duracion_minutos=minutos)
    duracion_txt = f" por {minutos} minutos" if minutos else ""
    await update.message.reply_text(
        f"🔕 *Modo Silencioso activado{duracion_txt}.*\\n"
        f"No enviaré mensajes proactivos. Puedes seguir escribiéndome si necesitas algo.",
        parse_mode="Markdown"
    )

async def cmd_terapeuta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    conversation_state_manager.activar_modo("terapeuta")
    primera_pregunta = conversation_state_manager.siguiente_pregunta_terapeuta()
    intro = (
        "🌿 *Sesión de Reflexión Guiada*\\n\\n"
        "Vamos a hacer un ejercicio de 5 preguntas para conectar contigo mismo/a. "
        "No hay respuestas correctas o incorrectas. Solo reflexión honesta.\\n"
        "Tómate el tiempo que necesites con cada pregunta.\\n\\n"
    )
    await update.message.reply_text(intro + primera_pregunta, parse_mode="Markdown")

async def cmd_normal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    modo_anterior = conversation_state_manager.desactivar_modo()
    await update.message.reply_text(
        f"✅ *Modo {modo_anterior.value} desactivado.*\\n"
        f"Regresando al modo normal. ¿En qué te puedo ayudar?",
        parse_mode="Markdown"
    )

async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    estado_conv = conversation_state_manager.get_estado_str()
    tts_estado = "🔊 Activo" if conversation_state_manager.tts_activo else "🔇 Inactivo"
    await update.message.reply_text(
        f"📋 *Estado actual de JARVIS*\\n\\n"
        f"🎭 Conversación: `{estado_conv}`\\n"
        f"🔊 Voz (TTS): {tts_estado}",
        parse_mode="Markdown"
    )
async def cmd_test_cron(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    tarea = context.args[0] if context.args else "matutino"
    await update.message.reply_text(f"🧪 Ejecutando tarea CRON: `{tarea}`*", parse_mode="Markdown")
    try:
        from src.core.cron import cron_manager
        tareas_disponibles = {
            "matutino": cron_manager._checkin_matutino,
            "mediodia": cron_manager._checkin_mediodia,
            "nocturno": cron_manager._checkin_nocturno,
            "resumen": cron_manager._resumen_diario,
            "metas": cron_manager._trigger_metas_olvidadas,
            "followups": cron_manager._check_followups,
            "patron": cron_manager._check_patron_emocional,
            "terapeuta": cron_manager._sesion_terapeuta_semanal,
            "sugerencia": cron_manager._sugerencia_semanal,
            "validacion": cron_manager._validacion_rutinas,
            "backup": cron_manager._ejecutar_backup_diario,
        }

        if tarea not in tareas_disponibles:
            lista = "\\n".join([f"• `{k}`" for k in tareas_disponibles.keys()])
            await update.message.reply_text(
                f"❓ Tarea `{tarea}` no reconocida.\\n\\n*Tareas disponibles:*\\n{lista}",
                parse_mode="Markdown"
            )
            return

        asyncio.create_task(tareas_disponibles[tarea]())
        await update.message.reply_text(
            f"✅ Tarea `{tarea}` lanzada. El mensaje llegará en unos segundos si el CRON está activo.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error en /test_cron: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Error: {str(e)}")


async def cmd_progreso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    await update.message.reply_text("📊 Generando tu gráfico de energía...", parse_mode="Markdown")
    # Resto de la implementación...

async def cmd_mes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    await update.message.reply_text("📅 Generando resumen mensual...", parse_mode="Markdown")
    # Resto de la implementación...

async def cmd_clima(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    await update.message.reply_text("🌡️ Consultando el clima...", parse_mode="Markdown")
    # Resto de la implementación...

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    # Resto de la implementación...

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    # Resto de la implementación...

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await seguridad_middleware(update): return
    # Resto de la implementación...


def iniciar_bot():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        logger.critical("No se encontró TELEGRAM_TOKEN")
        return

    application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ayuda", cmd_ayuda))
    application.add_handler(CommandHandler("tts", cmd_tts))
    application.add_handler(CommandHandler("escucha", cmd_escucha))
    application.add_handler(CommandHandler("foco", cmd_foco))
    application.add_handler(CommandHandler("silencio", cmd_silencio))
    application.add_handler(CommandHandler("terapeuta", cmd_terapeuta))
    application.add_handler(CommandHandler("normal", cmd_normal))
    application.add_handler(CommandHandler("estado", cmd_estado))
    application.add_handler(CommandHandler("test_cron", cmd_test_cron))
    application.add_handler(CommandHandler("progreso", cmd_progreso))
    application.add_handler(CommandHandler("mes", cmd_mes))
    application.add_handler(CommandHandler("clima", cmd_clima))
    
    application.add_handler(CallbackQueryHandler(handle_tool_callback, pattern="^tool:"))
    
    application.add_handler(MessageHandler((filters.TEXT | filters.VOICE | filters.AUDIO) & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("🤖 JARVIS V2 Telegram Interface lista")

    async def _post_init(app):
        cron_manager.set_orquestador(jarvis_core)
        iniciar_cron()

    application.post_init = _post_init

    try:
        application.run_polling()
    finally:
        detener_cron()


