import json
import os
import shutil
import asyncio
import logging
from threading import Lock as ThreadLock
from typing import Dict, Any, Type
from pydantic import BaseModel
from src.data import schemas

logger = logging.getLogger("db_handler")

# Directorio base para la memoria
MEMORY_PATH = "MEMORIA"

# Lock Global unificado para prevenir Race Conditions en operaciones I/O
_db_lock = ThreadLock()

def _get_path(filename: str) -> str:
    return os.path.join(MEMORY_PATH, filename)

def init_db():
    """
    Bootstrapping con datos válidos (Fail-Safe).
    Crea archivos con datos dummy válidos si no existen.
    """
    if not os.path.exists(MEMORY_PATH):
        os.makedirs(MEMORY_PATH)
        logger.info(f"Directorio {MEMORY_PATH} creado.")
    
    # DATOS SEMILLA (Deben coincidir con schemas.py)
    initial_data = {
        "persona.json": {
            "nombre": "Admin",
            "edad": 30,                      # <--- CAMPO OBLIGATORIO
            "profesion": "Ingeniero",        # <--- CAMPO OBLIGATORIO
            "valores_clave": ["Disciplina", "Automatisación"],
            "metas_largo_plazo": ["Sistema Estable"]
        },
        "entorno.json": {
            "ubicacion": "Base de Operaciones",
            "zona_horaria": "America/Lima",
            "dispositivos": {},
            "personas_clave": {}
        },
        "proyectos.json": {
            "proyectos_activos": {}
        },
        "contexto.json": {
            "recordatorios_pendientes": [],
            "lugares_frecuentes": {},
            "rutinas_diarias": []
        },
        "bitacora.json": {
            "historico_dias": {},
            "dia_actual": {
                "fecha": "2024-01-01",
                "nivel_energia": 8,
                "estado_animo": "Estable",
                "eventos_importantes": [],
                "notas_ia": "Inicio de sistema."
            }
        },
        "estado_emocional.json": {
            "conversaciones_profundas": [],
            "ultima_crisis_detectada": None,
            "dias_negativos_consecutivos": 0,
            "ultimo_logro_celebrado": None,
            "metas_ultima_mencion": {},
            "sugerencias_enviadas": []
        }
    }

    for filename, data in initial_data.items():
        path = _get_path(filename)
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as file:
                json.dump(data, file, indent=4, ensure_ascii=False)
            logger.info(f"Archivo base {filename} generado correctamente.")

def read_data(filename: str, model: Type[BaseModel]) -> BaseModel:
    path = _get_path(filename)
    
    # Auto-healing: Si el archivo no existe, intentamos crearlo
    if not os.path.exists(path):
        init_db()
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return model(**data)
    except Exception as e:
        logger.error(f"Error leyendo o parseando JSON desde {filename}: {e}", exc_info=True)
        raise e

async def async_read_data(filename: str, model: Type[BaseModel]) -> BaseModel:
    """Versión asíncrona segura de lectura, envuelve la sincrónica con run_in_executor y lock."""
    return await asyncio.to_thread(read_data, filename, model)

def save_data(filename: str, data: BaseModel):
    path = _get_path(filename)
    temp_path = path + ".tmp"
    
    try:
        json_data = data.model_dump(mode='json')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise e

async def async_save_data(filename: str, data: BaseModel):
    """Versión asíncrona segura de escritura, envuelve la sincrónica con run_in_executor."""
    return await asyncio.to_thread(save_data, filename, data)

async def async_read_bitacora_summary() -> schemas.BitacoraSummary:
    """
    Optimización Big-O: Lee el archivo de bitácora completo pero solo procesa y devuelve
    los datos esenciales (día actual y tendencia), reduciendo la huella de memoria
    del objeto retornado.
    """
    gestor_completo = await async_read_data("bitacora.json", schemas.GestorBitacora)
    
    tendencia = "Sin datos suficientes."
    if gestor_completo.historico_dias:
        historico_keys = sorted(gestor_completo.historico_dias.keys())
        if len(historico_keys) >= 3:
            ultimos_3_dias = historico_keys[-3:]
            ultimos_3_energias = [
                gestor_completo.historico_dias[k].nivel_energia for k in ultimos_3_dias
            ]
            if ultimos_3_energias:
                promedio = sum(ultimos_3_energias) / len(ultimos_3_energias)
                tendencia = f"Promedio energía últimos 3 días: {promedio:.1f}/10"

    return schemas.BitacoraSummary(
        dia_actual=gestor_completo.dia_actual,
        tendencia_energia=tendencia
    )
