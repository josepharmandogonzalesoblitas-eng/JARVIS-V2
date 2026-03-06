import os
import logging
import chromadb
from datetime import datetime

logger = logging.getLogger("vector_db")

class GestorVectorial:
    """
    Gestor de Memoria a Largo Plazo usando ChromaDB.
    Permite a la IA guardar y recuperar recuerdos de forma semántica.
    """
    def __init__(self, persist_directory: str = "MEMORIA/vector_db"):
        self.persist_directory = persist_directory
        os.makedirs(persist_directory, exist_ok=True)
        
        try:
            self.client = chromadb.PersistentClient(path=self.persist_directory)
            self.collection = self.client.get_or_create_collection(
                name="recuerdos_jarvis",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("ChromaDB inicializado correctamente.")
        except Exception as e:
            logger.error(f"Error inicializando ChromaDB: {e}")
            self.collection = None

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
            
        try:
            # Si la colección está vacía, evitamos el error
            if self.collection.count() == 0:
                return "Aún no hay recuerdos a largo plazo."
                
            resultados = self.collection.query(
                query_texts=[query],
                n_results=min(n_results, self.collection.count())
            )
            
            if not resultados['documents'] or not resultados['documents'][0]:
                return "No se encontraron recuerdos relevantes."
                
            # Formatear los documentos encontrados
            docs = resultados['documents'][0]
            metas = resultados['metadatas'][0]
            
            memoria_str = "--- RECUERDOS RELEVANTES (LARGO PLAZO) ---\n"
            for doc, meta in zip(docs, metas):
                fecha = meta.get("fecha", "").split("T")[0]
                memoria_str += f"- [{fecha}]: {doc}\n"
                
            return memoria_str
            
        except Exception as e:
            logger.error(f"Error buscando en memoria vectorial: {e}")
            return ""

# Instancia global para ser usada por los demás módulos
vector_db = GestorVectorial()
