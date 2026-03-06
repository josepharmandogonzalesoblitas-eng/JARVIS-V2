import json
import os
import shutil
from threading import Lock
from typing import Dict, Any, Type
from pydantic import BaseModel
from src.data import schemas

# Directorio base para la memoria
MEMORY_PATH = "MEMORIA"

# Lock Global para evitar Race Conditions
_db_lock = Lock()

def _get_path(filename: str) -> str:
    return os.path.join(MEMORY_PATH, filename)

def init_db():
    """
    Bootstrapping con datos válidos (Fail-Safe).
    Crea archivos con datos dummy válidos si no existen.
    """
    if not os.path.exists(MEMORY_PATH):
        os.makedirs(MEMORY_PATH)
        print(f"[DB] Directorio {MEMORY_PATH} creado.")
    
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
        "bitacora.json": {
            "fecha": "2024-01-01",
            "nivel_energia": 8,
            "estado_animo": "Estable",
            "eventos_importantes": [],
            "notas_ia": "Inicio de sistema."
        }
    }

    for filename, data in initial_data.items():
        path = _get_path(filename)
        # Solo creamos si no existe (para no borrar datos del usuario futuro)
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as file:
                json.dump(data, file, indent=4, ensure_ascii=False)
            print(f"[DB] Archivo base {filename} generado correctamente.")

def read_data(filename: str, model: Type[BaseModel]) -> BaseModel:
    path = _get_path(filename)
    
    with _db_lock:
        # Auto-healing: Si el archivo no existe, intentamos crearlo
        if not os.path.exists(path):
            init_db()
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return model(**data)
        except Exception as e:
            # Aquí podrías loguear el error, pero dejamos que suba para que el test lo detecte
            print(f"[ERROR DB READ] {filename}: {e}")
            raise e

def save_data(filename: str, data: BaseModel):
    path = _get_path(filename)
    temp_path = path + ".tmp"
    
    with _db_lock:
        try:
            json_data = data.model_dump(mode='json')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise e