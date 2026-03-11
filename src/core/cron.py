import os
import logging
import asyncio
from datetime import datetime
from telegram import Bot
from dataclasses import dataclass, field
from typing import Callable, Optional, List, Any

from src.core.orquestador import Orquestador
from src.core.repositories import JSONDataRepository, ChromaVectorRepository, DefaultToolsRepository
from src.utils.backup import crear_backup

logger = logging.getLogger("cron")

@dataclass
class ScheduledTask:
    """Representa una tarea programada con sus condiciones de ejecución."""
    id: str
    action: Callable[[], Any]
    time: Optional[str] = None  # HH:MM para tareas diarias
    weekday: Optional[int] = None  # 0=Lunes...6=Domingo para tareas semanales

class CronManager:
    """
    Gestor de tareas programadas (Scheduler) — V3 (Adaptativo y Determinístico).

    Nuevas capacidades:
    - Motor de Reglas en Python para una planificación clara y sin alucinaciones.
    - Estructura modular de tareas (Estáticas, Dinámicas, Críticas).
    - Preparado para recibir "sugerencias de agendamiento" desde el Orquestador.
    - Mantiene la idempotencia y el respeto por los modos de silencio.
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
        self._task_registry: List[ScheduledTask] = []
        self._dynamic_tasks: List[ScheduledTask] = [] # Tareas generadas en tiempo de ejecución
        self._alarmas_dinamicas = [] # Legado

        # Idempotencia: registro de eventos ejecutados hoy
        self._eventos_ejecutados_hoy = set()
        self._fecha_ultima_ejecucion = datetime.now().date()

        token = os.getenv("TELEGRAM_TOKEN")
        if token:
            self.bot = Bot(token=token)

        self._register_static_tasks()

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

    async def _es_momento_sensible(self) -> bool:
        """Verifica si el usuario está en un momento emocionalmente vulnerable (energía baja o crisis)."""
        try:
            from src.core.emotion_engine import emotion_engine
            from src.data import db_handler, schemas
            
            nivel, _ = await emotion_engine.detectar_patron_negativo_historico(self.orquestador._historial_reciente)
            if nivel >= 1:
                return True
                
            bitacora = await db_handler.async_read_data("bitacora.json", schemas.GestorBitacora)
            if bitacora.dia_actual:
                if bitacora.dia_actual.nivel_energia is not None and bitacora.dia_actual.nivel_energia <= 3:
                    return True
                if bitacora.dia_actual.estado_animo:
                    animo_lower = bitacora.dia_actual.estado_animo.lower()
                    if any(p in animo_lower for p in ["triste", "mal", "deprim", "agotad", "solo", "ansios"]):
                        return True
            
            estado_emocional = await db_handler.async_read_data("estado_emocional.json", schemas.EstadoEmocionalSistema)
            if estado_emocional.dias_negativos_consecutivos >= 2:
                return True
                
            return False
        except Exception as e:
            logger.warning(f"Error verificando momento sensible: {e}")
            return False

    async def _run_async_prompt(self, prompt: str):
        """Ejecuta el pipeline de IA y envía la respuesta por Telegram."""
        if self._es_modo_silencioso():
            logger.info("CRON: Modo silencioso activo, omitiendo mensaje proactivo.")
            return
        try:
            respuesta = await self.orquestador.procesar_mensaje("SISTEMA_CRON", prompt, audio_path=None)
            await self._enviar_mensaje_telegram(respuesta)

            if self.orquestador._pending_attachment:
                path = self.orquestador._pending_attachment
                self.orquestador._pending_attachment = None
                await self._enviar_foto_telegram(path, "📊 Gráfico generado por JARVIS")
        except Exception as e:
            logger.error(f"Error en ejecución CRON: {e}", exc_info=True)

    # ─── TAREAS FIJAS DIARIAS ─────────────────────────────────────────────────

    async def _checkin_matutino(self):
        logger.info("CRON: Check-in Matutino")
        clima_str = ""
        try:
            if os.getenv("OPENWEATHER_API_KEY"):
                from src.TOOLS.tool_weather import obtener_clima_actual, generar_sugerencia_clima, formatear_clima_mensaje
                clima = obtener_clima_actual()
                if "error" not in clima:
                    clima_str = f"\\nClima actual: {formatear_clima_mensaje(clima)}"
                    sugerencia = generar_sugerencia_clima(clima)
                    if sugerencia:
                        clima_str += f"\\nSugerencia climática: {sugerencia}"
        except Exception as e:
            logger.warning(f"No se pudo obtener clima para el matutino: {e}")

        prompt = (
            f"[SISTEMA - CHECK-IN MATUTINO] Buenos días. Revisa el contexto completo:\\n"
            f"1. Saluda al usuario por su nombre con mucha suavidad.\\n"
            f"2. NO menciones rutinas productivas ni recordatorios de trabajo.\\n"
            f"3. Pregúntale cómo se siente y si descansó bien, dándole espacio para expresarse.\\n"
            f"{clima_str}\\n"
            f"Sé muy empático, sin presión por ser productivo hoy."
        ) if await self._es_momento_sensible() else (
            f"[SISTEMA - CHECK-IN MATUTINO] Buenos días. Revisa el contexto completo:\\n"
            f"1. Saluda al usuario por su nombre.\\n"
            f"2. Si tiene RUTINAS registradas, recuérdale las de esta mañana.\\n"
            f"3. Si tiene RECORDATORIOS pendientes, menciona los 2 más relevantes.\\n"
            f"4. Pregúntale cómo se siente para arrancar el día.\\n"
            f"{clima_str}\\n"
            f"Sé breve, cálido y energético. Máximo 4 frases."
        )
        await self._run_async_prompt(prompt)

    async def _checkin_mediodia(self):
        logger.info("CRON: Check-in Mediodía")
        prompt = (
            "[SISTEMA - CHECK-IN MEDIODÍA] Es mediodía. Revisa el contexto:\\n"
            "1. Pregunta suavemente cómo se siente ahora mismo.\\n"
            "2. NO le preguntes por tareas pendientes ni avances de proyectos.\\n"
            "3. Sugiere que tome una pausa o coma algo rico.\\n"
            "Sé breve, un amigo que se preocupa sin exigir productividad."
        ) if await self._es_momento_sensible() else (
            "[SISTEMA - CHECK-IN MEDIODÍA] Es mediodía. Revisa el contexto:\\n"
            "1. Pregunta cómo va el día y si avanzó en sus tareas de la mañana.\\n"
            "2. Si tiene recordatorios para la tarde, recuérdaselos.\\n"
            "3. Si su energía de hoy es baja (≤4), sugiere tareas simples.\\n"
            "Sé breve y proactivo."
        )
        await self._run_async_prompt(prompt)

    async def _checkin_nocturno(self):
        logger.info("CRON: Check-in Nocturno")
        prompt = (
            "[SISTEMA - CHECK-IN NOCTURNO] Es tarde. Ayuda al usuario a cerrar el día:\\n"
            "1. Valida que el día ha sido difícil y que está bien descansar.\\n"
            "2. NO menciones tareas pendientes ni metas no cumplidas.\\n"
            "3. Aconséjale relajarse y descansar bien para mañana.\\n"
            "Sé sumamente empático, cálido y reconfortante."
        ) if await self._es_momento_sensible() else (
            "[SISTEMA - CHECK-IN NOCTURNO] Es tarde. Ayuda al usuario a cerrar el día:\\n"
            "1. Pregúntale cómo le fue y qué logró hoy.\\n"
            "2. Si tiene tareas pendientes sin completar, menciónalas brevemente.\\n"
            "3. Una pregunta breve de reflexión sobre su bienestar.\\n"
            "4. Cierre motivador o tranquilizador.\\n"
            "Sé cálido y breve."
        )
        await self._run_async_prompt(prompt)

    async def _resumen_diario(self):
        logger.info("CRON: Resumen Diario")
        prompt = (
            "[SISTEMA - RESUMEN DIARIO] Son las 10pm. Cierre del día:\\n"
            "1. Reconoce que hoy no fue el mejor día energéticamente o anímicamente.\\n"
            "2. Ignora por completo las tareas o pendientes que no se hicieron.\\n"
            "3. Dale permiso explícito para desconectar y descansar sin culpa.\\n"
            "Formato: Amigo reconfortante y comprensivo. Sin presiones."
        ) if await self._es_momento_sensible() else (
            "[SISTEMA - RESUMEN DIARIO] Son las 10pm. Cierre del día:\\n"
            "1. Lista tareas/recordatorios pendientes de hoy.\\n"
            "2. Indica cuántas están sin completar.\\n"
            "3. Evalúa el nivel de energía registrado hoy.\\n"
            "4. Frase motivadora corta + pregunta si quiere reprogramar algo para mañana.\\n"
            "Formato: resumen ejecutivo personal. Claro y conciso."
        )
        await self._run_async_prompt(prompt)

    async def _ejecutar_backup_diario(self):
        logger.info("CRON: Backup diario de memoria.")
        await asyncio.to_thread(crear_backup)

    # ─── TAREAS SEMANALES ─────────────────────────────────────────────────────

    async def _seguimiento_metas_semanal(self):
        logger.info("CRON: Seguimiento Semanal de Metas")
        prompt = (
            "[SISTEMA - SEGUIMIENTO SEMANAL DE METAS] Es domingo. Momento de reflexionar:\\n"
            "1. Reconoce que la semana puede haber sido pesada.\\n"
            "2. NO le preguntes por metas ni proyectos.\\n"
            "3. Pregúntale qué actividad le daría paz o descanso hoy.\\n"
            "Sé un apoyo emocional, sin exigir rendimiento."
        ) if await self._es_momento_sensible() else (
            "[SISTEMA - SEGUIMIENTO SEMANAL DE METAS] Es domingo. Momento de reflexionar:\\n"
            "1. Revisa las metas a largo plazo del usuario.\\n"
            "2. Para cada meta activa, pregunta si avanzó esta semana.\\n"
            "3. Si tiene proyectos activos, pregunta por el estado de sus tareas.\\n"
            "4. Anímalo a definir UNA acción concreta para la próxima semana.\\n"
            "Sé motivador y estratégico. Máximo 5 frases."
        )
        await self._run_async_prompt(prompt)

    async def _validacion_rutinas(self):
        logger.info("CRON: Validación de Rutinas")
        prompt = (
            "[SISTEMA - VALIDACIÓN DE RUTINAS] Revisa las rutinas del usuario:\\n"
            "1. Menciona 1-2 rutinas guardadas.\\n"
            "2. Pregunta de forma amigable si las sigue haciendo.\\n"
            "3. Si cambió alguna, actualiza el registro.\\n"
            "Casual, sin presionar. Solo verificación amistosa."
        )
        await self._run_async_prompt(prompt)

    async def _analisis_patron_energia(self):
        logger.info("CRON: Análisis de Patrones de Energía")
        prompt = (
            "[SISTEMA - ANÁLISIS DE PATRONES] Es lunes. Analiza el historial:\\n"
            "1. Revisa la bitácora de los últimos días.\\n"
            "2. Detecta si hay patrones (ej: energía baja los lunes).\\n"
            "3. Si hay patrón, compártelo constructivamente.\\n"
            "4. Sugiere UN ajuste concreto en rutinas.\\n"
            "Si hay menos de 3 días de datos, pide que registre más.\\n"
            "Analítico pero cercano."
        )
        await self._run_async_prompt(prompt)

    async def _sesion_terapeuta_semanal(self):
        logger.info("CRON: Sesión Terapeuta Semanal")
        if self._es_modo_silencioso():
            return
        try:
            from src.core.conversation_state import conversation_state_manager
            conversation_state_manager.activar_modo("terapeuta")
            primera_pregunta = conversation_state_manager.siguiente_pregunta_terapeuta()
            intro = (
                "🌿 *Momento de reflexión semanal*\\n\\n"
                "Es domingo por la noche. Es el mejor momento para mirar hacia adentro "
                "y cerrar la semana con intención. Tengo 5 preguntas para ti. "
                "Tómate el tiempo que necesites con cada una.\\n\\n"
            )
            await self._enviar_mensaje_telegram(intro + primera_pregunta)
        except Exception as e:
            logger.error(f"Error iniciando sesión terapeuta: {e}")

    # ─── TRIGGERS INTELIGENTES ─────────────────────────────────────────────────

    async def _check_followups(self):
        logger.info("CRON: Verificando follow-ups pendientes")
        try:
            from src.core.emotion_engine import emotion_engine
            mensaje = await emotion_engine.verificar_followups_pendientes()
            if mensaje:
                await self._enviar_mensaje_telegram(mensaje)
        except Exception as e:
            logger.warning(f"Error verificando follow-ups: {e}")

    async def _trigger_metas_olvidadas(self):
        logger.info("CRON: Verificando triggers de metas")
        if self._es_modo_silencioso():
            return
        try:
            from src.core.emotion_engine import emotion_engine
            mensaje = await emotion_engine.verificar_triggers_metas(self.orquestador._historial_reciente)
            if mensaje:
                await self._enviar_mensaje_telegram(mensaje)
        except Exception as e:
            logger.warning(f"Error en trigger de metas: {e}")

    async def _check_patron_emocional(self):
        logger.info("CRON: Verificando patrón emocional")
        if self._es_modo_silencioso():
            return
        try:
            from src.core.emotion_engine import emotion_engine
            nivel, dias_negativos = await emotion_engine.detectar_patron_negativo_historico(self.orquestador._historial_reciente)
            if nivel == 1 and dias_negativos >= 3:
                from src.data import db_handler, schemas
                persona = await db_handler.async_read_data("persona.json", schemas.Persona)
                nombre = persona.nombre if persona else "amigo"
                mensaje = emotion_engine.generar_respuesta_crisis(1, nombre)
                if mensaje:
                    await self._enviar_mensaje_telegram(mensaje)
        except Exception as e:
            logger.warning(f"Error verificando patrón emocional: {e}")

    async def _sugerencia_semanal(self):
        logger.info("CRON: Generando sugerencia semanal")
        if self._es_modo_silencioso():
            return
        try:
            from src.data import db_handler, schemas
            from src.TOOLS.tool_system import ejecutar_herramienta_sistema
            
            persona = await db_handler.async_read_data("persona.json", schemas.Persona)
            profesion = persona.profesion or "tecnología"
            hobbies = list(persona.preferencias.values())[:2]
            query = f"novedades tendencias {profesion} {' '.join(hobbies)} 2026"

            estado = await db_handler.async_read_data("estado_emocional.json", schemas.EstadoEmocionalSistema)
            if query in estado.sugerencias_enviadas:
                logger.info("CRON: Sugerencia ya enviada, omitiendo.")
                return

            resultado = await asyncio.to_thread(ejecutar_herramienta_sistema, "buscar_web", {"query": query})

            if resultado and "Error" not in resultado and "No encontré" not in resultado:
                estado.sugerencias_enviadas.append(query)
                estado.sugerencias_enviadas = estado.sugerencias_enviadas[-20:]
                await db_handler.async_save_data("estado_emocional.json", estado)
                prompt = (
                    f"[SISTEMA - SUGERENCIA SEMANAL] Encontré algo que podría interesarte:\\n"
                    f"{resultado}\\n\\n"
                    f"Basado en esto, genera un mensaje breve (2-3 frases) para el usuario "
                    f"que sea genuinamente interesante para alguien que trabaja en '{profesion}'. "
                    f"Pregunta si quiere más información. No seas genérico."
                )
                await self._run_async_prompt(prompt)
        except Exception as e:
            logger.warning(f"Error en sugerencia semanal: {e}")

    # ─── ALARMAS (LEGADO) Y TAREAS DINÁMICAS ──────────────────────────────────

    def agendar_alarma_dinamica(self, hora_hhmm: str, mensaje: str):
        """(Legado) Agenda un mensaje push para una hora específica del día."""
        try:
            logger.info(f"CRON: Alarma dinámica (legado) → {hora_hhmm}: {mensaje}")
            self._alarmas_dinamicas.append((hora_hhmm, mensaje))
            return f"✅ Alarma configurada para las {hora_hhmm}."
        except Exception as e:
            logger.error(f"Error agendando alarma: {e}")
            return f"❌ No se pudo agendar: {str(e)}"

    # ─── REGISTRO Y LOOP PRINCIPAL ───────────────────────────────────────────

    def _register_static_tasks(self):
        """Registra todas las tareas estáticas del sistema."""
        static_tasks = [
            ScheduledTask(id="matutino", action=self._checkin_matutino, time="08:00"),
            ScheduledTask(id="followups", action=self._check_followups, time="09:00"),
            ScheduledTask(id="patron_emocional", action=self._check_patron_emocional, time="11:00"),
            ScheduledTask(id="mediodia", action=self._checkin_mediodia, time="14:00"),
            ScheduledTask(id="nocturno", action=self._checkin_nocturno, time="20:30"),
            ScheduledTask(id="resumen_diario", action=self._resumen_diario, time="22:00"),
            ScheduledTask(id="backup", action=self._ejecutar_backup_diario, time="03:00"),
            ScheduledTask(id="metas_semanal", action=self._seguimiento_metas_semanal, time="10:00", weekday=6),
            ScheduledTask(id="validacion_rutinas", action=self._validacion_rutinas, time="18:00", weekday=6),
            ScheduledTask(id="terapeuta_semanal", action=self._sesion_terapeuta_semanal, time="20:00", weekday=6),
            ScheduledTask(id="analisis_patron", action=self._analisis_patron_energia, time="08:30", weekday=0),
            ScheduledTask(id="trigger_metas_tue", action=self._trigger_metas_olvidadas, time="10:00", weekday=1),
            ScheduledTask(id="trigger_metas_thu", action=self._trigger_metas_olvidadas, time="10:00", weekday=3),
            ScheduledTask(id="sugerencia_semanal", action=self._sugerencia_semanal, time="10:00", weekday=2),
        ]
        self._task_registry.extend(static_tasks)
        logger.info(f"Registradas {len(static_tasks)} tareas estáticas.")

    async def _verificar_y_ejecutar_tareas(self):
        """Motor de reglas que evalúa y ejecuta las tareas programadas."""
        ahora = datetime.now()
        hora_actual = ahora.strftime("%H:%M")
        fecha_actual = ahora.date()
        dia_semana_actual = ahora.weekday()

        if fecha_actual > self._fecha_ultima_ejecucion:
            self._eventos_ejecutados_hoy.clear()
            self._dynamic_tasks.clear()
            self._fecha_ultima_ejecucion = fecha_actual
            logger.info("CRON: Reseteo de eventos diarios de idempotencia.")

        todas_las_tareas = self._task_registry + self._dynamic_tasks
        for task in todas_las_tareas:
            if task.id in self._eventos_ejecutados_hoy:
                continue

            condicion_tiempo = task.time == hora_actual
            condicion_dia_semana = task.weekday is None or task.weekday == dia_semana_actual

            if condicion_tiempo and condicion_dia_semana:
                logger.info(f"CRON: Disparando tarea '{task.id}'.")
                self._eventos_ejecutados_hoy.add(task.id)
                asyncio.create_task(task.action())
        
        await self._procesar_alarmas_dinamicas_legado(hora_actual)

    async def _procesar_alarmas_dinamicas_legado(self, hora_actual: str):
        alarmas_a_remover = []
        for hora_alarma, mensaje in self._alarmas_dinamicas:
            if hora_actual == hora_alarma:
                evento_id = f"alarma_legado_{hora_alarma}_{mensaje[:10]}"
                if evento_id not in self._eventos_ejecutados_hoy:
                    logger.info(f"CRON: ¡Alarma (legado) disparada! → {mensaje}")
                    self._eventos_ejecutados_hoy.add(evento_id)
                    asyncio.create_task(
                        self._enviar_mensaje_telegram(f"🔔 *RECORDATORIO:*\\n{mensaje}")
                    )
                    alarmas_a_remover.append((hora_alarma, mensaje))
        
        for alarma in alarmas_a_remover:
            if alarma in self._alarmas_dinamicas:
                self._alarmas_dinamicas.remove(alarma)

    async def _run_loop(self):
        while self.running:
            await self._verificar_y_ejecutar_tareas()
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
                logger.info("✅ CRON V3 (Adaptativo) iniciado.")
            except RuntimeError:
                logger.error("No se pudo iniciar el CRON: no hay Event Loop activo.")

    def stop(self):
        """Detiene el scheduler."""
        self.running = False
        if self._task:
            self._task.cancel()
            logger.info("CRON detenido.")

cron_manager = CronManager()

def iniciar_cron():
    cron_manager.start()

def detener_cron():
    cron_manager.stop()
