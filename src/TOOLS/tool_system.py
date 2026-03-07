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

from duckduckgo_search import DDGS

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
                
            logger.info(f"Buscando en la web: {query}")
            resultados = []
            # Añadir User-Agent para evitar bloqueos
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
            }
            with DDGS(headers=headers) as ddgs:
                # Buscamos los 3 primeros resultados
                for r in ddgs.text(query, max_results=3):
                    resultados.append(f"- {r.get('title')}: {r.get('body')} ({r.get('href')})")
            
            if not resultados:
                return f"No encontré información en internet sobre '{query}'."
                
            res_str = "\n".join(resultados)
            return f"Resultados web para '{query}':\n{res_str}"
            
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

        return f"Herramienta '{nombre}' no encontrada en el módulo de sistema."

    except Exception as e:
        logger.error(f"Error ejecutando herramienta {nombre}: {e}")
        return f"Fallo al ejecutar {nombre}: {str(e)}"