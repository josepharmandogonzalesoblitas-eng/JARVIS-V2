from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Type
from pydantic import BaseModel

class ILLMProvider(ABC):
    """
    Abstracción agnóstica para Modelos de Lenguaje (DIP - SOLID).
    Permite intercambiar Gemini por OpenAI, Claude o Groq sin tocar el Core (Low-Coupling).
    """

    @abstractmethod
    async def classify_intent(
        self,
        system_prompt: str,
        user_message: str,
        context: str,
        response_model: Optional[Type[BaseModel]] = None
    ) -> Any:
        """
        Clasifica la intención y extrae datos en un formato JSON.
        Si response_model se proporciona, valida y devuelve el modelo Pydantic (Type-Safety).
        Si no, devuelve un diccionario puro.
        O(1) Efficiency: Ideal para modelos rápidos/baratos.
        """
        pass

    @abstractmethod
    async def generate_response(
        self,
        system_prompt: str,
        user_message: str,
        context: str,
        tool_result: Optional[str] = None,
        audio_file_path: Optional[str] = None,
        image_file_path: Optional[str] = None
    ) -> str:
        """
        Genera la respuesta final en lenguaje natural empático.
        """
        pass
