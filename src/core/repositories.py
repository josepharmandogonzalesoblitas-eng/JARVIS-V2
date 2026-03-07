import os
import asyncio
import logging
import chromadb
from datetime import datetime
from typing import Dict, Any, Type, Optional

from pydantic import BaseModel
from src.core.interfaces import IDataRepository, IVectorRepository, IToolsRepository
from src.data import schemas
from src.data import db_handler
from src.data.vector_db import GoogleGenAIEmbeddingFunction
from src.TOOLS.tool_system import ejecutar_herramienta_sistema
from src.TOOLS.tool_memory import async_ejecutar_memoria

logger = logging.getLogger("repositories")


class JSONDataRepository(IDataRepository):
    def read_data(self, filename: str, model: Type[BaseModel]) -> BaseModel:
        return db_handler.read_data(filename, model)

    async def async_read_data(self, filename: str, model: Type[BaseModel]) -> BaseModel:
        return await db_handler.async_read_data(filename, model)

    def save_data(self, filename: str, data: BaseModel):
        db_handler.save_data(filename, data)

    async def async_save_data(self, filename: str, data: BaseModel):
        await db_handler.async_save_data(filename, data)
        
    async def async_read_bitacora_summary(self) -> schemas.BitacoraSummary:
        return await db_handler.async_read_bitacora_summary()


class ChromaVectorRepository(IVectorRepository):
    """
    Repositorio vectorial auto-contenido usando ChromaDB.
    
    CORRECCIÓN ARQUITECTÓNICA: Esta clase ya no delega a la instancia global
    `vector_db`. Tiene su propio cliente y colección ChromaDB, lo que permite:
    - Inyección de dependencias real (tests pueden parchear __init__ con aislamiento total)
    - MemoryManager escribe en la MISMA colección que el repositorio lee
    - Sin efectos secundarios entre tests
    """

    def __init__(self):
        self.persist_directory = "MEMORIA/vector_db"
        os.makedirs(self.persist_directory, exist_ok=True)
        self._lock = asyncio.Lock()
        self.collection = None
        self.client = None

        try:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY no encontrado para ChromaVectorRepository.")

            embedding_fn = GoogleGenAIEmbeddingFunction(api_key=api_key)
            self.client = chromadb.PersistentClient(path=self.persist_directory)
            self.collection = self.client.get_or_create_collection(
                name="recuerdos_jarvis",
                embedding_function=embedding_fn,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("ChromaVectorRepository inicializado correctamente.")
        except Exception as e:
            logger.error(f"Error inicializando ChromaVectorRepository: {e}")
            self.collection = None

    # ------------------------------------------------------------------
    # Métodos de LECTURA (IVectorRepository)
    # ------------------------------------------------------------------

    def buscar_recuerdos_relevantes(self, query: str, n_results: int = 3) -> list:
        """Busca recuerdos relevantes usando self.collection (no global)."""
        if not self.collection:
            return []
        try:
            count = self.collection.count()
            if count == 0:
                return []
            resultados = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, count)
            )
            if not resultados['documents'] or not resultados['documents'][0]:
                return []
            return resultados['documents'][0]
        except Exception as e:
            logger.error(f"FAIL-SAFE: Error buscando en ChromaVectorRepository: {e}")
            return []

    def buscar_contexto(self, query: str, n_results: int = 3) -> str:
        """Retorna string formateado con los recuerdos más relevantes."""
        docs = self.buscar_recuerdos_relevantes(query, n_results)
        if not docs:
            return "No se encontraron recuerdos relevantes."
        memoria_str = "--- RECUERDOS RELEVANTES (LARGO PLAZO) ---\n"
        for doc in docs:
            memoria_str += f"- {doc}\n"
        return memoria_str

    def indexar_documento(self, doc_id: str, texto: str, metadata: Optional[Dict[str, Any]] = None):
        """Indexa un documento con ID personalizado."""
        if not self.collection:
            return
        try:
            self.collection.add(
                documents=[texto],
                ids=[doc_id],
                metadatas=[metadata or {}]
            )
        except Exception as e:
            logger.error(f"Error indexando documento en ChromaVectorRepository: {e}")

    async def async_buscar_recuerdos_relevantes(self, query: str, n_results: int = 3) -> list:
        """Versión asíncrona de buscar_recuerdos_relevantes."""
        async with self._lock:
            return await asyncio.to_thread(self.buscar_recuerdos_relevantes, query, n_results)

    # ------------------------------------------------------------------
    # Método de ESCRITURA (nuevo — requerido por MemoryManager)
    # ------------------------------------------------------------------

    async def async_agregar_recuerdo(self, texto: str, tipo: str = "general") -> str:
        """
        Agrega un recuerdo a largo plazo de forma asíncrona.
        Incluye chequeo de idempotencia para evitar duplicados.
        """
        if not self.collection:
            return "Error: Base de datos vectorial no disponible."

        # Chequeo de idempotencia
        try:
            resultados = await asyncio.to_thread(
                self.collection.query,
                query_texts=[texto],
                n_results=1,
                include=["distances"]
            )
            if (resultados and resultados['distances'] and
                    resultados['distances'][0] and
                    resultados['distances'][0][0] < 0.05):
                logger.warning(f"IDEMPOTENCIA: Recuerdo similar ya existe. Omitiendo.")
                return "Este recuerdo ya está registrado."
        except Exception as e:
            # No bloqueamos la operación si la verificación falla
            logger.error(f"Error en chequeo de idempotencia: {e}")

        async with self._lock:
            return await asyncio.to_thread(self._agregar_recuerdo_sync, texto, tipo)

    def _agregar_recuerdo_sync(self, texto: str, tipo: str) -> str:
        """Operación síncrona de escritura en ChromaDB."""
        if not self.collection:
            return "Error: Base de datos vectorial no disponible."
        try:
            doc_id = f"mem_{int(datetime.now().timestamp() * 1000)}"
            self.collection.add(
                documents=[texto],
                metadatas=[{"fecha": datetime.now().isoformat(), "tipo": tipo}],
                ids=[doc_id]
            )
            logger.info(f"Recuerdo guardado: {doc_id}")
            return "Recuerdo guardado exitosamente a largo plazo."
        except Exception as e:
            logger.error(f"Error al guardar recuerdo: {e}")
            return f"Error al guardar recuerdo: {str(e)}"


class DefaultToolsRepository(IToolsRepository):
    def ejecutar_herramienta(self, nombre_tool: str, params: Dict[str, Any]) -> str:
        return ejecutar_herramienta_sistema(nombre_tool, params)

    async def async_ejecutar_memoria(self, datos: Dict[str, Any]) -> str:
        return await async_ejecutar_memoria(datos)
