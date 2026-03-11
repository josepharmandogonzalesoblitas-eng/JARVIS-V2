import os
import logging
import asyncio
from datetime import datetime
from telegram import Bot
from dataclasses import dataclass
from typing import Callable, Optional, List, Any

# Removido para evitar importación circular. La instancia del orquestador se inyectará.
# from src.core.orquestador import Orquestador 
from src.utils.backup import crear_backup

logger = logging.getLogger("cron")

@dataclass
class ScheduledTask:
    id: str
    action: Callable[[], Any]
    time: Optional[str] = None
    weekday: Optional[int] = None

class CronManager:
    def __init__(self):
        self.running = False
        self.bot = None
        self.chat_id = os.getenv("TELEGRAM_USER_ID")
        self.orquestador: Optional[Any] = None # Se inyectará externamente
        self._task = None
        self._task_registry: List[ScheduledTask] = []
        self._dynamic_tasks: List[ScheduledTask] = []
        self._alarmas_dinamicas = []

        self._eventos_ejecutados_hoy = set()
        self._fecha_ultima_ejecucion = datetime.now().date()

        token = os.getenv("TELEGRAM_TOKEN")
        if token:
            self.bot = Bot(token=token)

        self._register_static_tasks()

    def set_orquestador(self, orquestador: Any):
        self.orquestador = orquestador
        logger.info("Instancia de Orquestador inyectada en CronManager.")

    async def _enviar_mensaje_telegram(self, texto: str):
        if not self.bot or not self.chat_id:
            logger.error("No se puede enviar push: faltan credenciales.")
            return
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=texto, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error enviando mensaje push: {e}")

    async def _enviar_foto_telegram(self, path: str, caption: str = ""):
        if not self.bot or not self.chat_id or not os.path.exists(path):
            return
        try:
            with open(path, "rb") as f:
                await self.bot.send_photo(chat_id=self.chat_id, photo=f, caption=caption)
        except Exception as e:
            logger.error(f"Error enviando foto push: {e}")

    def _es_modo_silencioso(self) -> bool:
        try:
            from src.core.conversation_state import conversation_state_manager
            return conversation_state_manager.es_silencioso()
        except Exception:
            return False

    async def _es_momento_sensible(self) -> bool:
        if not self.orquestador: return False
        try:
            from src.core.emotion_engine import emotion_engine
            from src.data import db_handler, schemas
            
            nivel, _ = await emotion_engine.detectar_patron_negativo_historico(self.orquestador._historial_reciente)
            if nivel >= 1: return True
                
            bitacora = await db_handler.async_read_data("bitacora.json", schemas.GestorBitacora)
            if bitacora.dia_actual:
                if bitacora.dia_actual.nivel_energia is not None and bitacora.dia_actual.nivel_energia <= 3: return True
                if bitacora.dia_actual.estado_animo:
                    if any(p in bitacora.dia_actual.estado_animo.lower() for p in ["triste", "mal", "deprim", "agotad", "solo", "ansios"]): return True
            
            estado_emocional = await db_handler.async_read_data("estado_emocional.json", schemas.EstadoEmocionalSistema)
            if estado_emocional.dias_negativos_consecutivos >= 2: return True
                
            return False
        except Exception as e:
            logger.warning(f"Error verificando momento sensible: {e}")
            return False

    async def _run_async_prompt(self, prompt: str):
        if not self.orquestador:
            logger.error("CRON: Orquestador no inyectado.")
            return
        if self._es_modo_silencioso():
            logger.info("CRON: Modo silencioso activo, omitiendo.")
            return
        try:
            respuesta = await self.orquestador.procesar_mensaje("SISTEMA_CRON", prompt)
            await self._enviar_mensaje_telegram(respuesta)
            if self.orquestador._pending_attachment:
                path = self.orquestador._pending_attachment
                self.orquestador._pending_attachment = None
                await self._enviar_foto_telegram(path, "📊 Gráfico generado por JARVIS")
        except Exception as e:
            logger.error(f"Error en ejecución CRON: {e}", exc_info=True)

    async def _checkin_matutino(self):
        logger.info("CRON: Check-in Matutino")
        # El resto de las implementaciones de las tareas...
        await self._run_async_prompt("Prompt para el checkin matutino")

    async def _checkin_mediodia(self):
        logger.info("CRON: Check-in Mediodía")
        await self._run_async_prompt("Prompt para el checkin de mediodía")

    async def _checkin_nocturno(self):
        logger.info("CRON: Check-in Nocturno")
        await self._run_async_prompt("Prompt para el checkin nocturno")

    async def _resumen_diario(self):
        logger.info("CRON: Resumen Diario")
        await self._run_async_prompt("Prompt para el resumen diario")

    async def _ejecutar_backup_diario(self):
        logger.info("CRON: Backup diario de memoria.")
        await asyncio.to_thread(crear_backup)

    async def _seguimiento_metas_semanal(self):
        await self._run_async_prompt("Prompt para seguimiento de metas")
    
    async def _validacion_rutinas(self):
        await self._run_async_prompt("Prompt para validación de rutinas")

    async def _analisis_patron_energia(self):
        await self._run_async_prompt("Prompt para análisis de patrón de energía")

    async def _sesion_terapeuta_semanal(self):
        await self._run_async_prompt("Prompt para sesión de terapeuta")

    async def _check_followups(self):
        await self._run_async_prompt("Prompt para check de followups")

    async def _trigger_metas_olvidadas(self):
        await self._run_async_prompt("Prompt para trigger de metas olvidadas")

    async def _check_patron_emocional(self):
        await self._run_async_prompt("Prompt para check de patrón emocional")

    async def _sugerencia_semanal(self):
        await self._run_async_prompt("Prompt para sugerencia semanal")

    def agendar_alarma_dinamica(self, hora_hhmm: str, mensaje: str):
        try:
            self._alarmas_dinamicas.append((hora_hhmm, mensaje))
            return f"✅ Alarma configurada para las {hora_hhmm}."
        except Exception as e:
            return f"❌ No se pudo agendar: {str(e)}"

    def _register_static_tasks(self):
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

    async def _verificar_y_ejecutar_tareas(self):
        ahora = datetime.now()
        hora_actual = ahora.strftime("%H:%M")
        fecha_actual = ahora.date()
        dia_semana_actual = ahora.weekday()

        if fecha_actual > self._fecha_ultima_ejecucion:
            self._eventos_ejecutados_hoy.clear()
            self._dynamic_tasks.clear()
            self._fecha_ultima_ejecucion = fecha_actual

        all_tasks = self._task_registry + self._dynamic_tasks
        for task in all_tasks:
            if task.id in self._eventos_ejecutados_hoy:
                continue

            time_match = task.time == hora_actual
            weekday_match = task.weekday is None or task.weekday == dia_semana_actual

            if time_match and weekday_match:
                self._eventos_ejecutados_hoy.add(task.id)
                asyncio.create_task(task.action())
        
        await self._procesar_alarmas_dinamicas_legado(hora_actual)

    async def _procesar_alarmas_dinamicas_legado(self, hora_actual: str):
        # This is kept for retro-compatibility
        pass

    async def _run_loop(self):
        while self.running:
            await self._verificar_y_ejecutar_tareas()
            await asyncio.sleep(60 - datetime.now().second)

    def start(self):
        if not self.running:
            self.running = True
            try:
                loop = asyncio.get_running_loop()
                self._task = loop.create_task(self._run_loop())
                logger.info("✅ CRON V3 (Adaptativo) iniciado.")
            except RuntimeError:
                logger.error("No se pudo iniciar el CRON: no hay Event Loop activo.")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            logger.info("CRON detenido.")

cron_manager = CronManager()

def iniciar_cron():
    cron_manager.start()

def detener_cron():
    cron_manager.stop()
