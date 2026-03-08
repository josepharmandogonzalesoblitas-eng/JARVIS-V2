from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum
import uuid

# --- BLOQUE 1: IDENTIDAD Y CONTEXTO ---

class Persona(BaseModel):
    nombre: str = "Usuario"
    edad: int
    profesion: str
    valores_clave: List[str] = Field(default_factory=list, description="Principios innegociables del usuario")
    metas_largo_plazo: List[str] = Field(default_factory=list)
    tono_respuesta: str = Field(default="Normal", description="Tono de respuesta de la IA (Ej: Amigo_Sarcástico, Mentor_Relajado)")
    preferencias: Dict[str, str] = Field(
        default_factory=dict,
        description="Gustos y preferencias del usuario. Ej: {'color_favorito': 'azul', 'animal_favorito': 'gatos'}"
    )

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

class BitacoraSummary(BaseModel):
    """
    Modelo optimizado para contener solo la información esencial de la bitácora
    para el prompt de la IA, reduciendo la carga en memoria.
    """
    dia_actual: Optional[RegistroDiario] = None
    tendencia_energia: str = "Sin datos suficientes."

# --- BLOQUE 4: CONTEXTO RÁPIDO Y RUTAS (Asistente Móvil) ---

class Recordatorio(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
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


# ═══════════════════════════════════════════════════════════════════
# BLOQUE 5: PERSONALIDAD, EMOCIONES E INTELIGENCIA CONTEXTUAL
# ═══════════════════════════════════════════════════════════════════

class ModoConversacion(str, Enum):
    """Modos de conversación activos en JARVIS."""
    NORMAL = "normal"
    ESCUCHA_PROFUNDA = "escucha_profunda"
    TRABAJO_PROFUNDO = "trabajo_profundo"
    TERAPEUTA = "terapeuta"
    SILENCIOSO = "silencioso"


class ConversacionProfundaItem(BaseModel):
    """
    Registro de una conversación importante con seguimiento automático.
    JARVIS guarda esto para preguntar semanas después cómo resultó.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    resumen: str
    tipo: str = Field(
        default="general",
        description="salud | relacion | meta | crisis | trabajo | personal | general"
    )
    fecha: str = Field(description="YYYY-MM-DD de cuándo ocurrió")
    fecha_followup: Optional[str] = Field(
        default=None,
        description="YYYY-MM-DD cuando JARVIS debe preguntar cómo resultó"
    )
    completado: bool = False  # True cuando ya se hizo el follow-up


class EstadoEmocionalSistema(BaseModel):
    """
    Estado emocional del sistema para detección de patrones, crisis y logros.
    Persistido en estado_emocional.json
    """
    conversaciones_profundas: List[ConversacionProfundaItem] = Field(
        default_factory=list,
        description="Conversaciones marcadas para seguimiento posterior"
    )
    ultima_crisis_detectada: Optional[str] = Field(
        default=None,
        description="Fecha (YYYY-MM-DD) de la última señal de crisis detectada"
    )
    dias_negativos_consecutivos: int = Field(
        default=0,
        description="Contador de días seguidos con estado de ánimo negativo"
    )
    ultimo_logro_celebrado: Optional[str] = Field(
        default=None,
        description="Descripción del último logro celebrado"
    )
    metas_ultima_mencion: Dict[str, str] = Field(
        default_factory=dict,
        description="meta -> fecha_ultima_mencion (YYYY-MM-DD) para triggers inteligentes"
    )
    sugerencias_enviadas: List[str] = Field(
        default_factory=list,
        description="Títulos de sugerencias ya enviadas (para no repetir)"
    )
