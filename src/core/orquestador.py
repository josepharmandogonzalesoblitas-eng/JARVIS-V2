import logging
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

# --- MODULARIDAD: Inversión de Dependencias ---
from src.core.cerebro import CerebroDigital, PensamientoJarvis
from src.core.memory_manager import MemoryManager
from src.core.emotion_engine import emotion_engine
from src.core.conversation_state import conversation_state_manager
from src.data import schemas
from src.core.interfaces import IDataRepository, IVectorRepository, IToolsRepository

# --- TRAZABILIDAD ---
logger = logging.getLogger("orquestador")

# Marcador especial para archivos adjuntos generados por herramientas
ARCHIVO_ADJUNTO_PREFIX = "__ARCHIVO_ADJUNTO__:"


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
        self.cerebro = CerebroDigital()
        self.memory_manager = MemoryManager(vector_repo=self.vector_repo)

        # Buffer de conversación en memoria (short-term memory)
        self._historial_reciente: list = []

        # Archivo adjunto pendiente de enviar (foto/gráfico generado por herramienta)
        # El telegram_bot lo lee y envía como photo/document
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

        Args:
            usuario_id: ID del remitente.
            texto_limpio: Mensaje sanitizado.
            audio_path: Ruta temporal de audio si aplica.
            image_path: Ruta temporal de imagen si aplica (Gemini Vision).

        Returns:
            Respuesta final en texto para enviar al usuario.
        """
        try:
            # Limpiar adjunto previo
            self._pending_attachment = None

            if not texto_limpio and not audio_path and not image_path:
                return "..."

            # Verificar expiración de modos de conversación
            expirado = conversation_state_manager.verificar_expiracion()
            if expirado:
                # Notificar que el modo expiró
                modo_str = conversation_state_manager.modo.value
                logger.info(f"Modo {modo_str} expirado automáticamente.")

            # ─── MODO TERAPEUTA: Sesión estructurada ──────────────────────────
            if (conversation_state_manager.sesion_terapeuta_activa
                    and texto_limpio
                    and usuario_id != "SISTEMA_CRON"):

                # Guardar respuesta del usuario
                conversation_state_manager.guardar_respuesta_terapeuta(texto_limpio)

                # Obtener siguiente pregunta
                siguiente = conversation_state_manager.siguiente_pregunta_terapeuta()

                # Construir contexto para respuesta empática de Gemini
                contexto_str = await self._construir_contexto_async(texto_limpio)
                prompt_terapeuta = (
                    f"[MODO TERAPEUTA] El usuario respondió a una pregunta de reflexión guiada. "
                    f"Valida su respuesta con 1-2 frases empáticas y sinceras. "
                    f"NO hagas más preguntas (la siguiente pregunta ya está incluida). "
                    f"Respuesta: '{texto_limpio}'"
                )

                pensamiento = await self.cerebro.pensar(prompt_terapeuta, contexto_str)
                respuesta_empatica = pensamiento.respuesta_usuario

                if siguiente:
                    return f"{respuesta_empatica}\n\n{siguiente}"
                else:
                    # Sesión completada
                    cierre = conversation_state_manager.generar_cierre_sesion()
                    return f"{respuesta_empatica}\n\n{cierre}"

            # ─── MODO FOCO COMPLETADO: Preguntar qué logró ────────────────────
            if conversation_state_manager.foco_completado():
                mins = conversation_state_manager.tiempo_en_foco()
                conversation_state_manager.desactivar_modo()
                return (
                    f"⏰ ¡Tiempo! Completaste {mins} minutos de trabajo profundo. "
                    f"¿Qué lograste en esta sesión? Cuéntame para registrarlo. 🎯"
                )

            # ─── ANÁLISIS EMOCIONAL EN TIEMPO REAL ───────────────────────────
            analisis_emocional = {}
            if texto_limpio and usuario_id != "SISTEMA_CRON":
                analisis_emocional = emotion_engine.analizar_mensaje(texto_limpio)

                # Crisis nivel 2: Respuesta inmediata de seguridad
                if analisis_emocional.get("nivel_crisis") == 2:
                    await emotion_engine.registrar_crisis(2)
                    try:
                        persona = await self.data_repo.async_read_data("persona.json", schemas.Persona)
                        nombre = persona.nombre
                    except Exception:
                        nombre = "amigo"
                    return emotion_engine.generar_respuesta_crisis(2, nombre)

                # Actualizar mención de metas (en background)
                asyncio.create_task(
                    emotion_engine.actualizar_mencion_meta(texto_limpio)
                )

            # 1. CARGA DE CONTEXTO (RAG) - ASÍNCRONO
            contexto_str = await self._construir_contexto_async(texto_limpio or "")

            # 2. INFERENCIA (El Cerebro Piensa)
            pensamiento: PensamientoJarvis = await self.cerebro.pensar(
                texto_limpio or "",
                contexto_str,
                audio_path,
                image_path
            )

            # 3. PROCESAMIENTO DE MEMORIA
            if pensamiento.memoria_intencion:
                await self.memory_manager.procesar_intencion_memoria(
                    pensamiento.memoria_intencion,
                    pensamiento.memoria_datos or {}
                )

            # 4. EJECUCIÓN DE INTENCIÓN (Router Lógico)
            respuesta_final = pensamiento.respuesta_usuario

            if pensamiento.intencion == "fallback_error":
                return respuesta_final

            elif pensamiento.intencion == "comando":
                if pensamiento.herramienta_sugerida and pensamiento.herramienta_sugerida != "None":
                    resultado_tool = self._ejecutar_herramienta(
                        pensamiento.herramienta_sugerida,
                        pensamiento.datos_extra or {}
                    )

                    # Detectar archivos adjuntos generados por herramientas
                    if resultado_tool.startswith(ARCHIVO_ADJUNTO_PREFIX):
                        self._pending_attachment = resultado_tool[len(ARCHIVO_ADJUNTO_PREFIX):]
                        # La respuesta de texto es la del LLM (ya tiene descripción)
                    else:
                        respuesta_final += f"\n\n{resultado_tool}"

                    # Si se activó modo terapeuta, enviar primera pregunta
                    if (pensamiento.herramienta_sugerida == "activar_modo"
                            and (pensamiento.datos_extra or {}).get("modo") == "terapeuta"):
                        primera_pregunta = conversation_state_manager.siguiente_pregunta_terapeuta()
                        if primera_pregunta:
                            respuesta_final += f"\n\n{primera_pregunta}"

            # ─── POST-PROCESAMIENTO EMOCIONAL ─────────────────────────────────

            # Celebración de logros
            if (analisis_emocional.get("es_logro")
                    and usuario_id != "SISTEMA_CRON"
                    and texto_limpio):
                try:
                    persona = await self.data_repo.async_read_data("persona.json", schemas.Persona)
                    mensaje_celebracion = emotion_engine.generar_mensaje_celebracion(
                        texto_limpio, persona.nombre
                    )
                    # Agregar al final solo si la respuesta no tiene ya una celebración
                    if mensaje_celebracion and "🎉" not in respuesta_final and "🏆" not in respuesta_final:
                        respuesta_final = f"{respuesta_final}\n\n{mensaje_celebracion}"
                except Exception:
                    pass

            # Alerta de patrón negativo (nivel 1) — más sutil, sin interrumpir el flujo
            if (analisis_emocional.get("nivel_crisis") == 1
                    and usuario_id != "SISTEMA_CRON"):
                await emotion_engine.registrar_crisis(1)
                # La respuesta del LLM ya debería ser empática; no añadimos más

            # Registrar mención en modos de conversación
            if texto_limpio and usuario_id != "SISTEMA_CRON":
                conversation_state_manager.incrementar_turno()

            # 5. ACTUALIZAR HISTORIAL (Short-Term Memory)
            if texto_limpio:
                self._historial_reciente.append({
                    "u": texto_limpio,
                    "j": respuesta_final
                })
                if len(self._historial_reciente) > 12:
                    self._historial_reciente = self._historial_reciente[-12:]

            return respuesta_final

        except Exception as e:
            logger.error(f"Error crítico en orquestador: {e}", exc_info=True)
            return f"⚠️ Error del Sistema: {str(e)}. Mis protocolos de recuperación están activos."

    async def _construir_contexto_async(self, texto_usuario: str) -> str:
        """
        Recopila de forma concurrente el contexto necesario para el prompt de la IA.
        V2: Incluye estado emocional del sistema y modo de conversación activo.
        """
        try:
            import pytz
            persona_task = self.data_repo.async_read_data("persona.json", schemas.Persona)
            proyectos_task = self.data_repo.async_read_data("proyectos.json", schemas.GestorProyectos)
            bitacora_summary_task = self.data_repo.async_read_bitacora_summary()
            contexto_task = self.data_repo.async_read_data("contexto.json", schemas.GestorContexto)
            entorno_task = self.data_repo.async_read_data("entorno.json", schemas.Entorno)

            persona, proyectos, bitacora_summary, contexto, entorno = await asyncio.gather(
                persona_task, proyectos_task, bitacora_summary_task, contexto_task, entorno_task
            )

            # Timezone
            try:
                user_tz = pytz.timezone(entorno.zona_horaria)
            except pytz.UnknownTimeZoneError:
                user_tz = pytz.timezone("America/Lima")

            hora_local_str = f"La fecha y hora actual es: {datetime.now(user_tz).strftime('%Y-%m-%d %H:%M:%S')} ({entorno.zona_horaria})."

            # Búsqueda vectorial concurrente
            memoria_vectorial = await asyncio.to_thread(
                self.vector_repo.buscar_contexto, texto_usuario, 3
            )

            bitacora_hoy_str = (
                bitacora_summary.dia_actual.model_dump_json(indent=2)
                if bitacora_summary.dia_actual else "No hay registro de hoy."
            )

            # Resumen de proyectos
            resumen_proyectos = []
            for nombre, p in proyectos.proyectos_activos.items():
                pendientes = len([t for t in p.tareas_pendientes if t.estado != 'completado'])
                resumen_proyectos.append(f"- {nombre}: {p.estado_actual} ({pendientes} tareas pendientes)")
            str_proyectos = "\n            ".join(resumen_proyectos) if resumen_proyectos else "No hay proyectos activos."

            # Estado de conversación activo
            estado_conv_str = conversation_state_manager.get_estado_str()
            instruccion_modo = conversation_state_manager.get_instruccion_modo()

            # Historial reciente de conversación (se mueve al final del prompt)
            if self._historial_reciente:
                lineas = []
                for ex in self._historial_reciente[-10:]:
                    lineas.append(f"  Usuario: {ex['u']}\n  Jarvis: {ex['j']}")
                historial_str = (
                    "--- CONVERSACIÓN RECIENTE (MÁXIMA PRIORIDAD PARA MANTENER EL HILO) ---\n"
                    + "\n".join(lineas)
                )
            else:
                historial_str = "--- CONVERSACIÓN RECIENTE ---\n(Inicio de nueva conversación)"

            return f"""
            --- ESTADO DE CONVERSACIÓN ACTIVO ---
            {estado_conv_str}
            {instruccion_modo}

            --- CONTEXTO TEMPORAL Y DE ENTORNO ---
            {hora_local_str}

            --- PERFIL USUARIO Y PREFERENCIAS ---
            {persona.model_dump_json(indent=2)}

            --- RESUMEN DE PROYECTOS ACTIVOS ---
            {str_proyectos}

            --- ESTADO DE HOY ({datetime.now().strftime('%Y-%m-%d')}) ---
            {bitacora_hoy_str}
            Tendencia Reciente: {bitacora_summary.tendencia_energia}

            --- CONTEXTO Y RECORDATORIOS ---
            {contexto.model_dump_json(indent=2)}

            --- MEMORIA A LARGO PLAZO RELEVANTE ---
            {memoria_vectorial}

            {historial_str}
            """
        except Exception as e:
            logger.warning(f"No se pudo cargar contexto completo: {e}")
            return "Contexto no disponible temporalmente."

    async def _ejecutar_memoria_async(self, datos: Dict[str, Any]) -> str:
        return await self.tools_repo.async_ejecutar_memoria(datos)

    def _ejecutar_herramienta(self, nombre_tool: str, params: Dict[str, Any]) -> str:
        return self.tools_repo.ejecutar_herramienta(nombre_tool, params)
