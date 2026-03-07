"""
HERRAMIENTA DE CLIMA - Integración con OpenWeatherMap.

Obtiene el clima actual y pronóstico para adaptar las sugerencias de JARVIS
al contexto meteorológico del usuario.

Requiere: OPENWEATHER_API_KEY en .env
Obtener gratis en: https://openweathermap.org/api (plan Free)
"""

import os
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger("tool_weather")

WEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"


def _get_api_key() -> Optional[str]:
    """Obtiene la API key desde el entorno."""
    return os.getenv("OPENWEATHER_API_KEY")


def _get_ciudad_usuario() -> str:
    """Obtiene la ciudad del usuario desde entorno.json."""
    try:
        from src.data import db_handler, schemas
        entorno = db_handler.read_data("entorno.json", schemas.Entorno)
        return entorno.ubicacion or "Lima"
    except Exception:
        return "Lima"


def obtener_clima_actual(ciudad: Optional[str] = None) -> Dict[str, Any]:
    """
    Obtiene el clima actual para una ciudad.

    Args:
        ciudad: Nombre de la ciudad. Si None, usa la del perfil del usuario.

    Returns:
        Dict con datos de clima, o {"error": "..."} si falla.
    """
    api_key = _get_api_key()
    if not api_key:
        return {"error": "OPENWEATHER_API_KEY no configurado en .env. Obtén una gratis en openweathermap.org"}

    if not ciudad:
        ciudad = _get_ciudad_usuario()

    try:
        response = requests.get(
            f"{WEATHER_BASE_URL}/weather",
            params={
                "q": ciudad,
                "appid": api_key,
                "units": "metric",
                "lang": "es"
            },
            timeout=10
        )

        if response.status_code == 404:
            return {"error": f"Ciudad '{ciudad}' no encontrada en OpenWeatherMap"}
        if response.status_code == 401:
            return {"error": "API Key de OpenWeatherMap inválida"}

        response.raise_for_status()
        data = response.json()

        llueve = (
            data.get("weather", [{}])[0].get("main", "").lower() in ["rain", "drizzle", "thunderstorm"]
            or data.get("rain") is not None
        )

        return {
            "ciudad": data.get("name", ciudad),
            "pais": data.get("sys", {}).get("country", ""),
            "temperatura": round(data["main"]["temp"], 1),
            "sensacion_termica": round(data["main"]["feels_like"], 1),
            "temp_min": round(data["main"]["temp_min"], 1),
            "temp_max": round(data["main"]["temp_max"], 1),
            "descripcion": data["weather"][0]["description"].capitalize(),
            "humedad": data["main"]["humidity"],
            "viento_kmh": round(data["wind"]["speed"] * 3.6, 1),
            "lluvia": llueve,
            "nublado": data.get("clouds", {}).get("all", 0) > 70,
            "timestamp": datetime.now().isoformat()
        }

    except requests.exceptions.ConnectionError:
        return {"error": "Sin conexión a internet para obtener el clima"}
    except requests.exceptions.Timeout:
        return {"error": "Timeout al consultar OpenWeatherMap"}
    except Exception as e:
        logger.error(f"Error obteniendo clima: {e}", exc_info=True)
        return {"error": str(e)}


def obtener_pronostico_dias(ciudad: Optional[str] = None, dias: int = 3) -> List[Dict[str, Any]]:
    """
    Obtiene el pronóstico para los próximos días (hasta 5).
    Usa el endpoint /forecast (5 días / intervalos de 3h) del plan gratuito.

    Returns:
        Lista de dicts con pronóstico por día, o [{"error": "..."}] si falla.
    """
    api_key = _get_api_key()
    if not api_key:
        return [{"error": "OPENWEATHER_API_KEY no configurado"}]

    if not ciudad:
        ciudad = _get_ciudad_usuario()

    try:
        response = requests.get(
            f"{WEATHER_BASE_URL}/forecast",
            params={
                "q": ciudad,
                "appid": api_key,
                "units": "metric",
                "lang": "es",
                "cnt": min(dias * 8, 40)  # 8 registros por día
            },
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # Agrupar por día y tomar resumen diario
        pronostico_diario: Dict[str, Dict] = {}
        for item in data.get("list", []):
            fecha = item["dt_txt"][:10]
            if fecha not in pronostico_diario:
                pronostico_diario[fecha] = {
                    "fecha": fecha,
                    "temp_min": item["main"]["temp_min"],
                    "temp_max": item["main"]["temp_max"],
                    "descripcion": item["weather"][0]["description"].capitalize(),
                    "lluvia": False
                }
            else:
                pronostico_diario[fecha]["temp_min"] = min(
                    pronostico_diario[fecha]["temp_min"],
                    item["main"]["temp_min"]
                )
                pronostico_diario[fecha]["temp_max"] = max(
                    pronostico_diario[fecha]["temp_max"],
                    item["main"]["temp_max"]
                )

            if item.get("weather", [{}])[0].get("main", "").lower() in ["rain", "drizzle", "thunderstorm"]:
                pronostico_diario[fecha]["lluvia"] = True

        return list(pronostico_diario.values())[:dias]

    except Exception as e:
        logger.error(f"Error obteniendo pronóstico: {e}")
        return [{"error": str(e)}]


def formatear_clima_mensaje(clima: Dict[str, Any]) -> str:
    """Formatea el clima como mensaje natural para Telegram."""
    if "error" in clima:
        return f"⚠️ No pude obtener el clima: {clima['error']}"

    lluvia_txt = "\n☔ *Ojo: habrá lluvia hoy.* Lleva paraguas." if clima.get("lluvia") else ""
    nublado_txt = " (muy nublado)" if clima.get("nublado") else ""

    return (
        f"🌡️ *Clima en {clima['ciudad']}*\n"
        f"🌤 {clima['descripcion']}{nublado_txt}\n"
        f"🌡 {clima['temperatura']}°C (sensación {clima['sensacion_termica']}°C)\n"
        f"📊 Mín: {clima['temp_min']}°C | Máx: {clima['temp_max']}°C\n"
        f"💧 Humedad: {clima['humedad']}% | 💨 Viento: {clima['viento_kmh']} km/h"
        f"{lluvia_txt}"
    )


def formatear_pronostico_mensaje(pronostico: List[Dict[str, Any]]) -> str:
    """Formatea el pronóstico de varios días como mensaje."""
    if not pronostico or "error" in pronostico[0]:
        error = pronostico[0].get("error", "desconocido") if pronostico else "sin datos"
        return f"⚠️ No pude obtener el pronóstico: {error}"

    lineas = ["📅 *Pronóstico próximos días:*\n"]
    for dia in pronostico:
        lluvia_ico = " ☔" if dia.get("lluvia") else ""
        lineas.append(
            f"• {dia['fecha']}: {dia['descripcion']}, "
            f"{dia['temp_min']:.0f}°-{dia['temp_max']:.0f}°C{lluvia_ico}"
        )

    return "\n".join(lineas)


def generar_sugerencia_clima(clima: Dict[str, Any]) -> Optional[str]:
    """
    Genera una sugerencia proactiva basada en el clima.
    Ej: si llueve → reprogramar ejercicio al interior.
    """
    if "error" in clima:
        return None

    sugerencias = []

    if clima.get("lluvia"):
        sugerencias.append(
            "Hoy llueve. Si tenías ejercicio al aire libre, considera hacerlo en casa o en el gimnasio."
        )
    if clima.get("temperatura", 20) > 30:
        sugerencias.append(
            f"Hace bastante calor ({clima['temperatura']}°C). Mantente bien hidratado hoy."
        )
    if clima.get("temperatura", 20) < 10:
        sugerencias.append(
            f"Está frío ({clima['temperatura']}°C). Abrígate bien si vas a salir."
        )
    if clima.get("viento_kmh", 0) > 40:
        sugerencias.append(
            f"Hay viento fuerte ({clima['viento_kmh']} km/h). Considera si tus planes al aire libre siguen siendo viables."
        )

    return sugerencias[0] if sugerencias else None
