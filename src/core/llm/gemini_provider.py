import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel
from google import genai
from google.genai import types
from google.genai.errors import APIError

from src.utils.model_loader import get_best_model_name
from src.core.llm.interfaces import ILLMProvider

logger = logging.getLogger("gemini_provider")

class GeminiProvider(ILLMProvider):
    """
    Implementación específica para Google Gemini (SOLID: Liskov Substitution).
    """

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("FATAL: GEMINI_API_KEY missing (Fail-Safe)")
        
        self.model_name = get_best_model_name()
        self.client = genai.Client(api_key=self.api_key)

    async def classify_intent(
        self,
        system_prompt: str,
        user_message: str,
        context: str,
        response_model: Optional[Type[BaseModel]] = None
    ) -> Any:
        """
        Obliga a Gemini a devolver un JSON.
        Si response_model es dado, retorna el modelo validado.
        Si no, retorna un dict puro (Flexibilidad, Type-Safety dinámico).
        """
        config = types.GenerateContentConfig(
            temperature=0.0, # Determinístico
            response_mime_type="application/json",
            system_instruction=system_prompt
        )

        prompt = f"CONTEXT: {context}\n\nUSER_MESSAGE: '{user_message}'\n\nReturn ONLY a valid JSON without markdown wrapping."
        
        try:
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=[prompt],
                    config=config
                ),
                timeout=15.0
            )

            # Extraemos y limpiamos el JSON
            raw_text = response.text.strip()
            
            # Auto-healing (Poka-Yoke): buscar bloque JSON explícito
            import re
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                raw_text = json_match.group(0)
            else:
                raw_text = raw_text.replace("```json", "").replace("```", "").strip()

            data_dict = json.loads(raw_text)
            
            if response_model:
                # Type-Safety: Pydantic lanza excepción si el formato no es válido
                return response_model(**data_dict)
            return data_dict

        except asyncio.TimeoutError:
            logger.error("Gemini Intent Timeout (Graceful Degradation trigger)")
            raise RuntimeError("LLM Timeout")
        except APIError as e:
            logger.error(f"Gemini API Error: {e}")
            raise
        except Exception as e:
            logger.error(f"Gemini Parsing Error: {e} - Raw: {response.text if 'response' in locals() else 'N/A'}")
            # Retornar dict vacío en lugar de crashear si no es critical type
            if not response_model:
                return {}
            raise

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
        Generación de lenguaje natural, asimilando tool_result si existe (High-Cohesion).
        """
        config = types.GenerateContentConfig(
            temperature=0.7, # Más creativo para empatía
            system_instruction=system_prompt
        )

        prompt_parts = [f"CONTEXT: {context}"]
        
        if tool_result:
            prompt_parts.append(f"TOOL_RESULT (The system executed an action, incorporate this seamlessly): {tool_result}")
            
        prompt_parts.append(f"USER_MESSAGE: '{user_message}'")
        prompt = "\n\n".join(prompt_parts)

        contents = []

        # Graceful handling de archivos adjuntos (Modularidad)
        if audio_file_path and os.path.exists(audio_file_path):
            try:
                upload_config = types.UploadFileConfig(mime_type="audio/ogg")
                audio_file = await asyncio.to_thread(
                    self.client.files.upload,
                    file=audio_file_path,
                    config=upload_config
                )
                contents.append(audio_file)
                prompt += "\n(Audio attached by user)"
            except Exception as e:
                logger.warning(f"Failed to attach audio: {e}")

        elif image_file_path and os.path.exists(image_file_path):
            try:
                ext = os.path.splitext(image_file_path)[1].lower()
                mime_map = {
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".webp": "image/webp"
                }
                mime_type = mime_map.get(ext, "image/jpeg")
                with open(image_file_path, "rb") as f:
                    image_bytes = f.read()
                image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                contents.append(image_part)
                prompt += "\n(Image attached by user)"
            except Exception as e:
                logger.warning(f"Failed to attach image: {e}")

        contents.append(prompt)

        # Fail-Safe / Retry Mecanismo (2 intentos para lidiar con picos de Rate Limit 429)
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = await asyncio.wait_for(
                    self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=config
                    ),
                    timeout=30.0
                )
                
                if not response.text:
                    logger.warning("Gemini devolvió respuesta vacía en generate_response.")
                    return "Tu mensaje fue recibido, pero mi sistema de IA devolvió una respuesta en blanco (posible bloqueo). ¿Puedes intentar de otra manera?"
                    
                return response.text.strip()
                
            except asyncio.TimeoutError:
                logger.error(f"Gemini Gen Timeout (Attempt {attempt+1}/{max_retries})")
                if attempt == max_retries - 1:
                    return "Mis sistemas de IA están sobrecargados (Timeout). Inténtalo de nuevo más tarde."
            except APIError as e:
                logger.error(f"Gemini API Error (Attempt {attempt+1}/{max_retries}): {e}")
                if "429" in str(e):
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2) # Backoff
                        continue
                    return "He alcanzado mi límite de cuota (Rate Limit) con Google Gemini. Por favor espera unos minutos."
                if attempt == max_retries - 1:
                    return f"Fallo de conexión API: {e}"
            except Exception as e:
                logger.error(f"Gemini Gen Error: {e}", exc_info=True)
                return "Sistemas de IA temporalmente desconectados. Respondiendo en modo seguro."
