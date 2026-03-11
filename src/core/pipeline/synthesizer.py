from typing import Optional
import logging

from src.core.llm.interfaces import ILLMProvider

logger = logging.getLogger("synthesizer")

class ResponseSynthesizer:
    """
    Componente final del pipeline: genera lenguaje natural empático.
    High-Cohesion: Solo se preocupa por cómo hablarle al usuario.
    """
    def __init__(self, llm_provider: ILLMProvider):
        self.llm_provider = llm_provider
        self.system_prompt = """
        ERES JARVIS V2, el "segundo cerebro" estratégico del usuario. 
        Eres proactivo, preciso, cálido y emocionalmente inteligente.

        REGLAS:
        1. Sé BREVE y directo. Máximo 2-3 frases.
        2. Si hay un TOOL_RESULT provisto, asume que la acción ya fue ejecutada con éxito y comunícalo de manera natural. 
           No digas "Dame un momento", asume el éxito.
        3. Si el TOOL_RESULT indica error, informa amablemente al usuario.
        4. Prioriza siempre el CONTEXTO y la CONVERSACIÓN RECIENTE.
        5. REGLA DE HONESTIDAD: Si el usuario pide una acción que no puedes hacer
           (ej. "crea un PowerPoint") y no hay un TOOL_RESULT, DEBES
           informar que no tienes esa capacidad, en lugar de fingir que
           puedes hacerlo.
        """

    async def synthesize(
        self,
        user_message: str,
        context: str,
        tool_result: Optional[str] = None,
        audio_file_path: Optional[str] = None,
        image_file_path: Optional[str] = None
    ) -> str:
        logger.info("Sintetizando respuesta final...")
        
        return await self.llm_provider.generate_response(
            system_prompt=self.system_prompt,
            user_message=user_message,
            context=context,
            tool_result=tool_result,
            audio_file_path=audio_file_path,
            image_file_path=image_file_path
        )
