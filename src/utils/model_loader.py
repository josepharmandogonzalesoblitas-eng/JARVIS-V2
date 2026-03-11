from google import genai
import os
import logging

logger = logging.getLogger("model_loader")

# Modelos en orden de preferencia explícita (MECE — sin ambigüedad)
# gemini-2.0-flash es el modelo actual estable y rápido (2025-2026)
_PRIORIDAD_MODELOS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-001",
    "gemini-1.5-flash",
    "gemini-1.5-flash-001",
    "gemini-1.5-flash-002",
    "gemini-1.5-pro",
    "gemini-1.5-pro-001",
    "gemini-1.5-pro-002",
]

# Fallback definitivo si todo falla (modelo estable y ampliamente disponible)
_FALLBACK_MODEL = "gemini-2.5-flash"


def get_best_model_name() -> str:
    """
    Selecciona el mejor modelo Gemini disponible usando una lista de prioridad explícita.

    Principios aplicados:
    - MECE: Lista de prioridad sin solapamientos ni ambigüedades.
    - Fail-Safe: Fallback definitivo si la API falla.
    - Type-Safety: Siempre retorna un string válido.
    - DRY: La lógica de selección está centralizada aquí.
    """
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("No se encontró GEMINI_API_KEY en .env")

        client = genai.Client(api_key=api_key)

        # Obtener lista de modelos disponibles
        available_models_raw = list(client.models.list())
        # Normalizar nombres (quitar prefijo "models/")
        available_names = {
            m.name.replace("models/", "")
            for m in available_models_raw
        }

        logger.info(f"Modelos disponibles en la API: {sorted(available_names)}")

        # Selección por prioridad explícita (Poka-Yoke: orden determinístico)
        for modelo in _PRIORIDAD_MODELOS:
            if modelo in available_names:
                logger.info(f"Modelo seleccionado: {modelo}")
                return modelo

        # Si ninguno de la lista está disponible, intentar auto-descubrir
        # cualquier modelo "flash" disponible (sin los deprecated -8b, -8b-001)
        flash_models = sorted([
            m for m in available_names
            if "flash" in m
            and "8b" not in m          # Excluir modelos -8b (deprecated)
            and "thinking" not in m    # Excluir modelos de reasoning (costosos)
            and "exp" not in m         # Excluir experimentales en producción
        ], reverse=True)

        if flash_models:
            logger.info(f"Modelo auto-descubierto: {flash_models[0]}")
            return flash_models[0]

        # Fallback final
        logger.warning(f"Ningún modelo preferido encontrado. Usando fallback: {_FALLBACK_MODEL}")
        return _FALLBACK_MODEL

    except Exception as e:
        logger.warning(
            f"No se pudieron listar los modelos de Gemini ({type(e).__name__}: {e}). "
            f"Usando fallback '{_FALLBACK_MODEL}'."
        )
        return _FALLBACK_MODEL


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    from dotenv import load_dotenv
    load_dotenv()
    selected_model = get_best_model_name()
    logger.info(f"Modelo de Gemini seleccionado: {selected_model}")
