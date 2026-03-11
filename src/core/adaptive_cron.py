import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class AdaptiveCron:
    """
    Motor de lógica para el agendamiento dinámico de tareas del Cron.
    Se integra con CronManager para agendar alarmas y recordatorios
    basados en el contexto de una conversación.
    """

    def analyze_and_schedule(self, conversation_context: Dict[str, Any]) -> Optional[str]:
        """
        Analiza el contexto de una conversación y, si detecta una intención de
        agendamiento futuro, delega al cron_manager para agendar la alarma.

        Args:
            conversation_context: El contexto de la conversación actual,
                                  incluyendo intent, entities, etc.

        Returns:
            Mensaje de confirmación si se agendó algo, None en caso contrario.
        """
        try:
            from src.core.cron import cron_manager

            intent = conversation_context.get("intent")
            entities = conversation_context.get("entities", {})

            # Si hay una intención de recordatorio con hora definida
            if intent in ("crear_recordatorio", "agendar_alarma") and "time" in entities:
                hora = entities["time"]  # ej: "15:30"
                mensaje = entities.get("subject", "Recordatorio programado por JARVIS")

                confirmacion = cron_manager.agendar_alarma_dinamica(hora, mensaje)
                logger.info(f"AdaptiveCron: Tarea dinámica agendada → {hora}: {mensaje}")
                return confirmacion

        except Exception as e:
            logger.error(f"AdaptiveCron.analyze_and_schedule error: {e}", exc_info=True)

        return None

    def schedule_reminder(self, hora_hhmm: str, mensaje: str) -> str:
        """
        Agenda directamente un recordatorio a una hora específica.

        Args:
            hora_hhmm: Hora en formato "HH:MM"
            mensaje: Texto del recordatorio

        Returns:
            Mensaje de confirmación
        """
        try:
            from src.core.cron import cron_manager
            return cron_manager.agendar_alarma_dinamica(hora_hhmm, mensaje)
        except Exception as e:
            logger.error(f"AdaptiveCron.schedule_reminder error: {e}")
            return f"❌ No se pudo agendar el recordatorio: {str(e)}"


# Singleton
adaptive_cron = AdaptiveCron()
