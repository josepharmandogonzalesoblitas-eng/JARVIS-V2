from typing import Dict, Any, Type, Optional
from pydantic import BaseModel
from src.core.interfaces import IDataRepository, IVectorRepository, IToolsRepository
from src.data import schemas
from src.data import db_handler
from src.data.vector_db import vector_db
from src.TOOLS.tool_system import ejecutar_herramienta_sistema
from src.TOOLS.tool_memory import async_ejecutar_memoria

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
    def buscar_contexto(self, query: str, n_results: int = 3) -> str:
        return vector_db.buscar_contexto(query, n_results)
        
    def indexar_documento(self, doc_id: str, texto: str, metadata: Optional[Dict[str, Any]] = None):
        vector_db.indexar_documento(doc_id, texto, metadata)

class DefaultToolsRepository(IToolsRepository):
    def ejecutar_herramienta(self, nombre_tool: str, params: Dict[str, Any]) -> str:
        return ejecutar_herramienta_sistema(nombre_tool, params)

    async def async_ejecutar_memoria(self, datos: Dict[str, Any]) -> str:
        return await async_ejecutar_memoria(datos)
