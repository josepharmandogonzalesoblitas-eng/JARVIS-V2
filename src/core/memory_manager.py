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
        """Guarda un recordatorio a corto plazo.

        Idempotencia: no crea duplicados si el mismo recordatorio pendiente ya existe.
        """
        try:
            if not descripcion or not str(descripcion).strip():
                return "Error: descripción del recordatorio vacía."

            descripcion = str(descripcion).strip()
            contexto_obj = await db_handler.async_read_data("contexto.json", schemas.GestorContexto)

            # Idempotencia: evitar duplicados de recordatorios pendientes (misma descripción)
            pendientes_existentes = {
                r.descripcion.strip().lower()
                for r in contexto_obj.recordatorios_pendientes
                if not r.completado
            }
            if descripcion.lower() in pendientes_existentes:
                return f"Recordatorio ya registrado (sin duplicar): {descripcion}"

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

    async def actualizar_preferencia(self, clave: str, valor: str) -> str:
        """Guarda una preferencia del usuario en persona.json bajo el dict 'preferencias'."""
        try:
            persona = await db_handler.async_read_data("persona.json", schemas.Persona)
            persona.preferencias[clave] = valor
            await db_handler.async_save_data("persona.json", persona)
            return f"Preferencia guardada: {clave} = {valor}"
        except Exception as e:
            logger.error(f"Error guardando preferencia: {e}")
            return f"Error al guardar preferencia: {str(e)}"

    async def actualizar_rutina(self, descripcion: str) -> str:
        """Añade o actualiza una rutina/hábito del usuario en contexto.json."""
        try:
            contexto_obj = await db_handler.async_read_data("contexto.json", schemas.GestorContexto)
            if descripcion not in contexto_obj.rutinas_diarias:
                contexto_obj.rutinas_diarias.append(descripcion)
                await db_handler.async_save_data("contexto.json", contexto_obj)
            return f"Rutina registrada: {descripcion}"
        except Exception as e:
            logger.error(f"Error guardando rutina: {e}")
            return f"Error al guardar rutina: {str(e)}"

    async def actualizar_persona_clave(self, nombre: str, descripcion: str) -> str:
        """Guarda una persona importante en entorno.json bajo 'personas_clave'."""
        try:
            entorno = await db_handler.async_read_data("entorno.json", schemas.Entorno)
            entorno.personas_clave[nombre] = descripcion
            await db_handler.async_save_data("entorno.json", entorno)
            return f"Persona clave registrada: {nombre} = {descripcion}"
        except Exception as e:
            logger.error(f"Error guardando persona clave: {e}")
            return f"Error al guardar persona clave: {str(e)}"

    async def actualizar_estado_animo(self, estado_animo: str, nivel_energia: int) -> str:
        """Actualiza el estado de ánimo y energía del día en bitacora.json."""
        try:
            bitacora = await db_handler.async_read_data("bitacora.json", schemas.GestorBitacora)
            hoy = datetime.now().strftime("%Y-%m-%d")

            if bitacora.dia_actual and bitacora.dia_actual.fecha == hoy:
                # Actualizar el día existente
                bitacora.dia_actual.estado_animo = estado_animo
                if 1 <= nivel_energia <= 10:
                    bitacora.dia_actual.nivel_energia = nivel_energia
            else:
                # Crear entrada de hoy si no existe
                bitacora.dia_actual = schemas.RegistroDiario(
                    fecha=hoy,
                    nivel_energia=max(1, min(10, nivel_energia)),
                    estado_animo=estado_animo
                )

            await db_handler.async_save_data("bitacora.json", bitacora)
            return f"Estado de ánimo registrado: {estado_animo} (energía: {nivel_energia}/10)"
        except Exception as e:
            logger.error(f"Error guardando estado de ánimo: {e}")
            return f"Error al guardar estado de ánimo: {str(e)}"

    async def guardar_conversacion_profunda(
        self,
        resumen: str,
        tipo: str = "general",
        dias_followup: int = 14
    ) -> str:
        """
        Guarda una conversación importante con fecha de follow-up automático.
        JARVIS recordará esta conversación en N días para preguntar cómo resultó.
        """
        try:
            from src.data import schemas as sc
            from datetime import timedelta

            estado = await db_handler.async_read_data("estado_emocional.json", sc.EstadoEmocionalSistema)

            fecha_hoy = datetime.now().strftime("%Y-%m-%d")
            fecha_followup = (datetime.now() + timedelta(days=dias_followup)).strftime("%Y-%m-%d")

            nueva_conv = sc.ConversacionProfundaItem(
                resumen=resumen[:200],  # Limitar a 200 chars
                tipo=tipo,
                fecha=fecha_hoy,
                fecha_followup=fecha_followup,
                completado=False
            )
            estado.conversaciones_profundas.append(nueva_conv)

            # Mantener solo las últimas 20 conversaciones
            if len(estado.conversaciones_profundas) > 20:
                estado.conversaciones_profundas = estado.conversaciones_profundas[-20:]

            await db_handler.async_save_data("estado_emocional.json", estado)
            return f"Conversación guardada. Haré seguimiento el {fecha_followup}."
        except Exception as e:
            logger.error(f"Error guardando conversación profunda: {e}")
            return f"Error al guardar: {str(e)}"

    async def registrar_logro(self, descripcion: str, tipo: str = "personal") -> str:
        """Registra un logro del usuario en el estado emocional del sistema."""
        try:
            from src.data import schemas as sc
            estado = await db_handler.async_read_data("estado_emocional.json", sc.EstadoEmocionalSistema)
            estado.ultimo_logro_celebrado = f"{datetime.now().strftime('%Y-%m-%d')}: {descripcion[:100]}"
            await db_handler.async_save_data("estado_emocional.json", estado)
            # También guardar como recuerdo a largo plazo
            await self.guardar_recuerdo_largo_plazo(
                f"Logro del usuario: {descripcion}",
                tipo="logro"
            )
            return f"Logro registrado: {descripcion}"
        except Exception as e:
            logger.error(f"Error registrando logro: {e}")
            return f"Error: {str(e)}"

    async def procesar_intencion_memoria(self, intencion: str, datos: Dict[str, Any]) -> str:
        """Procesa una intención de memoria devuelta por Gemini"""
        try:
            if intencion == "actualizar_nombre":
                return await self.guardar_dato_personal("nombre", datos.get("valor"))
            elif intencion == "actualizar_edad":
                return await self.guardar_dato_personal("edad", int(datos.get("valor")))
            elif intencion == "actualizar_profesion":
                return await self.guardar_dato_personal("profesion", datos.get("valor"))
            elif intencion == "actualizar_preferencia":
                return await self.actualizar_preferencia(
                    datos.get("clave", "preferencia"),
                    datos.get("valor", "")
                )
            elif intencion == "actualizar_rutina":
                return await self.actualizar_rutina(datos.get("descripcion", ""))
            elif intencion == "actualizar_persona_clave":
                return await self.actualizar_persona_clave(
                    datos.get("nombre", ""),
                    datos.get("descripcion", "")
                )
            elif intencion == "actualizar_estado_animo":
                val_energia = datos.get("nivel_energia")
                # Type-Safety: el LLM puede devolver strings no numéricos ("desconocido", None, etc.)
                try:
                    energia = int(val_energia) if val_energia is not None else 5
                    energia = max(1, min(10, energia))  # clamp al rango válido [1-10]
                except (ValueError, TypeError):
                    energia = 5  # Graceful Degradation: valor neutro por defecto
                return await self.actualizar_estado_animo(
                    datos.get("estado_animo", "estable") or "estable",
                    energia
                )
            elif intencion == "nuevo_recordatorio":
                return await self.guardar_recordatorio(
                    datos.get("descripcion"),
                    datos.get("contexto") or "general"  # Handles explicit None from LLM
                )
            elif intencion == "nuevo_recuerdo_largo_plazo":
                return await self.guardar_recuerdo_largo_plazo(
                    datos.get("texto"),
                    datos.get("tipo", "general")
                )
            elif intencion == "guardar_conversacion_profunda":
                return await self.guardar_conversacion_profunda(
                    datos.get("resumen", ""),
                    datos.get("tipo", "general"),
                    int(datos.get("dias_followup", 14))
                )
            elif intencion == "registrar_logro":
                return await self.registrar_logro(
                    datos.get("descripcion", ""),
                    datos.get("tipo", "personal")
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
