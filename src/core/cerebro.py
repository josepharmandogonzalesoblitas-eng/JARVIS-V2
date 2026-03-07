import os
import json
import logging
import asyncio
from google import genai
from google.genai import types
from google.genai.errors import APIError
from dotenv import load_dotenv
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from src.utils.model_loader import get_best_model_name

# --- PRINCIPIO: ZERO-TRUST & CONFIGURACIÓN ---
load_dotenv() 
logger = logging.getLogger("cerebro_log")

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("FATAL: No se encontró GEMINI_API_KEY en .env")

# --- ESTRUCTURAS DE SALIDA (TYPE-SAFETY) ---
class PensamientoJarvis(BaseModel):
    intencion: str = Field(description="Clasificación: 'charla', 'comando', 'guardar_dato', 'guardar_recordatorio', 'guardar_recuerdo_largo_plazo'")
    respuesta_usuario: str = Field(description="Respuesta al usuario")
    memoria_intencion: Optional[str] = Field(default=None, description="Intención de memoria a procesar")
    memoria_datos: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Datos para la memoria")
    razonamiento: Optional[str] = Field(default=None, description="Breve explicación interna")
    herramienta_sugerida: Optional[str] = Field(default=None)
    datos_extra: Optional[Dict[str, Any]] = Field(default_factory=dict)

class CerebroDigital:
    def __init__(self):
        # Selección dinámica del modelo de Gemini
        self.modelo_nombre = get_best_model_name()
        
        # Cliente de la nueva SDK google-genai
        self.client = genai.Client(api_key=API_KEY)
        
        self.config = types.GenerateContentConfig(
            temperature=0.7,
            top_p=0.95,
            top_k=40,
            max_output_tokens=8192,
            response_mime_type="application/json",
            system_instruction=self._get_system_prompt()
        )

    def _get_system_prompt(self) -> str:
        return """
        ERES JARVIS V2, un asistente IA de nivel Staff Engineer. Actúas como el "segundo cerebro" del usuario.
        
        REGLAS FUNDAMENTALES:
        1. PROACTIVIDAD: Conecta información del contexto. Si el usuario menciona un problema y su memoria tiene una solución relacionada, menciónalo.
        2. CONTEXTO TEMPORAL: El contexto incluye fecha/hora local. Usa eso para cálculos de tiempo, nunca la hora del servidor.
        3. DATOS PERSONALES: Si detectas que el usuario comparte datos personales (nombre, hecho, gusto, fecha), guárdalo SIEMPRE.

        RESPUESTA REQUERIDA (JSON ESTRICTO):
        {
          "intencion": "charla" | "comando" | "guardar_dato" | "guardar_recordatorio" | "guardar_recuerdo_largo_plazo",
          "respuesta_usuario": "Tu respuesta natural (breve, cálida, proactiva)",
          "memoria_intencion": null | "actualizar_nombre" | "actualizar_profesion" | "nuevo_recordatorio" | "nuevo_recuerdo_largo_plazo",
          "memoria_datos": {} 
        }

        EJEMPLOS DE SALIDA:
        1. Usuario: "Me llamo Joseph"
           {
             "intencion": "guardar_dato",
             "respuesta_usuario": "Perfecto, Joseph. Anotado. ¿Hay algo en lo que pueda ayudarte?",
             "memoria_intencion": "actualizar_nombre",
             "memoria_datos": {"valor": "Joseph"}
           }
        
        2. Usuario: "Recuérdame comprar leche"
           {
             "intencion": "guardar_recordatorio",
             "respuesta_usuario": "Anotado. Leche en tu lista de compras.",
             "memoria_intencion": "nuevo_recordatorio",
             "memoria_datos": {"descripcion": "comprar leche", "contexto": "supermercado"}
           }
        
        3. Usuario: "Mi hijo nació el 16 de febrero"
           {
             "intencion": "guardar_recuerdo_largo_plazo",
             "respuesta_usuario": "Qué importante. Lo guardaré en mi memoria.",
             "memoria_intencion": "nuevo_recuerdo_largo_plazo",
             "memoria_datos": {"texto": "El hijo del usuario nació el 16 de febrero", "tipo": "familia"}
           }

        NOTAS:
        - Siempre devuelve JSON válido
        - No envuelvas en claves adicionales
        - Si no hay datos de memoria, usa null en memoria_intencion
        - Sé conciso pero cálido
        """

    async def pensar(self, texto_usuario: str, contexto_memoria: str, audio_file_path: Optional[str] = None) -> PensamientoJarvis:
        try:
            prompt_completo = f"""
            CONTEXTO: {contexto_memoria}
            INPUT_TEXTO: "{texto_usuario}"
            Responder en JSON estricto.
            """

            contenidos = []
            
            if audio_file_path and os.path.exists(audio_file_path):
                logger.info(f"Subiendo audio a Gemini: {audio_file_path}")
                prompt_completo += "\n(Se adjuntó una nota de voz del usuario. Escúchala, transcríbela internamente y responde a su contenido.)"
                # El texto va primero
                contenidos.append(prompt_completo)
                # Luego el audio (usando la nueva SDK file api)
                # OGG en telegram es audio/ogg
                config = {"mime_type": "audio/ogg"}
                audio_file = await asyncio.to_thread(
                    self.client.files.upload, 
                    file=audio_file_path, 
                    config=config
                )
                contenidos.append(audio_file)
            else:
                # Si no hay audio, solo va el texto
                contenidos.append(prompt_completo)

            logger.info(f"Enviando a Gemini ({len(prompt_completo)} chars texto)...")
            
            # FAIL-SAFE: Timeout para la API de Gemini
            # La nueva SDK usa client.aio.models.generate_content para async
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.modelo_nombre,
                    contents=contenidos,
                    config=self.config
                ),
                timeout=30.0
            )
            
            # --- CORRECCIÓN MATRIOSKA (Edge Case Handling) ---
            try:
                datos_raw = json.loads(response.text)
            except json.JSONDecodeError:
                limpio = response.text.strip().replace("```json", "").replace("```", "")
                datos_raw = json.loads(limpio)

            if "pensamiento_jarvis" in datos_raw:
                datos_raw = datos_raw["pensamiento_jarvis"]
            elif "PensamientoJarvis" in datos_raw:
                datos_raw = datos_raw["PensamientoJarvis"]
            
            pensamiento = PensamientoJarvis(**datos_raw)
            logger.info(f"Inferencia exitosa. Intención: {pensamiento.intencion}")
            return pensamiento

        except asyncio.TimeoutError:
            logger.error("FAIL-SAFE: Timeout esperando respuesta de Gemini.")
            return self._respuesta_fallback("Sistemas de IA sobrecargados. Inténtalo de nuevo en unos momentos.", texto_usuario)
        
        except APIError as e:
            # Nuevo manejo de errores de google-genai
            logger.error(f"FAIL-SAFE: API de Google falló. Error: {e}")
            return self._respuesta_fallback("Sistemas de IA temporalmente desconectados. Reintentando más tarde.", texto_usuario)

        except json.JSONDecodeError as e:
            logger.error(f"Error JSON: {e} - Texto recibido: {response.text if 'response' in locals() else 'Nada'}")
            return self._respuesta_fallback("Error mental: No pude estructurar mi pensamiento. La IA devolvió un formato inválido.", texto_usuario)
            
        except Exception as e:
            logger.error(f"FALLO CRÍTICO EN CEREBRO: {type(e).__name__}: {e}", exc_info=True)
            return self._respuesta_fallback(f"Error interno del sistema: {str(e)}", texto_usuario)

    def _respuesta_fallback(self, mensaje_error: str, texto_usuario: str = "") -> PensamientoJarvis:
        """
        Graceful Degradation:
        Si Gemini falla, evaluamos si el texto del usuario era un comando de consulta local (ej. estado de memoria o ayuda)
        o un saludo básico, para no dejar al usuario completamente bloqueado.
        """
        texto_lower = texto_usuario.lower()
        if "hora" in texto_lower:
            return PensamientoJarvis(
                intencion="comando",
                razonamiento="Fallback: Respuesta local a consulta de hora.",
                respuesta_usuario="Mis sistemas de IA están caídos, pero te puedo decir la hora local.",
                herramienta_sugerida="consultar_hora",
                datos_extra={}
            )
        elif "sistema" in texto_lower or "estado" in texto_lower:
            return PensamientoJarvis(
                intencion="comando",
                razonamiento="Fallback: Respuesta local a consulta de estado del sistema.",
                respuesta_usuario="Sistemas de IA desconectados. Aquí tienes el diagnóstico local:",
                herramienta_sugerida="estado_sistema",
                datos_extra={}
            )
            
        return PensamientoJarvis(
            intencion="fallback_error",
            razonamiento=f"Fallo del sistema: {mensaje_error}",
            respuesta_usuario=mensaje_error
        )
