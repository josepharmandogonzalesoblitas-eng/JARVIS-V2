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
    Gestor de tareas programadas (Scheduler).
    Completamente Asíncrono. No utiliza Threads para evitar Race Conditions
    con la base de datos y la instancia del bot de Telegram.
    Aplica Idempotencia usando estados internos.
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
        self._alarmas_dinamicas = [] # Lista de tuplas (hora_hhmm, mensaje)
        
        # IDEMPOTENCIA: Registro de eventos del día para evitar repeticiones
        self._eventos_ejecutados_hoy = set()
        self._fecha_ultima_ejecucion = datetime.now().date()

        token = os.getenv("TELEGRAM_TOKEN")
        if token:
            self.bot = Bot(token=token)

    async def _enviar_mensaje_telegram(self, texto: str):
        """Función helper para enviar mensajes push."""
        if not self.bot or not self.chat_id:
            logger.error("No se puede enviar mensaje push: Faltan credenciales de Telegram.")
            return
            
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=texto)
        except Exception as e:
            logger.error(f"Error enviando mensaje push (Async): {e}")

    async def _run_async_prompt(self, prompt: str):
        """Ejecuta el pipeline asíncrono de forma nativa sin romper el Event Loop."""
        try:
            respuesta = await self.orquestador.procesar_mensaje("SISTEMA_CRON", prompt, audio_path=None)
            await self._enviar_mensaje_telegram(respuesta)
        except Exception as e:
            logger.error(f"Error en ejecución asíncrona del CRON: {e}", exc_info=True)

    async def _checkin_matutino(self):
        logger.info("CRON: Generando Check-in Matutino")
        prompt = "[SISTEMA] Es por la mañana. Saluda al usuario de forma natural, recuérdale sutilmente si tiene tareas o proyectos pendientes importantes para hoy, y pregúntale cómo se siente para empezar el día. Sé breve."
        await self._run_async_prompt(prompt)

    async def _checkin_mediodia(self):
        logger.info("CRON: Generando Check-in Mediodía")
        prompt = "[SISTEMA] Es mediodía. Pregúntale al usuario cómo va su día. Si detectas que tiene recordatorios pendientes o lugares a los que ir, recuérdaselo de forma amigable por si quiere aprovechar la tarde."
        await self._run_async_prompt(prompt)

    async def _checkin_nocturno(self):
        logger.info("CRON: Generando Check-in Nocturno")
        prompt = "[SISTEMA] Es de noche. Ayuda al usuario a cerrar el día. Pregúntale qué tal le fue, dale un consejo de descanso, y pregúntale si logró avanzar en sus metas para actualizar la bitácora."
        await self._run_async_prompt(prompt)

    async def _ejecutar_backup_diario(self):
        logger.info("CRON: Ejecutando backup diario de memoria.")
        # Se asume que crear_backup es síncrono, lo enviamos a un threadpool
        await asyncio.to_thread(crear_backup)

    def agendar_alarma_dinamica(self, hora_hhmm: str, mensaje: str):
        """
        Programa un mensaje de Telegram para una hora específica del día actual.
        """
        try:
            logger.info(f"CRON: Agendando alarma dinámica a las {hora_hhmm} - {mensaje}")
            self._alarmas_dinamicas.append((hora_hhmm, mensaje))
            return f"Alarma configurada exitosamente para las {hora_hhmm}."
        except Exception as e:
            logger.error(f"Error al agendar alarma dinámica: {e}")
            return f"Fallo al agendar alarma: {str(e)}"

    async def _verificar_y_ejecutar_tareas(self):
        """Evalúa qué tareas deben ejecutarse basado en la hora actual."""
        ahora = datetime.now()
        hora_actual = ahora.strftime("%H:%M")
        fecha_actual = ahora.date()

        # Reseteamos el registro si es un nuevo día (Idempotencia)
        if fecha_actual > self._fecha_ultima_ejecucion:
            self._eventos_ejecutados_hoy.clear()
            self._alarmas_dinamicas.clear() # Las alarmas dinámicas son de 1 día
            self._fecha_ultima_ejecucion = fecha_actual

        # --- TAREAS FIJAS ---
        if hora_actual == "08:00" and "matutino" not in self._eventos_ejecutados_hoy:
            self._eventos_ejecutados_hoy.add("matutino")
            asyncio.create_task(self._checkin_matutino())
            
        elif hora_actual == "14:00" and "mediodia" not in self._eventos_ejecutados_hoy:
            self._eventos_ejecutados_hoy.add("mediodia")
            asyncio.create_task(self._checkin_mediodia())
            
        elif hora_actual == "20:30" and "nocturno" not in self._eventos_ejecutados_hoy:
            self._eventos_ejecutados_hoy.add("nocturno")
            asyncio.create_task(self._checkin_nocturno())
            
        elif hora_actual == "03:00" and "backup" not in self._eventos_ejecutados_hoy:
            self._eventos_ejecutados_hoy.add("backup")
            asyncio.create_task(self._ejecutar_backup_diario())

        # --- TAREAS DINÁMICAS ---
        alarmas_a_remover = []
        for alarma in self._alarmas_dinamicas:
            hora_alarma, mensaje = alarma
            if hora_actual == hora_alarma:
                # Disparar
                logger.info(f"CRON: ¡Sonando alarma! -> {mensaje}")
                asyncio.create_task(self._enviar_mensaje_telegram(f"🔔 **RECORDATORIO:**\n{mensaje}"))
                alarmas_a_remover.append(alarma)
        
        # Eliminar las ya ejecutadas
        for alarma in alarmas_a_remover:
            if alarma in self._alarmas_dinamicas:
                self._alarmas_dinamicas.remove(alarma)

    async def _run_loop(self):
        while self.running:
            await self._verificar_y_ejecutar_tareas()
            # Dormimos hasta el inicio del próximo minuto exacto (para no saltar minutos por lag)
            ahora = datetime.now()
            segundos_restantes = 60 - ahora.second
            await asyncio.sleep(segundos_restantes)

    def start(self):
        """Inicia el scheduler como una tarea asíncrona."""
        if not self.running:
            self.running = True
            # Tomamos el loop principal y agregamos la tarea
            try:
                loop = asyncio.get_running_loop()
                self._task = loop.create_task(self._run_loop())
                logger.info("CRON Asíncrono iniciado.")
            except RuntimeError:
                logger.error("No se pudo iniciar el CRON: No hay Event Loop corriendo.")

    def stop(self):
        """Detiene el scheduler asíncrono."""
        self.running = False
        if self._task:
            self._task.cancel()
            logger.info("CRON Asíncrono detenido.")

# Instancia global
cron_manager = CronManager()

def iniciar_cron():
    """Llamado desde main.py después de que telegram-bot inicie su loop, o explícitamente."""
    cron_manager.start()

def detener_cron():
    cron_manager.stop()
