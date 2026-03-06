import google.generativeai as genai
import os

def get_best_model_name():
    """
    Lista los modelos de Gemini disponibles y selecciona el más adecuado.
    Prioriza los modelos "flash" por su velocidad y eficiencia.
    """
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("No se encontró GEMINI_API_KEY en .env")

        genai.configure(api_key=api_key)
        
        available_models = [m.name for m in genai.list_models()]
        
        # Prioridad 1: Buscar el último modelo "flash"
        flash_models = sorted([m for m in available_models if "flash" in m and "models/" in m], reverse=True)
        if flash_models:
            return flash_models[0].replace("models/", "")

        # Prioridad 2: Buscar el último modelo "pro" si no hay "flash"
        pro_models = sorted([m for m in available_models if "pro" in m and "models/" in m], reverse=True)
        if pro_models:
            return pro_models[0].replace("models/", "")
            
        # Fallback a un modelo conocido si todo falla
        return "gemini-1.5-flash"

    except Exception as e:
        print(f"Error al listar modelos de Gemini: {e}")
        # Fallback a un modelo conocido si la API falla
        return "gemini-1.5-flash"

if __name__ == '__main__':
    # Esto es para probar el script directamente
    load_dotenv()
    selected_model = get_best_model_name()
    print(f"Modelo seleccionado: {selected_model}")
