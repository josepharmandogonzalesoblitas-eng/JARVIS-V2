"""
GESTOR DE ESTADO DE CONVERSACIÓN DE JARVIS.

Maneja los modos de conversación activos:
- NORMAL      : Comportamiento estándar (default).
- ESCUCHA     : Mantiene el hilo de un tema emocional por 5 intercambios.
- FOCO        : Modo trabajo profundo, JARVIS no interrumpe durante N minutos.
- TERAPEUTA   : Sesión estructurada de reflexión guiada (5 preguntas de CBT).
- SILENCIOSO  : JARVIS recibe pero NO envía mensajes proactivos del CRON.

Estado en memoria (se resetea al reiniciar, es correcto — los modos son sesionales).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from src.data.schemas import ModoConversacion

logger = logging.getLogger("conversation_state")


class ConversationStateManager:
    """
    Gestiona el modo de conversación activo de JARVIS.
    Singleton: una instancia global compartida entre todos los módulos.
    """

    # Preguntas de reflexión guiada (basadas en técnicas de CBT + Journaling)
    PREGUNTAS_TERAPEUTA = [
        (
            "🏆 *Pregunta 1/5 — Victoria de la semana*\n\n"
            "¿Cuál fue tu mayor logro esta semana? No tiene que ser grande. "
            "¿Qué cosa hiciste que te hizo sentir orgulloso/a, aunque sea un poco?"
        ),
        (
            "🧩 *Pregunta 2/5 — Desafío y aprendizaje*\n\n"
            "¿Qué fue lo más difícil que enfrentaste esta semana? "
            "¿Qué aprendiste de esa situación sobre ti mismo/a?"
        ),
        (
            "💪 *Pregunta 3/5 — Bienestar físico*\n\n"
            "¿Cómo está tu cuerpo? ¿Dormiste bien, te alimentaste bien, te moviste? "
            "En una escala del 1-10, ¿cómo calificarías tu bienestar físico esta semana?"
        ),
        (
            "🎯 *Pregunta 4/5 — La tarea que evitaste*\n\n"
            "Sé honesto/a: ¿hubo algo que sabías que debías hacer esta semana "
            "pero evitaste? ¿Qué te frenó?"
        ),
        (
            "📊 *Pregunta 5/5 — Calificación global*\n\n"
            "Del 1 al 10, ¿cómo calificarías tu semana en general? "
            "Y lo más importante: ¿qué UNA cosa harías diferente la próxima semana?"
        ),
    ]

    def __init__(self):
        self.modo: ModoConversacion = ModoConversacion.NORMAL
        self.modo_expira: Optional[datetime] = None
        self.mensajes_en_modo: int = 0
        self.tema_activo: Optional[str] = None

        # Estado específico de modo foco
        self.inicio_foco: Optional[datetime] = None
        self.duracion_foco_minutos: int = 120

        # Estado específico de sesión terapeuta
        self.paso_terapeuta: int = 0
        self.sesion_terapeuta_activa: bool = False
        self.respuestas_sesion: list = []  # Para guardar respuestas y generar resumen

        # TTS global
        self.tts_activo: bool = False

    # ─── ACTIVACIÓN / DESACTIVACIÓN ────────────────────────────────────────────

    def activar_modo(
        self,
        modo: str,
        duracion_minutos: Optional[int] = None,
        tema: Optional[str] = None
    ) -> bool:
        """
        Activa un modo de conversación.

        Args:
            modo: Nombre del modo ("escucha_profunda", "trabajo_profundo", "terapeuta", "silencioso").
            duracion_minutos: Duración opcional del modo (para foco y silencioso).
            tema: Tema activo (para escucha profunda).

        Returns:
            True si se activó correctamente.
        """
        modos_validos = {m.value: m for m in ModoConversacion}
        if modo not in modos_validos:
            logger.warning(f"Modo inválido solicitado: '{modo}'")
            return False

        # Reset de estado previo
        self._reset_estado()

        self.modo = modos_validos[modo]
        self.mensajes_en_modo = 0
        self.tema_activo = tema

        if duracion_minutos:
            self.modo_expira = datetime.now() + timedelta(minutes=duracion_minutos)

        # Estado específico por modo
        if modo == "trabajo_profundo":
            self.inicio_foco = datetime.now()
            self.duracion_foco_minutos = duracion_minutos or 120
        elif modo == "terapeuta":
            self.sesion_terapeuta_activa = True
            self.paso_terapeuta = 0
            self.respuestas_sesion = []

        logger.info(f"🎭 Modo activado: {modo}" + (f" ({duracion_minutos}min)" if duracion_minutos else ""))
        return True

    def desactivar_modo(self) -> ModoConversacion:
        """Regresa al modo NORMAL. Retorna el modo que estaba activo."""
        modo_anterior = self.modo
        self._reset_estado()
        logger.info(f"Modo desactivado. Regresando a NORMAL desde {modo_anterior.value}")
        return modo_anterior

    def _reset_estado(self):
        """Limpia todo el estado de modo actual."""
        self.modo = ModoConversacion.NORMAL
        self.modo_expira = None
        self.mensajes_en_modo = 0
        self.tema_activo = None
        self.inicio_foco = None
        self.sesion_terapeuta_activa = False
        self.paso_terapeuta = 0
        self.respuestas_sesion = []

    # ─── VERIFICACIONES ────────────────────────────────────────────────────────

    def verificar_expiracion(self) -> bool:
        """
        Verifica si el modo actual expiró por tiempo.
        Si expiró, lo desactiva y retorna True.
        """
        if self.modo_expira and datetime.now() >= self.modo_expira:
            self.desactivar_modo()
            return True
        return False

    def es_silencioso(self) -> bool:
        """
        True si JARVIS debe omitir mensajes proactivos del CRON.
        Aplica en modo silencioso Y trabajo profundo.
        """
        return self.modo in [
            ModoConversacion.SILENCIOSO,
            ModoConversacion.TRABAJO_PROFUNDO
        ]

    def incrementar_turno(self):
        """
        Incrementa el contador de turnos en el modo actual.
        La escucha profunda se desactiva automáticamente después de 5 intercambios.
        """
        self.mensajes_en_modo += 1
        if (self.modo == ModoConversacion.ESCUCHA_PROFUNDA
                and self.mensajes_en_modo >= 5):
            logger.info("Escucha profunda: 5 intercambios completados. Volviendo a NORMAL.")
            self.desactivar_modo()

    def tiempo_en_foco(self) -> Optional[int]:
        """Retorna minutos transcurridos en modo foco, o None si no está en foco."""
        if self.inicio_foco and self.modo == ModoConversacion.TRABAJO_PROFUNDO:
            return int((datetime.now() - self.inicio_foco).total_seconds() / 60)
        return None

    def foco_completado(self) -> bool:
        """True si el tiempo de foco ya terminó pero no se desactivó manualmente."""
        mins = self.tiempo_en_foco()
        return mins is not None and mins >= self.duracion_foco_minutos

    # ─── SESIÓN TERAPEUTA ───────────────────────────────────────────────────────

    def siguiente_pregunta_terapeuta(self) -> Optional[str]:
        """
        Retorna la siguiente pregunta de la sesión terapeuta.
        Si se agotan las preguntas, cierra la sesión y retorna None.
        """
        if not self.sesion_terapeuta_activa:
            return None

        if self.paso_terapeuta < len(self.PREGUNTAS_TERAPEUTA):
            pregunta = self.PREGUNTAS_TERAPEUTA[self.paso_terapeuta]
            self.paso_terapeuta += 1
            return pregunta
        else:
            # Sesión completada
            self.desactivar_modo()
            return None

    def guardar_respuesta_terapeuta(self, texto: str):
        """Guarda una respuesta del usuario en la sesión."""
        self.respuestas_sesion.append(texto)

    def generar_cierre_sesion(self) -> str:
        """Genera un mensaje de cierre para la sesión de terapeuta."""
        num_respuestas = len(self.respuestas_sesion)
        return (
            f"✨ *Sesión de reflexión completada* ({num_respuestas} respuestas)\n\n"
            f"Gracias por tomarte este tiempo de introspección. "
            f"Explorar estas preguntas toma valentía. "
            f"¿Hay algo de lo que reflexionaste que quieras profundizar ahora? "
            f"Estoy aquí."
        )

    # ─── TTS ───────────────────────────────────────────────────────────────────

    def toggle_tts(self) -> bool:
        """Alterna el modo TTS (voz). Retorna el nuevo estado."""
        self.tts_activo = not self.tts_activo
        estado = "activado 🔊" if self.tts_activo else "desactivado 🔇"
        logger.info(f"TTS {estado}")
        return self.tts_activo

    # ─── DESCRIPCIÓN DEL ESTADO ────────────────────────────────────────────────

    def get_estado_str(self) -> str:
        """Descripción del estado actual para inyectar en el contexto del LLM."""
        base = f"[MODO: {self.modo.value.upper()}"

        if self.modo == ModoConversacion.ESCUCHA_PROFUNDA:
            base += f" | Tema: '{self.tema_activo or 'emocional'}' | Turno {self.mensajes_en_modo}/5"
        elif self.modo == ModoConversacion.TRABAJO_PROFUNDO:
            mins = self.tiempo_en_foco() or 0
            base += f" | {mins}/{self.duracion_foco_minutos} min"
        elif self.modo == ModoConversacion.TERAPEUTA:
            base += f" | Pregunta {self.paso_terapeuta}/{len(self.PREGUNTAS_TERAPEUTA)}"
        elif self.modo == ModoConversacion.SILENCIOSO:
            base += " | No enviar notificaciones proactivas"

        base += "]"
        return base

    def get_instruccion_modo(self) -> str:
        """Instrucción específica para el LLM según el modo activo."""
        if self.modo == ModoConversacion.ESCUCHA_PROFUNDA:
            return (
                f"INSTRUCCIÓN MODO ESCUCHA PROFUNDA: El usuario necesita ser escuchado. "
                f"Mantén el hilo del tema '{self.tema_activo or 'emocional'}'. "
                f"Responde con alta empatía, haz preguntas abiertas, NO cambies de tema. "
                f"NO ofrezcas soluciones inmediatas a menos que el usuario las pida."
            )
        elif self.modo == ModoConversacion.TRABAJO_PROFUNDO:
            mins = self.tiempo_en_foco() or 0
            return (
                f"INSTRUCCIÓN MODO FOCO: El usuario está en modo concentración ({mins}min transcurridos). "
                f"Responde de forma MUY breve (1 frase). No hagas preguntas adicionales."
            )
        elif self.modo == ModoConversacion.TERAPEUTA:
            return (
                f"INSTRUCCIÓN MODO TERAPEUTA: Estás en una sesión de reflexión guiada (paso {self.paso_terapeuta}). "
                f"Responde con empatía a lo que el usuario compartió, "
                f"valida su experiencia brevemente (1-2 frases), "
                f"luego la siguiente pregunta ya estará añadida al mensaje."
            )
        elif self.modo == ModoConversacion.SILENCIOSO:
            return "INSTRUCCIÓN MODO SILENCIOSO: Responde normalmente pero sin agregar preguntas adicionales."
        return ""


# ─── SINGLETON GLOBAL ──────────────────────────────────────────────────────────
conversation_state_manager = ConversationStateManager()
