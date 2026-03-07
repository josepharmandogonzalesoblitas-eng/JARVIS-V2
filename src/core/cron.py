import os
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Bot
from src.core.orquestador import Orquestador
from src.core.repositories import JSONDataRepository, ChromaVectorRepository, DefaultToolsRepository
from src.utils.backup import crear_backup

logger = logging.getLogger("cron")


class CronManager:
    """
    Gestor de tareas programadas (Scheduler) — V2.

    Nuevas capacidades:
    - Check matutino con clima (si OPENWEATHER_API_KEY está configurado)
    - Follow-up de conversaciones profundas
    - Triggers inteligentes de metas olvidadas
    - Sugerencias no solicitadas semanales (búsqueda web)
    - Sesión terapeuta semanal (domingo 20:00)
    - Alerta proactiva de patrones negativos
    - Respeta modo Silencioso y Trabajo Profundo

    Idempotente: cada tarea se ejecuta máximo una vez por día/semana.
    """

    def __init__(self):
        self.running = False
        self.bot = None
        self.chat_id = os.getenv("TELEGRAM_USER_ID")
        self.orquestador = Orquestador(
            data_repo=JSONDataRepository(),
            vector_repo=ChromaVectorRepository(),
            tools_repo=DefaultToolsRepository()
        )
        self._task = None
        self._alarmas_dinamicas = []

        # Idempotencia: registro de eventos ejecutados hoy
        self._eventos_ejecutados_hoy = set()
        self._fecha_ultima_ejecucion = datetime.now().date()

        token = os.getenv("TELEGRAM_TOKEN")
        if token:
            self.bot = Bot(token=token)

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    async def _enviar_mensaje_telegram(self, texto: str):
        """Envía un mensaje push al usuario."""
        if not self.bot or not self.chat_id:
            logger.error("No se puede enviar push: faltan credenciales.")
            return
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=texto, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error enviando mensaje push: {e}")

    async def _enviar_foto_telegram(self, path: str, caption: str = ""):
        """Envía una imagen al usuario."""
        if not self.bot or not self.chat_id or not os.path.exists(path):
            return
        try:
            with open(path, "rb") as f:
                await self.bot.send_photo(chat_id=self.chat_id, photo=f, caption=caption)
        except Exception as e:
            logger.error(f"Error enviando foto push: {e}")

    def _es_modo_silencioso(self) -> bool:
        """Verifica si JARVIS está en modo que inhibe mensajes proactivos."""
        try:
            from src.core.conversation_state import conversation_state_manager
            return conversation_state_manager.es_silencioso()
        except Exception:
            return False

    async def _run_async_prompt(self, prompt: str):
        """Ejecuta el pipeline de IA y envía la respuesta por Telegram."""
        if self._es_modo_silencioso():
            logger.info("CRON: Modo silencioso activo, omitiendo mensaje proactivo.")
            return
        try:
            respuesta = await self.orquestador.procesar_mensaje("SISTEMA_CRON", prompt, audio_path=None)
            await self._enviar_mensaje_telegram(respuesta)

            # Enviar adjunto si hay gráfico generado
            if self.orquestador._pending_attachment:
                path = self.orquestador._pending_attachment
                self.orquestador._pending_attachment = None
                await self._enviar_foto_telegram(path, "📊 Gráfico generado por JARVIS")
        except Exception as e:
            logger.error(f"Error en ejecución CRON: {e}", exc_info=True)

    # ─── TAREAS FIJAS DIARIAS ─────────────────────────────────────────────────

    async def _checkin_matutino(self):
        """Check-in de las 08:00. Incluye clima si está configurado."""
        logger.info("CRON: Check-in Matutino")

        # Obtener clima si está disponible
        clima_str = ""
        try:
            openweather_key = os.getenv("OPENWEATHER_API_KEY")
            if openweather_key:
                from src.TOOLS.tool_weather import obtener_clima_actual, generar_sugerencia_clima, formatear_clima_mensaje
                clima = obtener_clima_actual()
                if "error" not in clima:
                    clima_str = f"\nClima actual: {formatear_clima_mensaje(clima)}"
                    sugerencia = generar_sugerencia_clima(clima)
                    if sugerencia:
                        clima_str += f"\nSugerencia climática: {sugerencia}"
        except Exception as e:
            logger.warning(f"No se pudo obtener clima para el matutino: {e}")

        prompt = (
            f"[SISTEMA - CHECK-IN MATUTINO] Buenos días. Revisa el contexto completo:\n"
            f"1. Saluda al usuario por su nombre.\n"
            f"2. Si tiene RUTINAS registradas, recuérdale las de esta mañana.\n"
            f"3. Si tiene RECORDATORIOS pendientes, menciona los 2 más relevantes.\n"
            f"4. Pregúntale cómo se siente para arrancar el día.\n"
            f"{clima_str}\n"
            f"Sé breve, cálido y energético. Máximo 4 frases."
        )
        await self._run_async_prompt(prompt)

    async def _checkin_mediodia(self):
        logger.info("CRON: Check-in Mediodía")
        prompt = (
            "[SISTEMA - CHECK-IN MEDIODÍA] Es mediodía. Revisa el contexto:\n"
            "1. Pregunta cómo va el día y si avanzó en sus tareas de la mañana.\n"
            "2. Si tiene recordatorios para la tarde, recuérdaselos.\n"
            "3. Si su energía de hoy es baja (≤4), sugiere tareas simples.\n"
            "Sé breve y proactivo."
        )
        await self._run_async_prompt(prompt)

    async def _checkin_nocturno(self):
        logger.info("CRON: Check-in Nocturno")
        prompt = (
            "[SISTEMA - CHECK-IN NOCTURNO] Es tarde. Ayuda al usuario a cerrar el día:\n"
            "1. Pregúntale cómo le fue y qué logró hoy.\n"
            "2. Si tiene tareas pendientes sin completar, menciónalas brevemente.\n"
            "3. Una pregunta breve de reflexión sobre su bienestar.\n"
            "4. Cierre motivador o tranquilizador.\n"
            "Sé cálido y breve."
        )
        await self._run_async_prompt(prompt)

    async def _resumen_diario(self):
        logger.info("CRON: Resumen Diario")
        prompt = (
            "[SISTEMA - RESUMEN DIARIO] Son las 10pm. Cierre del día:\n"
            "1. Lista tareas/recordatorios pendientes de hoy.\n"
            "2. Indica cuántas están sin completar.\n"
            "3. Evalúa el nivel de energía registrado hoy.\n"
            "4. Frase motivadora corta + pregunta si quiere reprogramar algo para mañana.\n"
            "Formato: resumen ejecutivo personal. Claro y conciso."
        )
        await self._run_async_prompt(prompt)

    async def _ejecutar_backup_diario(self):
        logger.info("CRON: Backup diario de memoria.")
        await asyncio.to_thread(crear_backup)

    # ─── TAREAS SEMANALES ─────────────────────────────────────────────────────

    async def _seguimiento_metas_semanal(self):
        """Domingo 10:00 — Revisión de metas a largo plazo."""
        logger.info("CRON: Seguimiento Semanal de Metas")
        prompt = (
            "[SISTEMA - SEGUIMIENTO SEMANAL DE METAS] Es domingo. Momento de reflexionar:\n"
            "1. Revisa las metas a largo plazo del usuario.\n"
            "2. Para cada meta activa, pregunta si avanzó esta semana.\n"
            "3. Si tiene proyectos activos, pregunta por el estado de sus tareas.\n"
            "4. Anímalo a definir UNA acción concreta para la próxima semana.\n"
            "Sé motivador y estratégico. Máximo 5 frases."
        )
        await self._run_async_prompt(prompt)

    async def _validacion_rutinas(self):
        """Domingo 18:00 — Verificar si las rutinas siguen vigentes."""
        logger.info("CRON: Validación de Rutinas")
        prompt = (
            "[SISTEMA - VALIDACIÓN DE RUTINAS] Revisa las rutinas del usuario:\n"
            "1. Menciona 1-2 rutinas guardadas.\n"
            "2. Pregunta de forma amigable si las sigue haciendo.\n"
            "3. Si cambió alguna, actualiza el registro.\n"
            "Casual, sin presionar. Solo verificación amistosa."
        )
        await self._run_async_prompt(prompt)

    async def _analisis_patron_energia(self):
        """Lunes 08:30 — Análisis de patrones de energía de la semana pasada."""
        logger.info("CRON: Análisis de Patrones de Energía")
        prompt = (
            "[SISTEMA - ANÁLISIS DE PATRONES] Es lunes. Analiza el historial:\n"
            "1. Revisa la bitácora de los últimos días.\n"
            "2. Detecta si hay patrones (ej: energía baja los lunes).\n"
            "3. Si hay patrón, compártelo constructivamente.\n"
            "4. Sugiere UN ajuste concreto en rutinas.\n"
            "Si hay menos de 3 días de datos, pide que registre más.\n"
            "Analítico pero cercano."
        )
        await self._run_async_prompt(prompt)

    async def _sesion_terapeuta_semanal(self):
        """Domingo 20:00 — Sesión de reflexión guiada semanal."""
        logger.info("CRON: Sesión Terapeuta Semanal")
        if self._es_modo_silencioso():
            return
        try:
            from src.core.conversation_state import conversation_state_manager
            # Activar modo terapeuta
            conversation_state_manager.activar_modo("terapeuta")
            primera_pregunta = conversation_state_manager.siguiente_pregunta_terapeuta()

            intro = (
                "🌿 *Momento de reflexión semanal*\n\n"
                "Es domingo por la noche. Es el mejor momento para mirar hacia adentro "
                "y cerrar la semana con intención. Tengo 5 preguntas para ti. "
                "Tómate el tiempo que necesites con cada una.\n\n"
            )
            await self._enviar_mensaje_telegram(intro + primera_pregunta)
        except Exception as e:
            logger.error(f"Error iniciando sesión terapeuta: {e}")

    # ─── TRIGGERS INTELIGENTES ─────────────────────────────────────────────────

    async def _check_followups(self):
        """Cada día a las 09:00 — Verificar follow-ups de conversaciones profundas."""
        logger.info("CRON: Verificando follow-ups pendientes")
        try:
            from src.core.emotion_engine import emotion_engine
            mensaje = await emotion_engine.verificar_followups_pendientes()
            if mensaje:
                await self._enviar_mensaje_telegram(mensaje)
        except Exception as e:
            logger.warning(f"Error verificando follow-ups: {e}")

    async def _trigger_metas_olvidadas(self):
        """Martes y Jueves 10:00 — Detectar metas que llevan días sin mencionarse."""
        logger.info("CRON: Verificando triggers de metas")
        if self._es_modo_silencioso():
            return
        try:
            from src.core.emotion_engine import emotion_engine
            mensaje = await emotion_engine.verificar_triggers_metas(
                self.orquestador._historial_reciente
            )
            if mensaje:
                await self._enviar_mensaje_telegram(mensaje)
        except Exception as e:
            logger.warning(f"Error en trigger de metas: {e}")

    async def _check_patron_emocional(self):
        """Cada día a las 11:00 — Detectar si hay patrón de días negativos acumulados."""
        logger.info("CRON: Verificando patrón emocional")
        if self._es_modo_silencioso():
            return
        try:
            from src.core.emotion_engine import emotion_engine
            nivel, dias_negativos = await emotion_engine.detectar_patron_negativo_historico(
                self.orquestador._historial_reciente
            )
            if nivel == 1 and dias_negativos >= 3:
                try:
                    from src.data import db_handler, schemas
                    persona = await db_handler.async_read_data("persona.json", schemas.Persona)
                    nombre = persona.nombre
                except Exception:
                    nombre = "amigo"
                mensaje = emotion_engine.generar_respuesta_crisis(1, nombre)
                if mensaje:
                    await self._enviar_mensaje_telegram(mensaje)
        except Exception as e:
            logger.warning(f"Error verificando patrón emocional: {e}")

    async def _sugerencia_semanal(self):
        """Miércoles 10:00 — Sugerencia no solicitada basada en profesión/intereses."""
        logger.info("CRON: Generando sugerencia semanal")
        if self._es_modo_silencioso():
            return
        try:
            from src.data import db_handler, schemas
            from src.TOOLS.tool_system import ejecutar_herramienta_sistema
            from src.data.db_handler import async_read_data

            persona = await async_read_data("persona.json", schemas.Persona)

            # Construir query basado en profesión y preferencias
            profesion = persona.profesion or "tecnología"
            hobbies = list(persona.preferencias.values())[:2]
            query_terms = [profesion] + hobbies
            query = f"novedades tendencias {' '.join(query_terms[:2])} 2026"

            # Verificar que no enviamos la misma sugerencia antes
            estado = await async_read_data("estado_emocional.json", schemas.EstadoEmocionalSistema)
            if query in estado.sugerencias_enviadas:
                logger.info("CRON: Sugerencia ya enviada, omitiendo.")
                return

            # Buscar en la web
            resultado = await asyncio.to_thread(
                ejecutar_herramienta_sistema,
                "buscar_web",
                {"query": query}
            )

            if resultado and "Error" not in resultado and "No encontré" not in resultado:
                # Guardar registro de sugerencia enviada
                estado.sugerencias_enviadas.append(query)
                if len(estado.sugerencias_enviadas) > 20:
                    estado.sugerencias_enviadas = estado.sugerencias_enviadas[-20:]
                await db_handler.async_save_data("estado_emocional.json", estado)

                # Formatear y enviar
                prompt = (
                    f"[SISTEMA - SUGERENCIA SEMANAL] Encontré algo que podría interesarte:\n"
                    f"{resultado}\n\n"
                    f"Basado en esto, genera un mensaje breve (2-3 frases) para el usuario "
                    f"que sea genuinamente interesante para alguien que trabaja en '{profesion}'. "
                    f"Pregunta si quiere más información. No seas genérico."
                )
                await self._run_async_prompt(prompt)

        except Exception as e:
            logger.warning(f"Error en sugerencia semanal: {e}")

    # ─── ALARMAS DINÁMICAS ────────────────────────────────────────────────────

    def agendar_alarma_dinamica(self, hora_hhmm: str, mensaje: str):
        """Agenda un mensaje push para una hora específica del día."""
        try:
            logger.info(f"CRON: Alarma dinámica → {hora_hhmm}: {mensaje}")
            self._alarmas_dinamicas.append((hora_hhmm, mensaje))
            return f"✅ Alarma configurada para las {hora_hhmm}."
        except Exception as e:
            logger.error(f"Error agendando alarma: {e}")
            return f"❌ No se pudo agendar: {str(e)}"

    # ─── LOOP PRINCIPAL ───────────────────────────────────────────────────────

    async def _verificar_y_ejecutar_tareas(self):
        """Evalúa qué tareas deben ejecutarse según la hora y día actuales."""
        ahora = datetime.now()
        hora_actual = ahora.strftime("%H:%M")
        fecha_actual = ahora.date()
        dia_semana = ahora.weekday()  # 0=Lunes … 6=Domingo

        # Reset diario de idempotencia
        if fecha_actual > self._fecha_ultima_ejecucion:
            self._eventos_ejecutados_hoy.clear()
            self._alarmas_dinamicas.clear()
            self._fecha_ultima_ejecucion = fecha_actual

        # ── TAREAS DIARIAS ──────────────────────────────────────────────────
        programacion_diaria = {
            "08:00": ("matutino", self._checkin_matutino),
            "09:00": ("followups", self._check_followups),
            "11:00": ("patron_emocional", self._check_patron_emocional),
            "14:00": ("mediodia", self._checkin_mediodia),
            "20:30": ("nocturno", self._checkin_nocturno),
            "22:00": ("resumen_diario", self._resumen_diario),
            "03:00": ("backup", self._ejecutar_backup_diario),
        }

        for hora, (evento_id, tarea) in programacion_diaria.items():
            if hora_actual == hora and evento_id not in self._eventos_ejecutados_hoy:
                self._eventos_ejecutados_hoy.add(evento_id)
                asyncio.create_task(tarea())

        # ── TAREAS SEMANALES ────────────────────────────────────────────────
        # Domingo (6)
        if dia_semana == 6:
            if hora_actual == "10:00" and "metas_semanal" not in self._eventos_ejecutados_hoy:
                self._eventos_ejecutados_hoy.add("metas_semanal")
                asyncio.create_task(self._seguimiento_metas_semanal())

            elif hora_actual == "18:00" and "validacion_rutinas" not in self._eventos_ejecutados_hoy:
                self._eventos_ejecutados_hoy.add("validacion_rutinas")
                asyncio.create_task(self._validacion_rutinas())

            elif hora_actual == "20:00" and "terapeuta_semanal" not in self._eventos_ejecutados_hoy:
                self._eventos_ejecutados_hoy.add("terapeuta_semanal")
                asyncio.create_task(self._sesion_terapeuta_semanal())

        # Lunes (0)
        elif dia_semana == 0:
            if hora_actual == "08:30" and "analisis_patron" not in self._eventos_ejecutados_hoy:
                self._eventos_ejecutados_hoy.add("analisis_patron")
                asyncio.create_task(self._analisis_patron_energia())

        # Martes (1) y Jueves (3) — Triggers de metas
        elif dia_semana in [1, 3]:
            if hora_actual == "10:00" and "trigger_metas" not in self._eventos_ejecutados_hoy:
                self._eventos_ejecutados_hoy.add("trigger_metas")
                asyncio.create_task(self._trigger_metas_olvidadas())

        # Miércoles (2) — Sugerencia semanal
        elif dia_semana == 2:
            if hora_actual == "10:00" and "sugerencia_semanal" not in self._eventos_ejecutados_hoy:
                self._eventos_ejecutados_hoy.add("sugerencia_semanal")
                asyncio.create_task(self._sugerencia_semanal())

        # ── ALARMAS DINÁMICAS ───────────────────────────────────────────────
        alarmas_a_remover = []
        for alarma in self._alarmas_dinamicas:
            hora_alarma, mensaje = alarma
            if hora_actual == hora_alarma:
                logger.info(f"CRON: ¡Alarma disparada! → {mensaje}")
                asyncio.create_task(
                    self._enviar_mensaje_telegram(f"🔔 *RECORDATORIO:*\n{mensaje}")
                )
                alarmas_a_remover.append(alarma)

        for alarma in alarmas_a_remover:
            if alarma in self._alarmas_dinamicas:
                self._alarmas_dinamicas.remove(alarma)

    async def _run_loop(self):
        while self.running:
            await self._verificar_y_ejecutar_tareas()
            # Dormir hasta el inicio del próximo minuto exacto
            ahora = datetime.now()
            segundos_restantes = 60 - ahora.second
            await asyncio.sleep(segundos_restantes)

    def start(self):
        """Inicia el scheduler asíncrono."""
        if not self.running:
            self.running = True
            try:
                loop = asyncio.get_running_loop()
                self._task = loop.create_task(self._run_loop())
                logger.info("✅ CRON V2 iniciado (con triggers inteligentes y terapeuta semanal).")
            except RuntimeError:
                logger.error("No se pudo iniciar el CRON: no hay Event Loop activo.")

    def stop(self):
        """Detiene el scheduler."""
        self.running = False
        if self._task:
            self._task.cancel()
            logger.info("CRON detenido.")


# ─── SINGLETON GLOBAL ─────────────────────────────────────────────────────────
cron_manager = CronManager()


def iniciar_cron():
    cron_manager.start()


def detener_cron():
    cron_manager.stop()
