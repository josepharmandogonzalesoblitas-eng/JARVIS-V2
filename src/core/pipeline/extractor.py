from typing import Dict, Any, Type
from pydantic import BaseModel, create_model
import logging

from src.core.llm.interfaces import ILLMProvider

logger = logging.getLogger("extractor")

class ParameterExtractor:
    """
    Componente dedicado a extraer los argumentos necesarios para una herramienta o memoria específica.
    SRP, Type-Safety dinámico.
    """
    def __init__(self, llm_provider: ILLMProvider):
        self.llm_provider = llm_provider
        self.system_prompt = """
        Eres el Extractor de Entidades de JARVIS V2.
        Tu único trabajo es leer el mensaje del usuario y extraer los parámetros exactos necesarios
        para ejecutar la herramienta o memoria: {herramienta}.
        
        IMPORTANTE: 
        - Devuelve un JSON plano que contenga directamente los parámetros esperados por la herramienta.
        - Ejemplo de google_calendar: {{"resumen": "Reunión", "fecha_inicio_iso": "YYYY-MM-DDTHH:MM:00", "duracion_minutos": 60}}
        - Ejemplo de activar_modo: {{"modo": "trabajo_profundo"}} (no uses 'foco', usa 'trabajo_profundo')
        - Ejemplo de memoria_actualizar_preferencia: {{"clave": "color_favorito", "valor": "azul"}}
        - Ejemplo de memoria_actualizar_nombre: {{"valor": "Joseph"}}
        - Ejemplo de memoria_nuevo_recordatorio: {{"descripcion": "comprar pan", "contexto": "general"}}
        - Ejemplo de memoria_nuevo_recuerdo_largo_plazo: {{"texto": "Mi hijo nació el 16 de febrero", "tipo": "general"}}
        - Ejemplo de alarma_rapida: {{"minutos": 5, "mensaje": "sacar pizza"}}
        - Ejemplo de agendar_recordatorio: {{"hora": "15:30", "mensaje": "llamar a mamá"}}
        """

    async def extract(self, user_message: str, context: str, herramienta: str) -> Dict[str, Any]:
        """
        Llama al LLM pidiendo que extraiga los datos en formato dict.
        """
        logger.info(f"Extrayendo parámetros para {herramienta}...")
        
        prompt_dinamico = self.system_prompt.replace("{herramienta}", herramienta)

        try:
            # Sin response_model, devuelve dict puro
            result_dict = await self.llm_provider.classify_intent(
                system_prompt=prompt_dinamico,
                user_message=user_message,
                context=context
            )
            
            # Limpieza defensiva por si el LLM aún así anida la info
            if "datos" in result_dict and isinstance(result_dict["datos"], dict):
                return result_dict["datos"]
                
            return result_dict
        except Exception as e:
            logger.error(f"Error Extrayendo Parámetros para {herramienta}: {e}")
            raise ValueError(f"No pude extraer los parámetros necesarios para {herramienta}.")
