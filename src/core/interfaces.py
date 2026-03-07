from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional, List
from pydantic import BaseModel
from src.data import schemas

class IDataRepository(ABC):
    @abstractmethod
    def read_data(self, filename: str, model: Type[BaseModel]) -> BaseModel:
        pass

    @abstractmethod
    async def async_read_data(self, filename: str, model: Type[BaseModel]) -> BaseModel:
        pass

    @abstractmethod
    def save_data(self, filename: str, data: BaseModel):
        pass

    @abstractmethod
    async def async_save_data(self, filename: str, data: BaseModel):
        pass
        
    @abstractmethod
    async def async_read_bitacora_summary(self) -> schemas.BitacoraSummary:
        pass

class IVectorRepository(ABC):
    @abstractmethod
    def buscar_contexto(self, query: str, n_results: int = 3) -> str:
        pass
        
    @abstractmethod
    def indexar_documento(self, doc_id: str, texto: str, metadata: Optional[Dict[str, Any]] = None):
        pass

class IToolsRepository(ABC):
    @abstractmethod
    def ejecutar_herramienta(self, nombre_tool: str, params: Dict[str, Any]) -> str:
        pass

    @abstractmethod
    async def async_ejecutar_memoria(self, datos: Dict[str, Any]) -> str:
        pass
