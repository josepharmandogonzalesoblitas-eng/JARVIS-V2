"""
HERRAMIENTA TTS (Text-to-Speech) con Personalidad Contextual.

Convierte las respuestas de JARVIS en audio natural usando gTTS (Google TTS).
- Gratuito, sin API key requerida.
- Limpia el texto de markdown y emojis para pronunciación natural.
- Adapta el tono al contexto temporal (mañana / tarde / noche).
"""

import os
import re
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("tool_tts")


def texto_a_audio(texto: str, contexto_hora: Optional[str] = None) -> Optional[str]:
    """
    Convierte texto a audio usando gTTS.

    Args:
        texto: El texto a convertir en voz.
        contexto_hora: "manana" | "tarde" | "noche" | None (auto-detecta por hora local).

    Returns:
        Ruta al archivo .mp3 temporal generado, o None si falla.
    """
    try:
        from gtts import gTTS

        # Auto-detectar contexto de hora
        if not contexto_hora:
            hora_actual = datetime.now().hour
            if 5 <= hora_actual < 12:
                contexto_hora = "manana"
            elif 12 <= hora_actual < 19:
                contexto_hora = "tarde"
            else:
                contexto_hora = "noche"

        # Limpiar texto para TTS natural
        texto_limpio = _limpiar_para_tts(texto)

        if not texto_limpio or len(texto_limpio) < 3:
            logger.warning("TTS: texto vacío tras limpieza, omitiendo.")
            return None

        # Limitar longitud para evitar audios muy largos
        if len(texto_limpio) > 500:
            texto_limpio = texto_limpio[:497] + "..."

        # Generar audio en español
        tts = gTTS(text=texto_limpio, lang='es', slow=False)

        # Guardar en directorio temporal
        os.makedirs("LOGS/temp", exist_ok=True)
        timestamp = int(datetime.now().timestamp() * 1000)
        audio_path = os.path.join("LOGS", "temp", f"tts_{timestamp}.mp3")
        tts.save(audio_path)

        logger.info(f"TTS generado: {audio_path} ({len(texto_limpio)} chars, contexto: {contexto_hora})")
        return audio_path

    except ImportError:
        logger.error("gTTS no instalado. Ejecuta: pip install gTTS")
        return None
    except Exception as e:
        logger.error(f"Error en TTS: {e}")
        return None


def _limpiar_para_tts(texto: str) -> str:
    """
    Limpia el texto de:
    - Formato Markdown (* _ # [] ())
    - Emojis y caracteres especiales
    - Múltiples espacios/saltos de línea
    - Mantiene: letras, números, puntuación básica y caracteres españoles.
    """
    if not texto:
        return ""

    # Eliminar código inline y bloques de código
    texto = re.sub(r'```[^`]*```', '', texto, flags=re.DOTALL)
    texto = re.sub(r'`[^`]+`', '', texto)

    # Eliminar formato markdown
    texto = re.sub(r'\*\*([^*]+)\*\*', r'\1', texto)  # **bold** → bold
    texto = re.sub(r'\*([^*]+)\*', r'\1', texto)       # *italic* → italic
    texto = re.sub(r'__([^_]+)__', r'\1', texto)       # __bold__ → bold
    texto = re.sub(r'_([^_]+)_', r'\1', texto)         # _italic_ → italic
    texto = re.sub(r'#{1,6}\s*', '', texto)             # ## Título → Título
    texto = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', texto)  # [link](url) → link
    texto = re.sub(r'^\s*[-*+]\s+', '', texto, flags=re.MULTILINE)  # listas

    # Eliminar emojis y caracteres Unicode especiales fuera del español
    texto = re.sub(
        r'[^\w\s\.\,\!\?\;\:\-\(\)áéíóúüñÁÉÍÓÚÜÑ0-9]',
        ' ',
        texto
    )

    # Normalizar espacios y saltos de línea
    texto = re.sub(r'\n+', '. ', texto)
    texto = re.sub(r'\s{2,}', ' ', texto)
    texto = texto.strip()

    return texto
