import os
import logging
import asyncio
import chromadb
from datetime import datetime

logger = logging.getLogger("vector_db")

from chromadb.utils import embedding_functions

class GestorVectorial:
    """
    Gestor de Memoria a Largo Plazo usando ChromaDB.
    Permite a la IA guardar y recuperar recuerdos de forma semántica.
    OPTIMIZACIÓN BIG-O RAM: Usa Embeddings remotos (Google Gemini) para no
    cargar el modelo de 80MB (SentenceTransformers) en la RAM del VPS (1GB max).
    """
    def __init__(self, persist_directory: str = "MEMORIA/vector_db"):
        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)
        self._lock = asyncio.Lock()
        
        try:
            # Recuperamos API KEY globalmente o lanzamos error (Poka-Yoke)
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("Falta GEMINI_API_KEY para Embeddings Vectoriales.")

            # Inicialización Lazy Loading (se retrasa hasta que se pida si quisiéramos)
            # Usamos Google Generative AI Embeddings para delegar cómputo
            google_ef = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
                api_key=api_key,
                model_name="models/embedding-001"
            )

            self.client = chromadb.PersistentClient(path=self.persist_directory)
            
            # Recreamos/Obtenemos colección inyectando el embedding remote
            self.collection = self.client.get_or_create_collection(
                name="recuerdos_jarvis",
                embedding_function=google_ef,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("ChromaDB inicializado (Google Embeddings O(1) RAM).")
        except Exception as e:
            logger.error(f"Error inicializando ChromaDB: {e}")
            self.collection = None

    async def async_agregar_recuerdo(self, texto_recuerdo: str, tipo: str = "general") -> str:
        """Versión asíncrona y segura para agregar un recuerdo."""
        if not self.collection:
            return "Error: Base de datos vectorial no disponible."
        
        # IDEMPOTENCIA: Verificar si un recuerdo muy similar ya existe.
        # Esto es costoso, así que lo hacemos de forma simple: buscar primero.
        # Una mejor implementación podría usar hashes o verificar por un ID de origen.
        try:
            resultados = await asyncio.to_thread(
                self.collection.query,
                query_texts=[texto_recuerdo],
                n_results=1,
                include=["distances"]
            )
            # Si encuentra algo muy cercano (distancia coseno baja), no lo inserta.
            if resultados and resultados['distances'] and resultados['distances'][0] and resultados['distances'][0][0] < 0.05:
                logger.warning(f"IDEMPOTENCIA: Recuerdo duplicado detectado. No se guardará: '{texto_recuerdo[:50]}...'")
                return "Este recuerdo ya está registrado."
        except Exception as e:
            logger.error(f"Error en chequeo de idempotencia de ChromaDB: {e}")
            # No bloqueamos la operación si la verificación falla, solo logueamos.

        async with self._lock:
            return await asyncio.to_thread(self.agregar_recuerdo, texto_recuerdo, tipo)

    def agregar_recuerdo(self, texto_recuerdo: str, tipo: str = "general") -> str:
        """
        Agrega un nuevo recuerdo a la base de datos vectorial.
        """
        if not self.collection:
            return "Error: Base de datos vectorial no disponible."
            
        try:
            # Usamos un timestamp como ID único
            doc_id = f"mem_{int(datetime.now().timestamp())}"
            
            self.collection.add(
                documents=[texto_recuerdo],
                metadatas=[{"fecha": datetime.now().isoformat(), "tipo": tipo}],
                ids=[doc_id]
            )
            logger.info(f"Recuerdo guardado: {doc_id}")
            return f"Recuerdo guardado exitosamente a largo plazo."
        except Exception as e:
            logger.error(f"Error al guardar recuerdo: {e}")
            return f"Error al guardar recuerdo: {str(e)}"

    def buscar_contexto(self, query: str, n_results: int = 3) -> str:
        """
        Busca recuerdos relevantes basados en la consulta actual.
        Retorna un string formateado con los recuerdos encontrados.
        """
        if not self.collection:
            return ""

        # GRACEFUL DEGRADATION: Si ChromaDB falla, el bot sigue funcionando.
        try:
            if self.collection.count() == 0:
                return "Aún no hay recuerdos a largo plazo."
                
            resultados = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, self.collection.count())
            )
            
            if not resultados['documents'] or not resultados['documents'][0]:
                return "No se encontraron recuerdos relevantes."
                
            docs = resultados['documents'][0]
            metas = resultados['metadatas'][0]
            
            memoria_str = "--- RECUERDOS RELEVANTES (LARGO PLAZO) ---\n"
            for doc, meta in zip(docs, metas):
                fecha = meta.get("fecha", "N/A").split("T")[0]
                memoria_str += f"- [{fecha}]: {doc}\n"
                
            return memoria_str
            
        except Exception as e:
            logger.error(f"FAIL-SAFE: Error buscando en memoria vectorial: {e}")
            return "No se pudo acceder a la memoria a largo plazo en este momento."

# Instancia global para ser usada por los demás módulos
vector_db = GestorVectorial()
