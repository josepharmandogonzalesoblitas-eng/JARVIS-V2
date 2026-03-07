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
    resultados independientemente de la distancia.
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
    Setup test environment with temp memory directory.

    CORRECCIÓN: El patched_init ahora usa EphemeralClient (in-memory) con una
    función de embedding basada en hash. Esto garantiza:
    - Aislamiento total entre tests (cada test tiene su propia colección fresca)
    - Sin dependencia de la API de Google para la parte vectorial
    - Sin warnings de chromadb sobre api_key deprecated
    - Las escrituras de MemoryManager van a la MISMA colección que el test lee,
      ya que Orquestador inyecta vector_repo en MemoryManager.
    """
    # La API key sigue siendo necesaria para el LLM (Gemini)
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY no encontrado, saltando prueba E2E.")

    test_memory_path = tmp_path / "MEMORIA_E2E_REAL"
    test_memory_path.mkdir(exist_ok=True)

    monkeypatch.setattr(db_handler, 'MEMORY_PATH', str(test_memory_path))

    def patched_init(self):
        import chromadb
        self.persist_directory = str(test_memory_path / "vector_db")
        self._lock = asyncio.Lock()
        # EphemeralClient: in-memory, sin persistencia, sin problemas de api_key
        self.client = chromadb.EphemeralClient()
        # Colección única por test para aislamiento total
        self.collection = self.client.create_collection(
            name=f"test_{uuid.uuid4().hex}",
            embedding_function=_make_hash_embedding_fn()
        )

    monkeypatch.setattr(ChromaVectorRepository, '__init__', patched_init)

    db_handler.init_db()

    return Orquestador(
        data_repo=JSONDataRepository(),
        vector_repo=ChromaVectorRepository(),
        tools_repo=DefaultToolsRepository()
    )


async def test_guardar_nombre(tmp_path, monkeypatch):
    """Verifica que el nombre se guarda correctamente en JSON"""
    orq = setup_test_environment(tmp_path, monkeypatch)

    await orq.procesar_mensaje("user1", "Me llamo Joseph")

    persona = await orq.data_repo.async_read_data("persona.json", schemas.Persona)
    assert persona.nombre == "Joseph", f"Nombre esperado 'Joseph', obtenido '{persona.nombre}'"


async def test_guardar_recordatorio(tmp_path, monkeypatch):
    """Verifica que los recordatorios se guardan correctamente"""
    orq = setup_test_environment(tmp_path, monkeypatch)

    await orq.procesar_mensaje("user1", "Recuérdame comprar leche")

    contexto = await orq.data_repo.async_read_data("contexto.json", schemas.GestorContexto)
    recordatorios = [r.descripcion for r in contexto.recordatorios_pendientes if not r.completado]

    assert any("leche" in r.lower() for r in recordatorios), (
        f"Recordatorio de leche no encontrado. Recordatorios: {recordatorios}"
    )


async def test_guardar_recuerdo_largo_plazo(tmp_path, monkeypatch):
    """
    Verifica que los recuerdos a largo plazo se guardan correctamente.

    CORRECCIÓN: Con la inyección de vector_repo en MemoryManager, ahora el
    recuerdo se guarda en la MISMA colección in-memory que está enlazada al
    orquestador. La búsqueda posterior usa esa misma colección, por lo que
    el test ya no devuelve vacío.
    """
    orq = setup_test_environment(tmp_path, monkeypatch)

    await orq.procesar_mensaje("user1", "Mi hijo nació el 16 de febrero")

    await asyncio.sleep(1)

    recuerdos = await orq.vector_repo.async_buscar_recuerdos_relevantes("cumpleaños hijo", n_results=1)
    assert len(recuerdos) > 0, "Recuerdo no encontrado en base vectorial"
    assert "16" in recuerdos[0] or "febrero" in recuerdos[0].lower(), (
        f"Fecha no encontrada en: {recuerdos[0]}"
    )
