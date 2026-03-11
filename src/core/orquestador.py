import logging
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

# --- MODULARIDAD: Inversión de Dependencias ---
from src.core.fsm.state_machine import FSMOrquestador
from src.core.memory_manager import MemoryManager
from src.core.emotion_engine import emotion_engine
from src.core.conversation_state import conversation_state_manager
from src.data import schemas
from src.core.interfaces import IDataRepository, IVectorRepository, IToolsRepository
from src.core.adaptive_cron import adaptive_cron

# --- TRAZABILIDAD ---
logger = logging.getLogger("orquestador")

# Marcador especial para archivos adjuntos generados por herramientas
ARCHIVO_ADJUNTO_PREFIX = "__ARCHIVO_ADJUNTO__:"

# Marcador para indicar al bot de Telegram que debe mostrar menú de herramientas
MENU_HERRAMIENTAS_MARKER = "__MOSTRAR_MENU_HERRAMIENTAS__:"

# Palabras clave que sugieren que el usuario quiere usar una herramienta
# pero la IA no fue capaz de identificar cuál
_PALABRAS_CLAVE_HERRAMIENTAS = [
    "agenda", "agend", "calendar", "evento", "cita", "reunión", "reunion",
    "tarea", "tasks", "lista", "pendiente",
    "recordatorio", "recuérdame", "recuerdame", "avísame", "avisame",
    "alarma", "timer", "minutos",
    "busca", "buscar", "buscarme", "investiga", "internet", "web",
    "clima", "tiempo", "lluvia", "temperatura",
    "gráfico", "grafico", "progreso", "resumen",
    "proyecto", "proyectos",
]


class Orquestador:
    """
    Controlador Central (MVC Pattern).
    Responsabilidad: Coordinar el flujo de datos entre IO, Lógica y Persistencia.
    Principios: Fail-Safe, Atomicidad, Trazabilidad, SOLID (Inyección de Dependencias).

    V2: Integra EmotionEngine y ConversationStateManager para inteligencia emocional.
    """

    def __init__(self, data_repo: IDataRepository, vector_repo: IVectorRepository, tools_repo: IToolsRepository):
        self.data_repo = data_repo
        self.vector_repo = vector_repo
        self.tools_repo = tools_repo
        self.memory_manager = MemoryManager(vector_repo=self.vector_repo)
        self.fsm = FSMOrquestador(tools_repo=self.tools_repo, memory_manager=self.memory_manager)

        # Buffer de conversación en memoria (short-term memory)
        self._historial_reciente: list = []
        
        # Trazabilidad / Observabilidad
        self.trace_log: list = []
        
        # Archivo adjunto pendiente de enviar (foto/gráfico generado por herramienta)
        self._pending_attachment: Optional[str] = None

    async def procesar_mensaje(
        self,
        usuario_id: str,
        texto_limpio: str,
        audio_path: str = None,
        image_path: str = None
    ) -> str:
        """
        Flujo principal de ejecución (Pipeline) ASÍNCRONO.
        """
        try:
            self.trace_log.clear()
            self._pending_attachment = None

            if not texto_limpio and not audio_path and not image_path:
                return "..."

            if conversation_state_manager.verificar_expiracion():
                logger.info(f"Modo {conversation_state_manager.modo.value} expirado automáticamente.")

            if (conversation_state_manager.sesion_terapeuta_activa and texto_limpio and usuario_id != "SISTEMA_CRON"):
                return await self._handle_terapeuta_session(texto_limpio)

            if conversation_state_manager.foco_completado():
                mins = conversation_state_manager.tiempo_en_foco()
                conversation_state_manager.desactivar_modo()
                return (
                    f"⏰ ¡Tiempo! Completaste {mins} minutos de trabajo profundo. "
                    f"¿Qué lograste en esta sesión? Cuéntame para registrarlo. 🎯"
                )

            analisis_emocional = await self._run_emotional_analysis(texto_limpio, usuario_id)
            if analisis_emocional.get("respuesta_inmediata"):
                return analisis_emocional["respuesta_inmediata"]

            contexto_str = await self._construir_contexto_async(texto_limpio or "")
            route_info = await self.fsm.step_1_route(texto_limpio or "", contexto_str)
            
            logger.debug(f"[DEBUG ROUTER]: {route_info}")

            resultado_tool, params_extra = await self._execute_tool_if_needed(route_info, texto_limpio or "", contexto_str, usuario_id)
            
            if route_info.get("memoria"):
                await self._process_memory_intent(route_info["memoria"], texto_limpio or "", contexto_str)

            respuesta_final = await self.fsm.step_4_synthesize(
                texto_limpio or "", contexto_str, tool_result=resultado_tool, audio=audio_path, image=image_path
            )

            respuesta_final = self._post_process_response(respuesta_final, route_info.get("herramienta"), params_extra, analisis_emocional, texto_limpio, usuario_id)

            self._actualizar_historial_reciente(texto_limpio, respuesta_final)

            if usuario_id != "SISTEMA_CRON":
                conversation_context = {
                    "texto_usuario": texto_limpio, "respuesta_jarvis": respuesta_final,
                    "intencion": route_info.get("intencion"), "herramienta": route_info.get("herramienta"),
                    "memoria": route_info.get("memoria"), "historial_reciente": self._historial_reciente
                }
                asyncio.create_task(self._run_adaptive_cron_analysis(conversation_context))
            
            trace_str = " | ".join(self.trace_log)
            return f"{respuesta_final}\\n\\n`🛠️ [DEBUG]: 🤖 Router: {route_info.get('intencion')} | {trace_str}`" if self.trace_log else f"{respuesta_final}\\n\\n`🛠️ [DEBUG]: 🤖 Router: {route_info.get('intencion')}`"

        except Exception as e:
            logger.error(f"Error crítico en orquestador: {e}", exc_info=True)
            return f"⚠️ Error del Sistema: {str(e)}. Mis protocolos de recuperación están activos."

    async def _handle_terapeuta_session(self, texto_limpio: str) -> str:
        conversation_state_manager.guardar_respuesta_terapeuta(texto_limpio)
        siguiente = conversation_state_manager.siguiente_pregunta_terapeuta()
        contexto_str = await self._construir_contexto_async(texto_limpio)
        prompt_terapeuta = f"[MODO TERAPEUTA] El usuario respondió: '{texto_limpio}'. Valida con 1-2 frases empáticas y sinceras. NO hagas más preguntas."
        respuesta_empatica = await self.fsm.step_4_synthesize(prompt_terapeuta, contexto_str)
        return f"{respuesta_empatica}\\n\\n{siguiente}" if siguiente else f"{respuesta_empatica}\\n\\n{conversation_state_manager.generar_cierre_sesion()}"

    async def _run_emotional_analysis(self, texto_limpio: str, usuario_id: str) -> Dict[str, Any]:
        if not texto_limpio or usuario_id == "SISTEMA_CRON":
            return {}
        
        analisis = emotion_engine.analizar_mensaje(texto_limpio)
        if analisis.get("nivel_crisis") == 2:
            await emotion_engine.registrar_crisis(2)
            try:
                persona = await self.data_repo.async_read_data("persona.json", schemas.Persona)
                nombre = persona.nombre
            except Exception:
                nombre = "amigo"
            analisis["respuesta_inmediata"] = emotion_engine.generar_respuesta_crisis(2, nombre)
        
        asyncio.create_task(emotion_engine.actualizar_mencion_meta(texto_limpio))
        return analisis

    async def _execute_tool_if_needed(self, route_info: Dict, texto_limpio: str, contexto_str: str, usuario_id: str) -> tuple[Optional[str], Dict]:
        herramienta = route_info.get("herramienta")
        if not herramienta:
            return None, {}
        
        try:
            params = await self.fsm.step_2_extract(texto_limpio, contexto_str, herramienta)
            resultado = await self.fsm.step_3_execute(herramienta, params)
            self.trace_log.append(f"🔨 Tool: {herramienta} | ✅ OK")
            
            if resultado.startswith(ARCHIVO_ADJUNTO_PREFIX):
                self._pending_attachment = resultado[len(ARCHIVO_ADJUNTO_PREFIX):]
            elif "no encontrada" in resultado.lower():
                self.trace_log[-1] = f"🔨 Tool: {herramienta} | ❓ Not Found"
                if any(kw in texto_limpio.lower() for kw in _PALABRAS_CLAVE_HERRAMIENTAS) and usuario_id != "SISTEMA_CRON":
                    return MENU_HERRAMIENTAS_MARKER + "Herramienta no disponible.", params
            return resultado, params
        except ValueError as e:
            logger.error(f"Error extrayendo parámetros para {herramienta}: {e}")
            self.trace_log.append(f"🔨 Tool: {herramienta} | ❌ FAIL")
            return "Faltan datos para ejecutar la herramienta. ¿Puedes ser más específico?", {}

    async def _process_memory_intent(self, memoria: str, texto_limpio: str, contexto_str: str):
        try:
            params = await self.fsm.step_2_extract(texto_limpio, contexto_str, f"memoria_{memoria}")
            await self.memory_manager.procesar_intencion_memoria(memoria, params)
            self.trace_log.append(f"🧠 Memoria: {memoria} | ✅ OK")
        except Exception as e:
            logger.warning(f"No se pudo guardar la memoria {memoria}: {e}")
            self.trace_log.append(f"🧠 Memoria: {memoria} | ❌ FAIL")

    def _post_process_response(self, respuesta: str, herramienta: Optional[str], params: Dict, analisis: Dict, texto: str, usuario_id: str) -> str:
        if herramienta == "activar_modo" and params.get("modo") == "terapeuta":
            primera_pregunta = conversation_state_manager.siguiente_pregunta_terapeuta()
            if primera_pregunta:
                respuesta += f"\\n\\n{primera_pregunta}"
        
        if analisis.get("es_logro") and usuario_id != "SISTEMA_CRON" and texto:
            try:
                persona = self.data_repo.read_data("persona.json", schemas.Persona)
                mensaje_celebracion = emotion_engine.generar_mensaje_celebracion(texto, persona.nombre)
                if mensaje_celebracion and "🎉" not in respuesta and "🏆" not in respuesta:
                    respuesta = f"{respuesta}\\n\\n{mensaje_celebracion}"
            except Exception:
                pass

        if analisis.get("nivel_crisis") == 1 and usuario_id != "SISTEMA_CRON":
            asyncio.create_task(emotion_engine.registrar_crisis(1))

        if texto and usuario_id != "SISTEMA_CRON":
            conversation_state_manager.incrementar_turno()
            
        return respuesta

    def _actualizar_historial_reciente(self, texto_usuario: str, respuesta_jarvis: str):
        if texto_usuario:
            self._historial_reciente.append({"u": texto_usuario, "j": respuesta_jarvis})
            if len(self._historial_reciente) > 12:
                self._historial_reciente = self._historial_reciente[-12:]

    async def _construir_contexto_async(self, texto_usuario: str) -> str:
        try:
            import pytz
            tasks = [
                self.data_repo.async_read_data("persona.json", schemas.Persona),
                self.data_repo.async_read_data("proyectos.json", schemas.GestorProyectos),
                self.data_repo.async_read_bitacora_summary(),
                self.data_repo.async_read_data("contexto.json", schemas.GestorContexto),
                self.data_repo.async_read_data("entorno.json", schemas.Entorno)
            ]
            persona, proyectos, bitacora, contexto, entorno = await asyncio.gather(*tasks)

            try:
                user_tz = pytz.timezone(entorno.zona_horaria)
            except pytz.UnknownTimeZoneError:
                user_tz = pytz.timezone("America/Lima")
            
            hora_local_str = f"La fecha y hora actual es: {datetime.now(user_tz).strftime('%Y-%m-%d %H:%M:%S')} ({entorno.zona_horaria})."
            memoria_vectorial = await asyncio.to_thread(self.vector_repo.buscar_contexto, texto_usuario, 3)
            bitacora_hoy_str = bitacora.dia_actual.model_dump_json(indent=2) if bitacora.dia_actual else "No hay registro de hoy."
            
            resumen_proyectos = [f"- {n}: {p.estado_actual} ({len([t for t in p.tareas_pendientes if t.estado != 'completado'])} pendientes)" for n, p in proyectos.proyectos_activos.items()]
            str_proyectos = "\\n            ".join(resumen_proyectos) if resumen_proyectos else "No hay proyectos activos."
            
            historial_str = "--- CONVERSACIÓN RECIENTE ---\\n(Inicio de nueva conversación)"
            if self._historial_reciente:
                lineas = [f"  Usuario: {ex['u']}\\n  Jarvis: {ex['j']}" for ex in self._historial_reciente[-10:]]
                historial_str = "--- CONVERSACIÓN RECIENTE (MÁXIMA PRIORIDAD PARA MANTENER EL HILO) ---\\n" + "\\n".join(lineas)

            return f"""
            --- ESTADO DE CONVERSACIÓN ACTIVO ---
            {conversation_state_manager.get_estado_str()}
            {conversation_state_manager.get_instruccion_modo()}
            --- CONTEXTO TEMPORAL Y DE ENTORNO ---
            {hora_local_str}
            --- PERFIL USUARIO Y PREFERENCIAS ---
            {persona.model_dump_json(indent=2)}
            --- RESUMEN DE PROYECTOS ACTIVOS ---
            {str_proyectos}
            --- ESTADO DE HOY ({datetime.now().strftime('%Y-%m-%d')}) ---
            {bitacora_hoy_str}
            Tendencia Reciente: {bitacora.tendencia_energia}
            --- CONTEXTO Y RECORDATORIOS ---
            {contexto.model_dump_json(indent=2)}
            --- MEMORIA A LARGO PLAZO RELEVANTE ---
            {memoria_vectorial}
            {historial_str}
            """
        except Exception as e:
            logger.warning(f"No se pudo cargar contexto completo: {e}")
            return "Contexto no disponible temporalmente."

    async def _run_adaptive_cron_analysis(self, context: Dict[str, Any]):
        """Ejecuta el análisis del cron adaptativo en segundo plano."""
        try:
            await asyncio.sleep(1)
            adaptive_cron.analyze_and_schedule(context)
        except Exception as e:
            logger.error(f"Error en el análisis de cron adaptativo: {e}", exc_info=True)
