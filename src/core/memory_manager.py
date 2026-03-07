import logging
from typing import Dict, Any, Optional, TYPE_CHECKING
from src.data import db_handler, schemas
from datetime import datetime

if TYPE_CHECKING:
    from src.core.interfaces import IVectorRepository

logger = logging.getLogger("memory_manager")


class MemoryManager:
    """
    Gestiona toda la lógica de lectura y escritura en memoria.
    
    CORRECCIÓN ARQUITECTÓNICA: acepta un IVectorRepository inyectado desde
    el Orquestador, de modo que las operaciones vectoriales van a la MISMA
    colección que usa ChromaVectorRepository (y que los tests parchean).
    Si no se inyecta ningún repo, usa el global como fallback.
    """

    def __init__(self, vector_repo: Optional["IVectorRepository"] = None):
        self.vector_repo = vector_repo

    async def guardar_dato_personal(self, nombre: str, valor: Any) -> str:
        """Guarda datos personales en persona.json"""
        try:
            persona = await db_handler.async_read_data("persona.json", schemas.Persona)
            setattr(persona, nombre, valor)
            await db_handler.async_save_data("persona.json", persona)
            return f"Perfil actualizado: {nombre} = {valor}"
        except Exception as e:
            logger.error(f"Error guardando dato personal: {e}")
            return f"Error al guardar: {str(e)}"

    async def guardar_recordatorio(self, descripcion: str, contexto: str = "general") -> str:
        """Guarda un recordatorio a corto plazo"""
        try:
            contexto_obj = await db_handler.async_read_data("contexto.json", schemas.GestorContexto)
            recordatorio = schemas.Recordatorio(
                descripcion=descripcion,
                contexto_asociado=contexto
            )
            contexto_obj.recordatorios_pendientes.append(recordatorio)
            await db_handler.async_save_data("contexto.json", contexto_obj)
            return f"Recordatorio guardado: {descripcion}"
        except Exception as e:
            logger.error(f"Error guardando recordatorio: {e}")
            return f"Error al guardar: {str(e)}"

    async def guardar_recuerdo_largo_plazo(self, texto: str, tipo: str = "general") -> str:
        """
        Guarda un recuerdo en la memoria vectorial.
        Usa el vector_repo inyectado si está disponible; de lo contrario,
        cae al global como fallback (para no romper código existente).
        """
        try:
            if self.vector_repo is not None:
                return await self.vector_repo.async_agregar_recuerdo(texto, tipo)
            # Fallback al singleton global
            from src.data.vector_db import vector_db
            return await vector_db.async_agregar_recuerdo(texto, tipo)
        except Exception as e:
            logger.error(f"Error guardando recuerdo a largo plazo: {e}")
            return f"Error al guardar: {str(e)}"

    async def procesar_intencion_memoria(self, intencion: str, datos: Dict[str, Any]) -> str:
        """Procesa una intención de memoria devuelta por Gemini"""
        try:
            if intencion == "actualizar_nombre":
                return await self.guardar_dato_personal("nombre", datos.get("valor"))
            elif intencion == "actualizar_edad":
                return await self.guardar_dato_personal("edad", int(datos.get("valor")))
            elif intencion == "actualizar_profesion":
                return await self.guardar_dato_personal("profesion", datos.get("valor"))
            elif intencion == "nuevo_recordatorio":
                return await self.guardar_recordatorio(
                    datos.get("descripcion"),
                    datos.get("contexto", "general")
                )
            elif intencion == "nuevo_recuerdo_largo_plazo":
                return await self.guardar_recuerdo_largo_plazo(
                    datos.get("texto"),
                    datos.get("tipo", "general")
                )
            else:
                return f"Intención no reconocida: {intencion}"
        except Exception as e:
            logger.error(f"Error procesando intención: {e}")
            return f"Error: {str(e)}"

    async def obtener_contexto_memoria(self) -> Dict[str, Any]:
        """Obtiene el estado actual de toda la memoria"""
        try:
            persona = await db_handler.async_read_data("persona.json", schemas.Persona)
            contexto = await db_handler.async_read_data("contexto.json", schemas.GestorContexto)
            entorno = await db_handler.async_read_data("entorno.json", schemas.Entorno)
            
            return {
                "nombre": persona.nombre,
                "profesion": persona.profesion,
                "recordatorios": [
                    r.descripcion for r in contexto.recordatorios_pendientes 
                    if not r.completado
                ],
                "zona_horaria": entorno.zona_horaria
            }
        except Exception as e:
            logger.error(f"Error obteniendo contexto: {e}")
            return {}
