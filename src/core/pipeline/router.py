from typing import Optional
from pydantic import BaseModel, Field
import logging

from src.core.llm.interfaces import ILLMProvider

logger = logging.getLogger("router")

class RouterSchema(BaseModel):
    """
    Schema estricto para el enrutador de intenciones (Type-Safety).
    """
    intencion: str = Field(alias="intencion", description="Clasificación: 'charla', 'conversacion_casual', 'comando', 'guardar_dato', 'guardar_recordatorio'")
    herramienta_sugerida: Optional[str] = Field(default=None, description="Nombre exacto de la herramienta si es comando")
    memoria_intencion: Optional[str] = Field(default=None, description="Intención de memoria si aplica")
    
    # Tolerancia a errores de Gemini (Poka-Yoke)
    def __init__(self, **data):
        if 'intention' in data and 'intencion' not in data:
            data['intencion'] = data.pop('intention')
        super().__init__(**data)

class IntentionRouter:
    """
    Componente del pipeline encargado exclusivamente de clasificar la intención.
    SRP (Single Responsibility Principle) - Big-O Efficiency (O(1)).
    """
    def __init__(self, llm_provider: ILLMProvider):
        self.llm_provider = llm_provider
        self.system_prompt = """
        Eres el Router Inteligente de JARVIS V2.
        Tu ÚNICO trabajo es clasificar la intención del usuario y determinar si necesita una herramienta.
        No respondas al usuario, solo clasifica.

        INTENCIONES VÁLIDAS:
        - "charla": conversacion general.
        - "comando": necesita usar una herramienta (ej. clima, google_calendar, google_tasks, buscar_web, activar_modo, generar_grafico_energia).
        - "guardar_dato": actualizar un dato en memoria (ej. color favorito, nombre).
        - "guardar_recordatorio": nuevo pendiente.
        - "guardar_recuerdo_largo_plazo": eventos, cumpleaños, recuerdos clave.

        REGLA DE MODOS AUTOMÁTICOS:
        Si el usuario dice "necesito hablar de algo" o "me siento mal",
        considera usar la herramienta "activar_modo" con "escucha_profunda".

        FORMATO ESTRICTO:
        Asegúrate de usar la llave exacta "intencion" (no "intention").

        REGLA DE MEMORIA_INTENCION:
        Si la intencion es "guardar_dato", DEBES llenar memoria_intencion con:
        - "actualizar_preferencia" (para gustos, hobbies, color favorito)
        - "actualizar_nombre", "actualizar_edad", "actualizar_rutina", "actualizar_persona_clave"
        Si la intencion es "guardar_recordatorio", usa memoria_intencion: "nuevo_recordatorio".
        Si la intencion es "guardar_recuerdo_largo_plazo", usa memoria_intencion: "nuevo_recuerdo_largo_plazo".

        REGLA DE HERRAMIENTAS:
        Si el usuario dice "pon en mi calendario a las 3pm", usa herramienta_sugerida: "google_calendar".
        Si dice "pon en mis tareas", usa "google_tasks".
        Si dice "recuérdame a las 5", usa "agendar_recordatorio".
        Si dice "pon timer en 5 min", usa "alarma_rapida".
        Si dice "activa modo foco/terapeuta", usa "activar_modo".
        Si dice "muéstrame mi progreso de energía", usa "generar_grafico_energia".
        Si no hay herramienta clara, devuelve null.

        REGLA DE ORO - BÚSQUEDA WEB:
        Si el usuario pregunta por cualquier dato que NO esté en su memoria local
        (ej: precios, noticias, definiciones, capitales, clima, hechos),
        DEBES usar la herramienta "buscar_web". Sé agresivo con esto.
        """

    async def route(self, user_message: str, context: str) -> RouterSchema:
        logger.info("Enrutando intención...")
        try:
            result = await self.llm_provider.classify_intent(
                system_prompt=self.system_prompt,
                user_message=user_message,
                context=context,
                response_model=RouterSchema
            )
            return result
        except Exception as e:
            logger.error(f"Error en Router, Fallback a charla: {e}")
            return RouterSchema(intencion="charla")
