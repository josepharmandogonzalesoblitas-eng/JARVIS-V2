import logging
import json
from datetime import datetime
from typing import Dict, Any

# --- MODULARIDAD: Importamos componentes aislados ---
from src.core.cerebro import CerebroDigital, PensamientoJarvis
from src.data import db_handler, schemas
from src.data.vector_db import vector_db
from src.utils.sanitizador import Sanitizador

# --- TRAZABILIDAD ---
logger = logging.getLogger("orquestador")

class Orquestador:
    """
    Controlador Central (MVC Pattern).
    Responsabilidad: Coordinar el flujo de datos entre IO, Lógica y Persistencia.
    Principios: Fail-Safe, Atomicidad, Trazabilidad.
    """

    def __init__(self):
        # Inyección de Dependencias implícita
        self.cerebro = CerebroDigital()
        
        # Inicializamos DB por si acaso (Idempotencia)
        db_handler.init_db()

    async def procesar_mensaje(self, usuario_id: str, texto_raw: str, audio_path: str = None) -> str:
        """
        Flujo principal de ejecución (Pipeline) ASÍNCRONO.
        Retorna la respuesta final para el usuario.
        Acepta un archivo de audio opcional.
        """
        try:
            # 1. SANITIZACIÓN (Zero-Trust)
            texto_limpio = Sanitizador.limpiar_texto(texto_raw) if texto_raw else ""
            if texto_limpio and not Sanitizador.validar_seguridad(texto_limpio):
                logger.warning(f"Intento de inyección bloqueado usuario {usuario_id}")
                return "⛔ Sistema de seguridad activado: Input rechazado por contener patrones maliciosos."

            if not texto_limpio and not audio_path:
                return "..." # Ignorar mensajes vacíos

            # 2. CARGA DE CONTEXTO (RAG - Retrieval Augmented Generation)
            # Leemos el estado actual para que el cerebro no alucine.
            contexto_str = self._construir_contexto(texto_limpio)

            # 3. INFERENCIA (El Cerebro Piensa)
            pensamiento: PensamientoJarvis = await self.cerebro.pensar(texto_limpio, contexto_str, audio_path)

            # 4. EJECUCIÓN DE INTENCIÓN (Switch Case Lógico)
            respuesta_final = pensamiento.respuesta_usuario

            if pensamiento.intencion == "actualizar_memoria":
                resultado_accion = self._ejecutar_memoria(pensamiento.datos_extra)
                # Si hubo éxito interno, quizás queramos anexarlo a la respuesta, 
                # pero por ahora confiamos en la respuesta generada por la IA.
                logger.info(f"Actualización de memoria: {resultado_accion}")
                # Para el Lazy Loading de proyectos, anexamos el resultado al usuario
                if pensamiento.datos_extra and pensamiento.datos_extra.get("accion") == "consultar_proyecto":
                    respuesta_final += f"\n\n[Sistema - Detalles del Proyecto]:\n{resultado_accion}"

            elif pensamiento.intencion == "comando":
                resultado_tool = self._ejecutar_herramienta(pensamiento.herramienta_sugerida, pensamiento.datos_extra)
                # Feedback del sistema añadido a la respuesta
                respuesta_final += f"\n\n[Sistema]: {resultado_tool}"

            # 5. RETORNO (Feedback)
            return respuesta_final

        except Exception as e:
            # GRACEFUL DEGRADATION
            # Si todo falla, el usuario recibe un mensaje digno, no un stack trace.
            logger.error(f"Error crítico en orquestador: {e}", exc_info=True)
            return f"⚠️ Error del Sistema: {str(e)}. Mis protocolos de recuperación están activos."

    def _construir_contexto(self, texto_usuario: str) -> str:
        """
        Recopila los JSONs, busca en la BD vectorial y los convierte en texto para el prompt.
        Aplica: Read-Only Access (no modifica nada).
        """
        try:
            # Leemos con Type-Safety gracias a Pydantic
            persona = db_handler.read_data("persona.json", schemas.Persona)
            proyectos = db_handler.read_data("proyectos.json", schemas.GestorProyectos)
            gestor_bitacora = db_handler.read_data("bitacora.json", schemas.GestorBitacora)
            contexto = db_handler.read_data("contexto.json", schemas.GestorContexto)
            
            # Buscamos en ChromaDB recuerdos relevantes para ESTE mensaje
            memoria_vectorial = vector_db.buscar_contexto(texto_usuario, n_results=3)
            
            # Extraer solo el día actual o un registro vacío
            bitacora_hoy = gestor_bitacora.dia_actual.model_dump_json(indent=2) if gestor_bitacora.dia_actual else "No hay registro de hoy."
            
            # Analizar el histórico si hay suficientes días
            historico_keys = list(gestor_bitacora.historico_dias.keys())
            tendencia = "Sin datos suficientes."
            if len(historico_keys) >= 3:
                ultimos_3 = [gestor_bitacora.historico_dias[k].nivel_energia for k in historico_keys[-3:]]
                promedio = sum(ultimos_3) / len(ultimos_3)
                tendencia = f"Promedio energía últimos días: {promedio:.1f}/10"
            
            # --- COMPRESIÓN DE CONTEXTO (Proyectos) ---
            # En lugar de enviar todo el JSON, enviamos un resumen para ahorrar tokens.
            resumen_proyectos = []
            for nombre, p in proyectos.proyectos_activos.items():
                tareas_pendientes = len([t for t in p.tareas_pendientes if t.estado != 'completado'])
                resumen_proyectos.append(f"- {nombre}: {p.estado_actual} ({tareas_pendientes} tareas pendientes)")
            
            str_proyectos = "\n            ".join(resumen_proyectos) if resumen_proyectos else "No hay proyectos activos."

            # Formateamos bonito para que Gemini entienda mejor
            return f"""
            --- PERFIL USUARIO ---
            {persona.model_dump_json(indent=2)}
            
            --- RESUMEN DE PROYECTOS ACTIVOS ---
            {str_proyectos}
            (Para ver detalles completos, usa intención 'actualizar_memoria', archivo 'proyectos', accion 'consultar_proyecto' con {{"nombre": "Nombre del proyecto"}})
            
            --- ESTADO DE HOY ({datetime.now().strftime('%Y-%m-%d')}) ---
            {bitacora_hoy}
            Tendencia Reciente: {tendencia}
            
            --- CONTEXTO Y RECORDATORIOS (MÓVIL) ---
            {contexto.model_dump_json(indent=2)}
            
            {memoria_vectorial}
            """
        except Exception as e:
            logger.warning(f"No se pudo cargar contexto completo: {e}")
            return "Contexto no disponible temporalmente."

    def _ejecutar_memoria(self, datos: Dict[str, Any]) -> str:
        """
        Maneja la persistencia de datos solicitada por la IA.
        Delega a la herramienta de memoria.
        """
        from src.TOOLS.tool_memory import ejecutar_memoria
        return ejecutar_memoria(datos)

    def _ejecutar_herramienta(self, nombre_tool: str, params: Dict[str, Any]) -> str:
        """
        Router para ejecución de scripts/tools.
        Aplica: Modularidad (Tools separadas).
        """
        from src.TOOLS.tool_system import ejecutar_herramienta_sistema
        return ejecutar_herramienta_sistema(nombre_tool, params)
