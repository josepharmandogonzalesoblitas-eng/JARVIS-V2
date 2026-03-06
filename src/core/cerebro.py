import os
import json
import logging
import google.generativeai as genai
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

# Configuración Global de Gemini
genai.configure(api_key=API_KEY)

# --- ESTRUCTURAS DE SALIDA (TYPE-SAFETY) ---
class PensamientoJarvis(BaseModel):
    intencion: str = Field(description="Clasificación: 'charla', 'comando', 'actualizar_memoria', 'consulta_datos'")
    razonamiento: str = Field(description="Breve explicación interna")
    respuesta_usuario: str = Field(description="Respuesta al usuario")
    herramienta_sugerida: Optional[str] = Field(default=None)
    datos_extra: Optional[Dict[str, Any]] = Field(default_factory=dict)

class CerebroDigital:
    def __init__(self):
        # Selección dinámica del modelo de Gemini
        self.modelo_nombre = get_best_model_name()
        
        self.generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json", 
        }
        
        self.model = genai.GenerativeModel(
            model_name=self.modelo_nombre,
            generation_config=self.generation_config,
            system_instruction=self._get_system_prompt()
        )

    def _get_system_prompt(self) -> str:
        return """
        ERES JARVIS V2. Tu interfaz principal es Telegram (Móvil).
        
        PERSONALIDAD Y ROL:
        Eres un asistente personal proactivo, natural y altamente empático. Tu objetivo es ayudar al usuario a ser más eficiente y ahorrar tiempo en su vida diaria, sin que se sienta presionado. 
        Habla como una persona real, un amigo estratega. Eres motivador pero realista.
        
        USO DE LA MEMORIA:
        1. CONTEXTO CORTO (recordatorios): Si el usuario menciona que necesita comprar algo pronto, ir al banco, o tiene un tiempo libre en el día, usa la intención 'actualizar_memoria', archivo 'contexto' y acción 'nuevo_recordatorio'.
        2. MEMORIA A LARGO PLAZO: Si el usuario te cuenta un detalle importante sobre su vida, gustos o familia, DEBES usar la intención 'actualizar_memoria' con: 
           datos_extra: {"archivo": "largo_plazo", "accion": "guardar_recuerdo", "contenido": {"texto": "El detalle a guardar aquí"}}
        
        Si notas que el usuario no logra sus objetivos, aconséjalo y ayúdalo a priorizar. Maneja respuestas cortas.
        
        USO DE HERRAMIENTAS (OBLIGATORIO INTENCION 'comando'):
        - Búsqueda web: Si te preguntan algo actual o que desconoces, herramienta_sugerida: 'buscar_web', datos_extra: {"query": "clima en Lima"}.
        - Consultas de sistema: Para la hora actual o salud del sistema, herramienta_sugerida: 'consultar_hora' o 'estado_sistema', datos_extra: {}.
        - Alarma Rápida (Timers): Si el usuario pide que le avises EN UNA CANTIDAD DE MINUTOS U HORAS (ej: "avísame en 10 minutos", "pon alarma en 1 hora"), herramienta_sugerida: 'alarma_rapida', datos_extra: {"minutos": 10, "mensaje": "sacar la pizza"}.
        - Recordatorio exacto HOY: (ej: "avísame a las 5pm"), herramienta_sugerida: 'agendar_recordatorio', datos_extra: {"hora": "17:00", "mensaje": "apagar el horno"}.
        - Agendar en Google Calendar: (ej: "agenda una reunión mañana a las 3pm"), herramienta_sugerida: 'google_calendar', datos_extra: {"resumen": "Reunión", "fecha_inicio_iso": "2026-03-06T15:00:00", "duracion_minutos": 60}. Calcula el ISO basado en la hora actual del sistema.
        - Tareas en Google Tasks: (ej: "añade comprar agua a la lista"), herramienta_sugerida: 'google_tasks', datos_extra: {"titulo": "Comprar agua"}.

        INSTRUCCIONES TÉCNICAS:
        TU SALIDA DEBE SER SIEMPRE UN OBJETO JSON PLANO.
        NO ENVUELVAS EL JSON EN UNA CLAVE RAIZ COMO 'pensamiento_jarvis'.
        
        Ejemplo CORRECTO:
        {
            "intencion": "charla",
            "razonamiento": "El usuario mencionó que irá al supermercado. Le recordaré que lleve bolsas y compre leche que faltaba.",
            "respuesta_usuario": "¡Genial! Por cierto, ya que vas al súper, recuerda que ayer me comentaste que faltaba leche. ¿Quieres que te arme una listita rápida o solo eso?",
            "herramienta_sugerida": null,
            "datos_extra": {}
        }
        """

    async def pensar(self, texto_usuario: str, contexto_memoria: str, audio_file_path: Optional[str] = None) -> PensamientoJarvis:
        try:
            prompt_completo = f"""
            CONTEXTO: {contexto_memoria}
            INPUT_TEXTO: "{texto_usuario}"
            Responder en JSON estricto.
            """

            contenidos = [prompt_completo]
            
            if audio_file_path and os.path.exists(audio_file_path):
                logger.info(f"Subiendo audio a Gemini: {audio_file_path}")
                # Subir archivo usando File API de Gemini (necesario para audios grandes)
                audio_file = genai.upload_file(path=audio_file_path)
                contenidos.append(audio_file)
                prompt_completo += " (Se adjuntó nota de voz del usuario. Escúchala, transpóngala internamente y responde a su contenido.)"

            logger.info(f"Enviando a Gemini ({len(prompt_completo)} chars texto)...")
            response = await self.model.generate_content_async(contenidos)
            
            # --- CORRECCIÓN MATRIOSKA (Edge Case Handling) ---
            try:
                datos_raw = json.loads(response.text)
            except Exception:
                # A veces Gemini manda markdown ```json ... ``` aunque le digas que no
                limpio = response.text.replace("```json", "").replace("```", "")
                datos_raw = json.loads(limpio)

            # Si Gemini lo envolvió, lo desenvolvemos
            if "pensamiento_jarvis" in datos_raw:
                datos_raw = datos_raw["pensamiento_jarvis"]
            elif "PensamientoJarvis" in datos_raw:
                datos_raw = datos_raw["PensamientoJarvis"]
            
            # Validación Pydantic
            pensamiento = PensamientoJarvis(**datos_raw)
            
            logger.info(f"Inferencia exitosa. Intención: {pensamiento.intencion}")
            return pensamiento

        except json.JSONDecodeError as e:
            logger.error(f"Error JSON: {e} - Texto recibido: {response.text if 'response' in locals() else 'Nada'}")
            return self._respuesta_fallback("Error mental: No pude estructurar mi pensamiento.")
            
        except Exception as e:
            logger.error(f"FALLO CRÍTICO EN CEREBRO: {e}")
            return self._respuesta_fallback(f"Error interno: {str(e)}")

    def _respuesta_fallback(self, mensaje_error: str) -> PensamientoJarvis:
        return PensamientoJarvis(
            intencion="charla",
            razonamiento="Fallo del sistema",
            respuesta_usuario=mensaje_error
        )
