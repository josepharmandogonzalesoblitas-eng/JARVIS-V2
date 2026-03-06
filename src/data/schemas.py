from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime

# --- BLOQUE 1: IDENTIDAD Y CONTEXTO ---

class Persona(BaseModel):
    nombre: str = "Usuario"
    edad: int
    profesion: str
    valores_clave: List[str] = Field(default_factory=list, description="Principios innegociables del usuario")
    metas_largo_plazo: List[str] = Field(default_factory=list)

class Entorno(BaseModel):
    ubicacion: str
    zona_horaria: str = "America/Lima"
    dispositivos: Dict[str, str] = Field(default_factory=dict, description="Ej: PC Principal, Laptop, Móvil")
    personas_clave: Dict[str, str] = Field(default_factory=dict, description="Mapa de relaciones importantes")

# --- BLOQUE 2: OPERACIÓN (Proyectos) ---

class Tarea(BaseModel):
    id: str
    descripcion: str
    estado: str = Field(pattern="^(pendiente|en_proceso|completado|bloqueado)$")
    prioridad: int = Field(ge=1, le=5)

class Proyecto(BaseModel):
    nombre: str
    descripcion: str
    stack_tecnologico: List[str]
    estado_actual: str
    tareas_pendientes: List[Tarea] = Field(default_factory=list)
    ultima_actualizacion: datetime = Field(default_factory=datetime.now)

class GestorProyectos(BaseModel):
    proyectos_activos: Dict[str, Proyecto] = Field(default_factory=dict)

# --- BLOQUE 3: ESTADO (Bitácora Diaria) ---

class RegistroDiario(BaseModel):
    fecha: str # Formato YYYY-MM-DD
    nivel_energia: int = Field(ge=1, le=10)
    estado_animo: str
    eventos_importantes: List[str] = Field(default_factory=list)
    notas_ia: str = "Sin observaciones aún."

class GestorBitacora(BaseModel):
    historico_dias: Dict[str, RegistroDiario] = Field(default_factory=dict)
    dia_actual: Optional[RegistroDiario] = None

# --- BLOQUE 4: CONTEXTO RÁPIDO Y RUTAS (Asistente Móvil) ---

class Recordatorio(BaseModel):
    id: str
    descripcion: str
    contexto_asociado: str = Field(description="Ej: 'banco', 'supermercado', 'tiempo_libre'")
    completado: bool = False
    fecha_creacion: datetime = Field(default_factory=datetime.now)

class GestorContexto(BaseModel):
    recordatorios_pendientes: List[Recordatorio] = Field(default_factory=list)
    lugares_frecuentes: Dict[str, str] = Field(default_factory=dict, description="Ej: 'banco': 'Centro de la ciudad'")
    rutinas_diarias: List[str] = Field(default_factory=list)

# --- AGREGADOR MAESTRO (Para validación global si fuera necesario) ---
class MemoriaTotal(BaseModel):
    persona: Persona
    entorno: Entorno
    proyectos: GestorProyectos
    bitacora: RegistroDiario
    contexto: GestorContexto
