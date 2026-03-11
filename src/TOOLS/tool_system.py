"""
HERRAMIENTAS DEL SISTEMA.
Control de PC, Búsqueda, Información del Sistema.
"""

import os
import platform
import logging
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any

logger = logging.getLogger("tool_system")

try:
    from duckduckgo_search import DDGS
    _DDGS_SUPPORTS_HEADERS = True
except ImportError:
    try:
        from ddgs import DDGS
        _DDGS_SUPPORTS_HEADERS = False
    except ImportError:
        DDGS = None
        _DDGS_SUPPORTS_HEADERS = False

import pytz

def ejecutar_herramienta_sistema(nombre: str, params: Dict[str, Any]) -> str:
    """
    Router principal para herramientas de sistema operativo y utilidades.
    """
    try:
        if nombre == "consultar_hora":
            # Usar el timezone del entorno del usuario para dar la hora correcta
            from src.data import db_handler, schemas
            try:
                entorno = db_handler.read_data("entorno.json", schemas.Entorno)
                user_tz = pytz.timezone(entorno.zona_horaria)
            except Exception:
                user_tz = pytz.timezone("America/Lima") # Fallback
            
            hora_correcta = datetime.now(user_tz)
            return f"La hora actual es {hora_correcta.strftime('%Y-%m-%d %H:%M:%S')}."
            
        elif nombre == "estado_sistema":
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            return f"Estado PC: CPU {cpu}%, RAM {ram.percent}% (Libre: {ram.available / (1024**3):.1f} GB)."
            
        elif nombre == "info_os":
            uname = platform.uname()
            return f"Sistema: {uname.system} {uname.release}, Nodo: {uname.node}, Máquina: {uname.machine}."
            
        elif nombre == "buscar_web":
            query = params.get("query")
            if not query:
                return "Error: No se proporcionó un término de búsqueda."

            # Inteligencia Geográfica: si el usuario pide algo "cerca",
            # inyectamos la ciudad del contexto.
            if "cerca" in query.lower() or "aquí" in query.lower() or "mi zona" in query.lower():
                from src.data import db_handler, schemas
                try:
                    entorno = db_handler.read_data("entorno.json", schemas.Entorno)
                    if entorno.ubicacion and entorno.ubicacion not in query:
                        query += f" en {entorno.ubicacion}"
                except Exception:
                    pass # Si falla, la búsqueda se hace sin contexto

            # Graceful Degradation: si ninguna librería está disponible
            if DDGS is None:
                return "Error: Librería de búsqueda web no disponible. Instala duckduckgo_search."

            logger.info(f"Buscando en la web: {query}")
            resultados = []

            # Fail-Safe: pasar headers solo si la librería los soporta
            ua = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36')
            ddgs_kwargs = {"headers": {"User-Agent": ua}} if _DDGS_SUPPORTS_HEADERS else {}

            with DDGS(**ddgs_kwargs) as ddgs:
                for r in ddgs.text(query, max_results=3):
                    titulo = r.get('title', 'Sin título')
                    cuerpo = r.get('body', '')
                    link = r.get('href', '')
                    resultados.append(f"🔹 **{titulo}**\n{cuerpo}\n🔗 {link}\n")

            if not resultados:
                return f"No encontré información en internet sobre '{query}'."

            res_str = "\n".join(resultados)
            return f"🌐 **Resultados web para '{query}':**\n\n{res_str}"
            
        elif nombre == "agendar_recordatorio":
            hora_hhmm = params.get("hora")
            mensaje = params.get("mensaje")
            if not hora_hhmm or not mensaje:
                return "Error: Falta la 'hora' (HH:MM) o el 'mensaje'."
            
            # Importar aquí para evitar referencias circulares
            from src.core.cron import cron_manager
            resultado = cron_manager.agendar_alarma_dinamica(hora_hhmm, mensaje)
            return resultado

        elif nombre == "alarma_rapida":
            minutos = params.get("minutos")
            mensaje = params.get("mensaje")
            if not minutos or not mensaje:
                return "Error: Faltan 'minutos' o 'mensaje'."
            
            from src.core.cron import cron_manager
            
            # Calculamos la hora sumando los minutos a la hora actual
            hora_futura = datetime.now() + timedelta(minutes=int(minutos))
            hora_hhmm = hora_futura.strftime('%H:%M')
            
            resultado = cron_manager.agendar_alarma_dinamica(hora_hhmm, f"[TIMER {minutos}m] {mensaje}")
            return f"Timer configurado. {resultado}"

        elif nombre == "google_calendar":
            from src.TOOLS.tool_agenda import ToolAgenda
            agenda = ToolAgenda()
            resumen = params.get("resumen")
            fecha_inicio_iso = params.get("fecha_inicio_iso")
            duracion = params.get("duracion_minutos", 60)
            
            if not resumen or not fecha_inicio_iso:
                return "Faltan datos para Calendar: resumen o fecha_inicio_iso."
                
            return agenda.crear_evento_calendar(resumen, fecha_inicio_iso, int(duracion))

        elif nombre == "google_tasks":
            from src.TOOLS.tool_agenda import ToolAgenda
            agenda = ToolAgenda()
            titulo = params.get("titulo")
            if not titulo:
                return "Faltan datos para Tasks: titulo."

            return agenda.crear_tarea(titulo)

        # ─── NUEVAS HERRAMIENTAS ─────────────────────────────────────────────

        elif nombre == "clima_actual":
            from src.TOOLS.tool_weather import obtener_clima_actual, formatear_clima_mensaje
            ciudad = params.get("ciudad")
            clima = obtener_clima_actual(ciudad)
            return formatear_clima_mensaje(clima)

        elif nombre == "pronostico_clima":
            from src.TOOLS.tool_weather import obtener_pronostico_dias, formatear_pronostico_mensaje
            ciudad = params.get("ciudad")
            dias = int(params.get("dias", 3))
            pronostico = obtener_pronostico_dias(ciudad, dias)
            return formatear_pronostico_mensaje(pronostico)

        elif nombre == "generar_grafico_energia":
            from src.TOOLS.tool_graphs import generar_grafico_energia
            dias = int(params.get("dias", 7))
            path = generar_grafico_energia(dias)
            if path:
                return f"__ARCHIVO_ADJUNTO__:{path}"
            return "No hay suficientes datos de energía registrados para generar el gráfico (mínimo 2 días)."

        elif nombre == "generar_progreso_proyecto":
            from src.TOOLS.tool_graphs import generar_grafico_progreso_proyecto
            nombre_proy = params.get("nombre_proyecto", "")
            path = generar_grafico_progreso_proyecto(nombre_proy)
            if path:
                return f"__ARCHIVO_ADJUNTO__:{path}"
            return f"No se pudo generar el gráfico del proyecto '{nombre_proy}'. Verifica que existe y tiene tareas registradas."

        elif nombre == "generar_resumen_mensual":
            from src.TOOLS.tool_graphs import generar_resumen_mensual
            path = generar_resumen_mensual()
            if path:
                return f"__ARCHIVO_ADJUNTO__:{path}"
            return "No hay datos del mes actual para generar el resumen visual."

        elif nombre == "activar_modo":
            from src.core.conversation_state import conversation_state_manager
            modo = params.get("modo", "escucha_profunda")
            duracion = params.get("duracion_minutos")
            tema = params.get("tema")

            if duracion:
                duracion = int(duracion)

            success = conversation_state_manager.activar_modo(modo, duracion, tema)
            if not success:
                return f"Modo '{modo}' no reconocido. Modos válidos: escucha_profunda, trabajo_profundo, silencioso, terapeuta."

            mensajes = {
                "escucha_profunda": f"🎙️ Modo Escucha Profunda activado. Estoy completamente presente para ti{' — tema: ' + tema if tema else ''}.",
                "trabajo_profundo": f"🧠 Modo Trabajo Profundo activado por {duracion or 120} minutos. No te interrumpiré. ¡A concentrarse!",
                "silencioso": f"🔕 Modo Silencioso activado{(' por ' + str(duracion) + ' minutos') if duracion else ''}. No enviaré notificaciones proactivas.",
                "terapeuta": "🌿 Iniciando sesión de reflexión guiada. Tómate tu tiempo con cada respuesta.",
                "normal": "✅ Regresando al modo normal."
            }
            return mensajes.get(modo, f"Modo '{modo}' activado.")

        elif nombre == "desactivar_modo":
            from src.core.conversation_state import conversation_state_manager
            modo_anterior = conversation_state_manager.desactivar_modo()
            return f"✅ Modo {modo_anterior.value} desactivado. Regresando al modo normal."

        return f"Herramienta '{nombre}' no encontrada en el módulo de sistema."

    except Exception as e:
        logger.error(f"Error ejecutando herramienta {nombre}: {e}")
        return f"Fallo al ejecutar {nombre}: {str(e)}"