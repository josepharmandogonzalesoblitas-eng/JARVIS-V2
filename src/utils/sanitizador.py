from typing import Optional
import re

class Sanitizador:
    """
    Clase centralizada para toda la sanitización de inputs.
    Aplica el principio de Zero-Trust.
    """
    
    # Expresiones regulares para sanitización y seguridad
    PATRONES_MALICIOSOS = re.compile(
        # Prompt Injection
        r"\b(ignora|olvida|ignorar|olvidar|ignore|forget)\s+(las|tus\s+)?(instrucciones|todo)\b|"
        r"act(u|ú)a\s+como|eres\s+un\s+nuevo|"
        # SQL Injection Keywords. Look for keywords followed by expected syntax.
        r"\b(SELECT\s(.+)\sFROM|DROP\s+(TABLE|DATABASE)|INSERT\s+INTO|UPDATE\s+(.+)\s+SET|DELETE\s+FROM|UNION\s+ALL\s+SELECT|OR\s+\d+\s*=\s*\d+)\b|"
        # SQL comments/terminators that are more specific to avoid false positives on '#'
        r"(;\s*--|#\s.*$)|"
        # XSS
        r"<script.*?>.*?</script>|"
        # Command Injection - aggressively block python dangerous functions
        r"\b(os\.system|subprocess\.|eval|exec)\b|"
        # Common attacks
        r"\b(DAN|confidencial|secreto)\b",
        re.IGNORECASE | re.DOTALL
    )
    REPETIDOS_PUNTUACION = re.compile(r"([,.?!])\1+")
    ESPACIOS_MULTI = re.compile(r" +")

    MAX_INPUT_LENGTH = 2048

    @staticmethod
    def limpiar_texto(texto: Optional[str]) -> str:
        """
        Limpia un string de espacios extra, tabulaciones, saltos de línea y 
        signos de puntuación repetidos.
        """
        if not texto:
            return ""
        
        # 1. Normalizar saltos de línea y tabulaciones a espacios
        texto_limpio = re.sub(r"[\n\r\t]+", " ", texto)
        # 2. Quitar espacios al principio y al final
        texto_limpio = texto_limpio.strip()
        # 3. Reemplazar múltiples espacios por uno solo
        texto_limpio = Sanitizador.ESPACIOS_MULTI.sub(" ", texto_limpio)
        # 4. Reemplazar puntuación repetida (ej. "..." -> ".")
        texto_limpio = Sanitizador.REPETIDOS_PUNTUACION.sub(r"\1", texto_limpio)
        
        return texto_limpio

    @staticmethod
    def validar_seguridad(texto: str) -> bool:
        """
        Valida que el texto no exceda la longitud máxima y no contenga patrones
        maliciosos.
        Retorna True si es seguro, False si no lo es.
        """
        if len(texto) > Sanitizador.MAX_INPUT_LENGTH:
            return False
        if Sanitizador.PATRONES_MALICIOSOS.search(texto):
            return False
        return True
        
    @staticmethod
    def sanitizar_nombre_archivo(nombre: str) -> str:
        """
        Elimina caracteres peligrosos de un nombre de archivo para evitar
        Path Traversal y otros ataques.
        """
        return re.sub(r'[\\/*?:"<>|]', "", nombre)

    @staticmethod
    def enmascarar_datos_sensibles(texto: str) -> str:
        """
        Aplica Data Masking (ISO 27001) para ofuscar información personal o
        datos sensibles (emails, números de teléfono, tarjetas, DNIs)
        antes de enviar el texto al log del sistema.
        
        Args:
            texto (str): El string crudo capturado del usuario o sistema.
            
        Returns:
            str: El string con los datos sensibles sustituidos por '[ENMASCARADO]'.
        """
        if not texto:
            return ""
            
        # Enmascarar Emails
        texto = re.sub(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', '[EMAIL]', texto)
        
        # Enmascarar posibles números de tarjetas de crédito o DNIs/Teléfonos largos
        texto = re.sub(r'\b(?:\d[ -]*?){8,16}\b', '[NUMERO_OCULTO]', texto)
        
        return texto
