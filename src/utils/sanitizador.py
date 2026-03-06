import re
import unicodedata
import logging
from typing import Optional

# --- PRINCIPIO: TRAZABILIDAD ---
# Configuramos un logger específico para seguridad
logger = logging.getLogger("security_audit")

class Sanitizador:
    """
    Módulo estático de limpieza y validación de inputs.
    Aplica principios: Zero-Trust, Poka-Yoke, Fail-Safe.
    """

    # Constantes de seguridad (Magic Numbers fuera del código lógico - DRY/Configurabilidad)
    MAX_INPUT_LENGTH = 4000  # Limite de tokens/caracteres para evitar DoS en la LLM
    PATRONES_PELIGROSOS = [
        r";\s*rm\s+-rf",      # Intento de borrado en Linux
        r"DROP\s+TABLE",      # SQL Injection clásica (por si acaso)
        r"<script>",          # XSS (si alguna vez tienes dashboard web)
        r"\{\{.*\}\}",        # Template Injection (Jinja2/Django)
    ]

    @staticmethod
    def limpiar_texto(texto: Optional[str]) -> str:
        """
        Punto de entrada principal.
        Aplica:
        1. Type-Safety: Maneja None.
        2. Normalización Unicode: Evita errores de encoding (NFKC).
        3. Trimming: Elimina espacios basura.
        4. Zero-Trust: Filtra caracteres de control no imprimibles.
        """
        # 1. Edge Case: Input nulo o no string
        if texto is None or not isinstance(texto, str):
            logger.warning("Input nulo o inválido recibido en sanitizador.")
            return ""

        # 2. Normalización Unicode (NFKC)
        # Convierte caracteres "raros" a su equivalente estándar.
        # Ej: "ℍ" -> "H", "½" -> "1/2". Crucial para NLP.
        texto_norm = unicodedata.normalize('NFKC', texto)

        # 3. Eliminar caracteres de control (ASCII 0-31) excepto saltos de línea
        # Regex eficiente (Big-O lineal)
        texto_limpio = "".join(ch for ch in texto_norm if unicodedata.category(ch)[0] != "C" or ch in "\n\t")

        # 4. Trimming de espacios múltiples (Clean Data)
        texto_limpio = re.sub(r'\s+', ' ', texto_limpio).strip()

        # 5. Fail-Safe: Si después de limpiar no queda nada
        if not texto_limpio:
            return ""

        return texto_limpio

    @staticmethod
    def validar_seguridad(texto: str) -> bool:
        """
        Verifica si el texto cumple con las normas de seguridad.
        Retorna True si es seguro, False si se rechaza.
        """
        # 1. DoS Protection (Longitud excesiva)
        if len(texto) > Sanitizador.MAX_INPUT_LENGTH:
            logger.warning(f"Input rechazado por longitud excesiva: {len(texto)} caracteres.")
            return False

        # 2. Detección de patrones maliciosos (Basic Injection Check)
        for patron in Sanitizador.PATRONES_PELIGROSOS:
            if re.search(patron, texto, re.IGNORECASE):
                logger.critical(f"ALERTA DE SEGURIDAD: Patrón malicioso detectado -> {patron}")
                return False

        return True

    @staticmethod
    def sanitizar_nombre_archivo(nombre: str) -> str:
        """
        Específico para cuando Jarvis necesite guardar/leer archivos.
        Evita 'Path Traversal' (../).
        """
        # Elimina todo lo que no sea alfanumérico, guiones o puntos
        nombre_seguro = re.sub(r'[^\w\-.]', '_', nombre)
        # Evita doble punto (..) para navegación de directorios
        while '..' in nombre_seguro:
            nombre_seguro = nombre_seguro.replace('..', '.')
        return nombre_seguro.strip('_')