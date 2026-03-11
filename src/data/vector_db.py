import os
import logging
import asyncio
import chromadb
from datetime import datetime
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

logger = logging.getLogger("vector_db")


class GoogleGenAIEmbeddingFunction(EmbeddingFunction[Documents]):
    """
    Función de embedding personalizada usando la nueva SDK google.genai.
    
    Hereda de chromadb.EmbeddingFunction[Documents] para:
    - Obtener embed_query() heredado (requerido por chromadb 1.5+)
    - Validación y normalización automática de embeddings vía __init_subclass__
    - Reemplazar la deprecada GoogleGenerativeAiEmbeddingFunction de chromadb
      (que usaba google.generativeai, la SDK antigua)
    """
    def __init__(self, api_key: str, model_name: str = "models/gemini-embedding-001"):
        from google import genai
        self._client = genai.Client(api_key=api_key)
        self._model_name = model_name

    @staticmethod
    def name() -> str:
        return "google_genai_embedding_fn"

    def get_config(self) -> dict:
        return {"model_name": self._model_name}

    @staticmethod
    def build_from_config(config: dict) -> "GoogleGenAIEmbeddingFunction":
        import os
        return GoogleGenAIEmbeddingFunction(
            api_key=os.getenv("GEMINI_API_KEY", ""),
            model_name=config.get("model_name", "models/gemini-embedding-001")
        )

    def __call__(self, input: Documents) -> Embeddings:
        """
        Genera embeddings para una lista de textos.
        Args:
            input: lista de strings (Documents)
        Returns:
            Lista de vectores (Embeddings)
        """
        try:
            response = self._client.models.embed_content(
                model=self._model_name,
                contents=input
            )
            return [list(e.values) for e in response.embeddings]
        except Exception as e:
            logger.error(f"Error generando embeddings con google.genai: {e}")
            raise


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
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("Falta GEMINI_API_KEY para Embeddings Vectoriales.")

            # Usamos la nueva SDK google.genai para embeddings
            embedding_fn = GoogleGenAIEmbeddingFunction(api_key=api_key)

            self.client = chromadb.PersistentClient(path=self.persist_directory)
            
            self.collection = self.client.get_or_create_collection(
                name="recuerdos_jarvis",
                embedding_function=embedding_fn,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("ChromaDB inicializado (Google Embeddings nueva SDK, O(1) RAM).")
        except Exception as e:
            logger.error(f"Error inicializando ChromaDB: {e}")
            self.collection = None

    async def async_agregar_recuerdo(self, texto_recuerdo: str, tipo: str = "general") -> str:
        """Versión asíncrona y segura para agregar un recuerdo."""
        if not self.collection:
            return "Error: Base de datos vectorial no disponible."
        
        # IDEMPOTENCIA: Verificar si un recuerdo muy similar ya existe.
        try:
            resultados = await asyncio.to_thread(
                self.collection.query,
                query_texts=[texto_recuerdo],
                n_results=1,
                include=["distances"]
            )
            if resultados and resultados['distances'] and resultados['distances'][0] and resultados['distances'][0][0] < 0.05:
                logger.warning(f"IDEMPOTENCIA: Recuerdo duplicado detectado. No se guardará: '{texto_recuerdo[:50]}...'")
                return "Este recuerdo ya está registrado."
        except Exception as e:
            logger.error(f"Error en chequeo de idempotencia de ChromaDB: {e}")

        async with self._lock:
            return await asyncio.to_thread(self.agregar_recuerdo, texto_recuerdo, tipo)

    def agregar_recuerdo(self, texto_recuerdo: str, tipo: str = "general") -> str:
        """Agrega un nuevo recuerdo a la base de datos vectorial."""
        if not self.collection:
            return "Error: Base de datos vectorial no disponible."
            
        try:
            doc_id = f"mem_{int(datetime.now().timestamp() * 1000)}"
            
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

    def buscar_recuerdos_relevantes(self, query: str, n_results: int = 3) -> list:
        """Busca recuerdos relevantes y devuelve los documentos."""
        if not self.collection:
            return []

        try:
            if self.collection.count() == 0:
                return []
                
            resultados = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, self.collection.count())
            )
            
            if not resultados['documents'] or not resultados['documents'][0]:
                return []
                
            return resultados['documents'][0]
            
        except Exception as e:
            logger.error(f"FAIL-SAFE: Error buscando en memoria vectorial: {e}")
            return []

    async def async_buscar_recuerdos_relevantes(self, query: str, n_results: int = 3) -> list:
        """Versión asíncrona para buscar recuerdos relevantes."""
        async with self._lock:
            return await asyncio.to_thread(self.buscar_recuerdos_relevantes, query, n_results)

    def buscar_contexto(self, query: str, n_results: int = 3) -> str:
        """
        Busca recuerdos relevantes basados en la consulta actual.
        Retorna un string formateado con los recuerdos encontrados.
        """
        docs = self.buscar_recuerdos_relevantes(query, n_results)
        if not docs:
            return "No se encontraron recuerdos relevantes."

        memoria_str = "--- RECUERDOS RELEVANTES (LARGO PLAZO) ---\n"
        for doc in docs:
            memoria_str += f"- {doc}\n"
            
        return memoria_str

    def indexar_documento(self, doc_id: str, texto: str, metadata=None):
        """Indexa un documento con un ID personalizado."""
        if not self.collection:
            return
        try:
            self.collection.add(
                documents=[texto],
                ids=[doc_id],
                metadatas=[metadata or {}]
            )
        except Exception as e:
            logger.error(f"Error indexando documento: {e}")


# Instancia global — usada como fallback si no se inyecta vector_repo
vector_db = GestorVectorial()
