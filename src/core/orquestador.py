import logging
import json
import asyncio
from datetime import datetime
from typing import Dict, Any

# --- MODULARIDAD: Inversión de Dependencias ---
from src.core.cerebro import CerebroDigital, PensamientoJarvis
from src.core.memory_manager import MemoryManager
from src.data import schemas
from src.core.interfaces import IDataRepository, IVectorRepository, IToolsRepository

# --- TRAZABILIDAD ---
logger = logging.getLogger("orquestador")

class Orquestador:
    """
    Controlador Central (MVC Pattern).
    Responsabilidad: Coordinar el flujo de datos entre IO, Lógica y Persistencia.
    Principios: Fail-Safe, Atomicidad, Trazabilidad, SOLID (Inyección de Dependencias).
    """

    def __init__(self, data_repo: IDataRepository, vector_repo: IVectorRepository, tools_repo: IToolsRepository):
        # Inyección de Dependencias Explícita
        self.data_repo = data_repo
        self.vector_repo = vector_repo
        self.tools_repo = tools_repo
        self.cerebro = CerebroDigital()
        # Pasamos vector_repo al MemoryManager para que escriba en la MISMA
        # colección que el repositorio vectorial inyectado (corrección DI).
        self.memory_manager = MemoryManager(vector_repo=self.vector_repo)

    async def procesar_mensaje(self, usuario_id: str, texto_limpio: str, audio_path: str = None) -> str:
        """
        Flujo principal de ejecución (Pipeline) ASÍNCRONO.
        Recibe texto ya sanitizado desde la interfaz.
        
        Args:
            usuario_id (str): ID del remitente autorizado.
            texto_limpio (str): Mensaje de texto sin caracteres maliciosos ni inyecciones.
            audio_path (str, optional): Ruta temporal del archivo de audio si aplica. Defaults to None.
            
        Returns:
            str: La respuesta final a enviar al usuario en Telegram.
        """
        try:
            if not texto_limpio and not audio_path:
                return "..." # Ignorar mensajes vacíos

            # 1. CARGA DE CONTEXTO (RAG) - ASÍNCRONO
            contexto_str = await self._construir_contexto_async(texto_limpio)

            # 2. INFERENCIA (El Cerebro Piensa)
            pensamiento: PensamientoJarvis = await self.cerebro.pensar(texto_limpio, contexto_str, audio_path)

            # 3. PROCESAMIENTO DE MEMORIA SI APLICA
            if pensamiento.memoria_intencion:
                await self.memory_manager.procesar_intencion_memoria(
                    pensamiento.memoria_intencion,
                    pensamiento.memoria_datos or {}
                )

            # 4. EJECUCIÓN DE INTENCIÓN (Router Lógico)
            respuesta_final = pensamiento.respuesta_usuario

            # FAIL-SAFE: Si la IA falló, no ejecutamos nada más.
            if pensamiento.intencion == "fallback_error":
                return respuesta_final

            elif pensamiento.intencion == "comando":
                if pensamiento.herramienta_sugerida and pensamiento.herramienta_sugerida != "None":
                    resultado_tool = self._ejecutar_herramienta(pensamiento.herramienta_sugerida, pensamiento.datos_extra)
                    respuesta_final += f"\n\n[Sistema]: {resultado_tool}"

            # 5. RETORNO (Feedback)
            return respuesta_final

        except Exception as e:
            # GRACEFUL DEGRADATION
            # Si todo falla, el usuario recibe un mensaje digno, no un stack trace.
            logger.error(f"Error crítico en orquestador: {e}", exc_info=True)
            return f"⚠️ Error del Sistema: {str(e)}. Mis protocolos de recuperación están activos."

    async def _construir_contexto_async(self, texto_usuario: str) -> str:
        """
        Recopila de forma concurrente el contexto necesario para el prompt de la IA.
        
        Extrae datos de la persona, proyectos activos, resumen de la bitácora
        y realiza una búsqueda semántica en la base de datos vectorial.
        
        Args:
            texto_usuario (str): El mensaje ingresado por el usuario, usado para
                                la búsqueda en la base vectorial.
                                
        Returns:
            str: Un string formateado que contiene todo el contexto comprimido,
                 listo para ser inyectado en el LLM. En caso de error, devuelve
                 un mensaje de fallback temporal.
        """
        try:
            import pytz
            # Lecturas de DB en paralelo para optimizar
            persona_task = self.data_repo.async_read_data("persona.json", schemas.Persona)
            proyectos_task = self.data_repo.async_read_data("proyectos.json", schemas.GestorProyectos)
            bitacora_summary_task = self.data_repo.async_read_bitacora_summary()
            contexto_task = self.data_repo.async_read_data("contexto.json", schemas.GestorContexto)
            entorno_task = self.data_repo.async_read_data("entorno.json", schemas.Entorno)
            
            persona, proyectos, bitacora_summary, contexto, entorno = await asyncio.gather(
                persona_task, proyectos_task, bitacora_summary_task, contexto_task, entorno_task
            )
            
            # --- CONTEXTO TEMPORAL (Timezone-Aware) ---
            try:
                user_tz = pytz.timezone(entorno.zona_horaria)
            except pytz.UnknownTimeZoneError:
                user_tz = pytz.timezone("America/Lima") # Fallback
            
            hora_local_usuario_str = f"La fecha y hora actual para el usuario es: {datetime.now(user_tz).strftime('%Y-%m-%d %H:%M:%S')}."
            
            # Búsqueda vectorial
            memoria_vectorial = await asyncio.to_thread(
                self.vector_repo.buscar_contexto, texto_usuario, 3
            )
            
            bitacora_hoy_str = bitacora_summary.dia_actual.model_dump_json(indent=2) if bitacora_summary.dia_actual else "No hay registro de hoy."
            tendencia = bitacora_summary.tendencia_energia
            
            # --- COMPRESIÓN DE CONTEXTO (Proyectos) ---
            resumen_proyectos = []
            for nombre, p in proyectos.proyectos_activos.items():
                tareas_pendientes = len([t for t in p.tareas_pendientes if t.estado != 'completado'])
                resumen_proyectos.append(f"- {nombre}: {p.estado_actual} ({tareas_pendientes} tareas pendientes)")
            
            str_proyectos = "\n            ".join(resumen_proyectos) if resumen_proyectos else "No hay proyectos activos."

            # Formateamos bonito para que Gemini entienda mejor
            return f"""
            --- CONTEXTO TEMPORAL Y DE ENTORNO (NO MOSTRAR AL USUARIO) ---
            {hora_local_usuario_str}
            
            --- PERFIL USUARIO ---
            {persona.model_dump_json(indent=2)}
            
            --- RESUMEN DE PROYECTOS ACTIVOS ---
            {str_proyectos}
            (Para ver detalles completos, usa intención 'actualizar_memoria', archivo 'proyectos', accion 'consultar_proyecto' con {{"nombre": "Nombre del proyecto"}})
            
            --- ESTADO DE HOY ({datetime.now().strftime('%Y-%m-%d')}) ---
            {bitacora_hoy_str}
            Tendencia Reciente: {tendencia}
            
            --- CONTEXTO Y RECORDATORIOS (MÓVIL) ---
            {contexto.model_dump_json(indent=2)}
            
            {memoria_vectorial}
            """
        except Exception as e:
            logger.warning(f"No se pudo cargar contexto completo: {e}")
            return "Contexto no disponible temporalmente."

    async def _ejecutar_memoria_async(self, datos: Dict[str, Any]) -> str:
        """
        Maneja la persistencia de datos de forma asíncrona usando el repositorio inyectado.
        
        Args:
            datos (Dict[str, Any]): Diccionario con los detalles de la operación
                                    a realizar en memoria (ej. actualizar perfil, bitácora).
                                    
        Returns:
            str: Resultado de la operación de memoria que se devolverá o mostrará al usuario.
        """
        return await self.tools_repo.async_ejecutar_memoria(datos)

    def _ejecutar_herramienta(self, nombre_tool: str, params: Dict[str, Any]) -> str:
        """
        Router para la ejecución de scripts/tools locales usando el repositorio inyectado.
        
        Args:
            nombre_tool (str): Nombre de la herramienta a ejecutar (ej. 'buscar_web', 'google_calendar').
            params (Dict[str, Any]): Parámetros requeridos por la herramienta extraídos por el LLM.
            
        Returns:
            str: Feedback del sistema tras la ejecución de la herramienta.
        """
        return self.tools_repo.ejecutar_herramienta(nombre_tool, params)
