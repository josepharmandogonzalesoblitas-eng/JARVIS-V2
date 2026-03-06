import time
import schedule
import logging
import threading
import os
import asyncio
from telegram import Bot
from src.core.orquestador import Orquestador
from src.utils.backup import crear_backup

logger = logging.getLogger("cron")

class CronManager:
    """
    Gestor de tareas programadas (Scheduler).
    Se ejecuta en un hilo separado para no bloquear la interfaz principal.
    """
    def __init__(self):
        self.running = False
        self.thread = None
        self.bot = None
        self.chat_id = os.getenv("TELEGRAM_USER_ID")
        self.orquestador = Orquestador()

        token = os.getenv("TELEGRAM_TOKEN")
        if token:
            self.bot = Bot(token=token)

    def _enviar_mensaje_telegram(self, texto: str):
        """Función helper para enviar mensajes push."""
        if not self.bot or not self.chat_id:
            logger.error("No se puede enviar mensaje push: Faltan credenciales de Telegram.")
            return
            
        async def send():
            await self.bot.send_message(chat_id=self.chat_id, text=texto)
            
        # Ejecutar asíncrono desde el hilo síncrono
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(send())
            loop.close()
        except Exception as e:
            logger.error(f"Error enviando mensaje push: {e}")

    def _run_async_prompt(self, prompt: str):
        """Ejecuta el pipeline asíncrono desde el hilo síncrono del scheduler."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            respuesta = loop.run_until_complete(self.orquestador.procesar_mensaje("SISTEMA_CRON", prompt))
            loop.close()
            self._enviar_mensaje_telegram(respuesta)
        except Exception as e:
            logger.error(f"Error en ejecución asíncrona del CRON: {e}")

    def _checkin_matutino(self):
        logger.info("CRON: Generando Check-in Matutino")
        prompt = "[SISTEMA] Es por la mañana. Saluda al usuario de forma natural, recuérdale sutilmente si tiene tareas o proyectos pendientes importantes para hoy, y pregúntale cómo se siente para empezar el día. Sé breve."
        threading.Thread(target=self._run_async_prompt, args=(prompt,)).start()

    def _checkin_mediodia(self):
        logger.info("CRON: Generando Check-in Mediodía")
        prompt = "[SISTEMA] Es mediodía. Pregúntale al usuario cómo va su día. Si detectas que tiene recordatorios pendientes o lugares a los que ir, recuérdaselo de forma amigable por si quiere aprovechar la tarde."
        threading.Thread(target=self._run_async_prompt, args=(prompt,)).start()

    def _checkin_nocturno(self):
        logger.info("CRON: Generando Check-in Nocturno")
        prompt = "[SISTEMA] Es de noche. Ayuda al usuario a cerrar el día. Pregúntale qué tal le fue, dale un consejo de descanso, y pregúntale si logró avanzar en sus metas para actualizar la bitácora."
        threading.Thread(target=self._run_async_prompt, args=(prompt,)).start()

    def _ejecutar_backup_diario(self):
        logger.info("CRON: Ejecutando backup diario de memoria.")
        crear_backup()

    def _configurar_tareas(self):
        """
        Aquí se definen las tareas y su periodicidad.
        """
        schedule.every().day.at("08:00").do(self._checkin_matutino)
        schedule.every().day.at("14:00").do(self._checkin_mediodia)
        schedule.every().day.at("20:30").do(self._checkin_nocturno)
        
        # Backup automático a las 3:00 AM
        schedule.every().day.at("03:00").do(self._ejecutar_backup_diario)

    def agendar_alarma_dinamica(self, hora_hhmm: str, mensaje: str):
        """
        Programa un mensaje de Telegram para una hora específica del día actual.
        """
        try:
            logger.info(f"CRON: Agendando alarma dinámica a las {hora_hhmm} - {mensaje}")
            
            # La función interna que se ejecutará a la hora acordada
            def tarea_alarma():
                logger.info(f"CRON: ¡Sonando alarma! -> {mensaje}")
                self._enviar_mensaje_telegram(f"🔔 **RECORDATORIO:**\n{mensaje}")
                return schedule.CancelJob # Retorna CancelJob para que solo suene 1 vez (hoy)

            # Usamos schedule para agendarlo hoy a esa hora
            schedule.every().day.at(hora_hhmm).do(tarea_alarma)
            return f"Alarma configurada exitosamente para las {hora_hhmm}."
        except Exception as e:
            logger.error(f"Error al agendar alarma dinámica: {e}")
            return f"Fallo al agendar alarma: {str(e)}"

    def _run_loop(self):
        while self.running:
            schedule.run_pending()
            time.sleep(1)

    def start(self):
        """Inicia el scheduler en un hilo daemon."""
        if not self.running:
            self._configurar_tareas()
            self.running = True
            self.thread = threading.Thread(target=self._run_loop, daemon=True, name="CronThread")
            self.thread.start()
            logger.info("CRON Scheduler iniciado en segundo plano.")

    def stop(self):
        """Detiene el scheduler."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            logger.info("CRON Scheduler detenido.")

# Instancia global
cron_manager = CronManager()

def iniciar_cron():
    cron_manager.start()

def detener_cron():
    cron_manager.stop()
