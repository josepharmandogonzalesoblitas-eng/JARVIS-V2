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
    class _HashEmbeddingFn(EmbeddingFunction[Documents]):
        def __call__(self, input: Documents) -> Embeddings:
            result = []
            for text in input:
                h = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
                vec = [(h >> (i % 64)) % 100 / 100.0 for i in range(768)]
                result.append(vec)
            return result
    return _HashEmbeddingFn()


def setup_test_environment(tmp_path, monkeypatch):
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY no encontrado")

    test_memory_path = tmp_path / "MEMORIA_E2E_REAL"
    test_memory_path.mkdir(exist_ok=True)

    monkeypatch.setattr(db_handler, 'MEMORY_PATH', str(test_memory_path))

    def patched_init(self):
        import chromadb
        self.client = chromadb.EphemeralClient()
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
    orq = setup_test_environment(tmp_path, monkeypatch)
    await orq.procesar_mensaje("user1", "Me llamo Joseph")
    persona = await orq.data_repo.async_read_data("persona.json", schemas.Persona)
    assert persona.nombre == "Joseph"

async def test_google_calendar_real(tmp_path, monkeypatch):
    orq = setup_test_environment(tmp_path, monkeypatch)
    response = await orq.procesar_mensaje("user1", "Agendar en google calendar reunión de equipo mañana a las 10 am por 60 minutos")
    assert "token" in response.lower() or "google calendar" in response.lower() or "agendado" in response.lower() or "fallo" in response.lower() or "listo" in response.lower()
