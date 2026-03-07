import pytest
import os
import asyncio
import uuid
import hashlib
from datetime import datetime
import pytz

from dotenv import load_dotenv
load_dotenv()

from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

# Módulos a probar
from src.core.orquestador import Orquestador
from src.core.repositories import JSONDataRepository, ChromaVectorRepository, DefaultToolsRepository
from src.data import db_handler, schemas

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e]


def _make_hash_embedding_fn():
    """
    Crea una función de embedding determinista basada en hash.
    No requiere ninguna API externa: ideal para tests E2E aislados donde
    lo que se valida es el FLUJO de datos, no la calidad semántica.
    Con colecciones pequeñas (1-3 items) ChromaDB devuelve todos los
    resultados independientemente de la distancia, por lo que el test
    funciona correctamente.
    """
    class _HashEmbeddingFn(EmbeddingFunction[Documents]):
        """
        Embedding determinista para tests: hereda de EmbeddingFunction[Documents]
        para que chromadb 1.5+ pueda llamar embed_query() (método concreto heredado).
        """
        def __init__(self):
            pass  # Requerido por chromadb 1.5+ para evitar DeprecationWarning

        @staticmethod
        def name() -> str:
            return "hash_embedding_fn_test"

        def get_config(self) -> dict:
            return {"type": "hash_md5", "dims": 768}

        @staticmethod
        def build_from_config(config: dict) -> "_HashEmbeddingFn":
            return _HashEmbeddingFn()

        def __call__(self, input: Documents) -> Embeddings:
            result = []
            for text in input:
                h = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
                vec = [(h >> (i % 64)) % 100 / 100.0 for i in range(768)]
                result.append(vec)
            return result
    return _HashEmbeddingFn()


def setup_test_environment(tmp_path, monkeypatch):
    """
    Helper function para preparar un entorno de test limpio y aislado.
    
    CORRECCIÓN: El patched_init ahora usa EphemeralClient (in-memory) con una
    función de embedding basada en hash. Esto garantiza:
    - Aislamiento total entre tests (cada test tiene su propia colección)
    - Sin dependencia de la API de Google para la parte vectorial
    - Sin warnings de chromadb sobre api_key deprecada
    - Las escrituras de MemoryManager van a la MISMA colección que lee el test
      (gracias a la inyección de dependencias en Orquestador → MemoryManager)
    """
    # Verificar API key para la parte LLM (Gemini sigue siendo necesario)
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY no encontrado, saltando prueba E2E.")

    # 1. Crear directorio de memoria temporal
    test_memory_path = tmp_path / "MEMORIA_E2E_REAL"
    test_memory_path.mkdir(exist_ok=True)

    # 2. Monkeypatch para que todos los módulos usen el directorio temporal
    monkeypatch.setattr(db_handler, 'MEMORY_PATH', str(test_memory_path))

    # 3. Patch para el __init__ de ChromaVectorRepository con client in-memory
    def patched_init(self):
        import chromadb
        self.persist_directory = str(test_memory_path / "vector_db")
        self._lock = asyncio.Lock()
        self.client = chromadb.EphemeralClient()
        self.collection = self.client.create_collection(
            name=f"test_{uuid.uuid4().hex}",
            embedding_function=_make_hash_embedding_fn()
        )

    monkeypatch.setattr(ChromaVectorRepository, '__init__', patched_init)

    # 4. Inicializar la base de datos en el directorio temporal
    db_handler.init_db()

    # 5. Crear la instancia del orquestador con repositorios reales
    orquestador = Orquestador(
        data_repo=JSONDataRepository(),
        vector_repo=ChromaVectorRepository(),
        tools_repo=DefaultToolsRepository()
    )

    return orquestador


# --- Suite de Pruebas E2E (Simulación de Conversación) ---

async def test_memoria_largo_plazo_conversacional_e2e(tmp_path, monkeypatch):
    """
    Prueba un flujo conversacional completo de guardado y recuperación en memoria a largo plazo,
    verificando también la consulta directa al repositorio vectorial.
    """
    orquestador_e2e = setup_test_environment(tmp_path, monkeypatch)
    user_id = "test_user_conversacional"
    color_favorito = "azul oscuro"

    # 1. El usuario le dice al bot su color favorito.
    frase_guardado = f"Mi color favorito es el {color_favorito}."
    print(f"\n[TEST] Enviando: '{frase_guardado}'")
    respuesta_guardado = await orquestador_e2e.procesar_mensaje(user_id, frase_guardado)
    print(f"[TEST] Recibido: '{respuesta_guardado}'")

    # La IA debería confirmar que ha guardado el dato.
    # Aceptamos varias formas de confirmación natural en español.
    respuesta_lower = respuesta_guardado.lower()
    confirmaciones_validas = [
        "entendido", "guardado", "anotado", "guardo",
        "registrado", "perfecto", "listo", "recuerdo",
        "anoto", "tomado nota", "lo tengo", "en cuenta", "preferencia"
    ]
    assert any(c in respuesta_lower for c in confirmaciones_validas), (
        f"La IA no confirmó el guardado del recuerdo. "
        f"Respuesta recibida: '{respuesta_guardado}'"
    )

    # Pausa para dar tiempo a que la base de datos vectorial se actualice.
    await asyncio.sleep(2)

    # 2. Verificación interna: Consultar directamente el Vector Repository.
    #    Esto asegura que el dato FUE escrito, no solo que la IA "recuerda" por contexto.
    print("[TEST] Verificando directamente en la base de datos vectorial...")
    vector_repo = orquestador_e2e.vector_repo
    recuerdos = await vector_repo.async_buscar_recuerdos_relevantes("¿cuál es mi color favorito?", n_results=1)
    print(f"[TEST] Recuerdos encontrados en DB: {recuerdos}")

    assert len(recuerdos) > 0, "La base de datos vectorial no devolvió ningún recuerdo."
    assert color_favorito in recuerdos[0], f"El recuerdo '{recuerdos[0]}' no contiene '{color_favorito}'."
    print("[TEST] Verificación en DB exitosa.")

    # 3. El usuario pregunta por su color favorito en un nuevo mensaje (nuevo ciclo).
    frase_pregunta = "¿Sabes cuál es mi color preferido?"
    print(f"[TEST] Enviando: '{frase_pregunta}'")
    respuesta_recuperacion = await orquestador_e2e.procesar_mensaje(user_id, frase_pregunta)
    print(f"[TEST] Recibido: '{respuesta_recuperacion}'")

    # 4. Verificación final: La IA debe responder correctamente.
    assert color_favorito in respuesta_recuperacion.lower(), \
           f"La IA no recordó el color. Respuesta: '{respuesta_recuperacion}'"
    print("[TEST] Flujo conversacional E2E completado con éxito.")


async def test_memoria_corto_plazo_e2e(tmp_path, monkeypatch):
    """Prueba guardar y recuperar un recordatorio de la memoria a corto plazo."""
    orquestador_e2e = setup_test_environment(tmp_path, monkeypatch)
    # Guardar
    await orquestador_e2e.procesar_mensaje("user123", "Recuérdame comprar leche")

    # Verificar
    respuesta = await orquestador_e2e.procesar_mensaje("user123", "¿Qué tenía pendiente para comprar?")
    assert "leche" in respuesta.lower()


async def test_memoria_largo_plazo_e2e(tmp_path, monkeypatch):
    """Prueba guardar y recuperar un hecho de la memoria a largo plazo (vectorial)."""
    orquestador_e2e = setup_test_environment(tmp_path, monkeypatch)
    # Guardar
    await orquestador_e2e.procesar_mensaje("user123", "Dato importante: el cumpleaños de mi hijo es el 16 de febrero.")
    await asyncio.sleep(2)  # Dar tiempo a que ChromaDB procese

    # Verificar
    respuesta = await orquestador_e2e.procesar_mensaje("user123", "¿Cuándo es el cumpleaños de mi hijo?")
    assert "16 de febrero" in respuesta.lower()


async def test_actualizar_y_recordar_perfil_e2e(tmp_path, monkeypatch):
    """Prueba que el bot puede actualizar el nombre del usuario y recordarlo."""
    orquestador_e2e = setup_test_environment(tmp_path, monkeypatch)
    # Guardar
    await orquestador_e2e.procesar_mensaje("user123", "Por cierto, me llamo Joseph")

    # Verificar
    respuesta = await orquestador_e2e.procesar_mensaje("user123", "¿Cómo me llamo?")
    assert "joseph" in respuesta.lower()


async def test_herramienta_timezone_e2e(tmp_path, monkeypatch):
    """Prueba que la herramienta de la hora es consciente de la zona horaria."""
    orquestador_e2e = setup_test_environment(tmp_path, monkeypatch)
    # Configurar la zona horaria en el entorno de prueba
    entorno = await orquestador_e2e.data_repo.async_read_data("entorno.json", schemas.Entorno)
    entorno.zona_horaria = "Europe/Madrid"
    await orquestador_e2e.data_repo.async_save_data("entorno.json", entorno)

    respuesta = await orquestador_e2e.procesar_mensaje("user123", "¿Qué hora es?")

    # Verificar que la hora devuelta corresponde a la zona horaria configurada
    madrid_time = datetime.now(pytz.timezone("Europe/Madrid"))
    # Comparamos solo la hora para evitar fallos por segundos de diferencia
    assert madrid_time.strftime('%H:%M') in respuesta
