"""
MOTOR DE INTELIGENCIA EMOCIONAL DE JARVIS.

Responsabilidades:
1. Detectar crisis emocionales en tiempo real (por mensaje).
2. Detectar patrones negativos acumulados (por historial de bitácora).
3. Celebrar logros detectados automáticamente.
4. Gestionar conversaciones profundas con follow-up automático.
5. Verificar seguimientos pendientes.

Principios: No invasivo, empático, nunca alarmista sin evidencia.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger("emotion_engine")

# ─── VOCABULARIO DE SEÑALES ─────────────────────────────────────────────────

# Señales de crisis real (nivel 2) — requieren acción inmediata
PALABRAS_CRISIS = [
    "quiero morir", "no quiero vivir", "hacerme daño", "hacerme daño",
    "terminar con todo", "no vale la pena seguir", "sin salida", "suicid",
    "matarme", "quitarme la vida", "no hay razón para seguir"
]

# Señales de malestar emocional (nivel 1) — requieren empatía y seguimiento
PALABRAS_NEGATIVAS = [
    "triste", "tristeza", "solo", "soledad", "deprimid", "depresión",
    "angustia", "angustiad", "ansios", "ansiedad", "agotad", "agotamiento",
    "lloro", "lloré", "no puedo más", "todo va mal", "nada funciona",
    "inútil", "fracas", "desesper", "vacío", "sin motivación",
    "me siento mal", "horrible", "terrible", "no sirvo"
]

# Señales de logro (para celebración)
PALABRAS_LOGRO = [
    "terminé", "completé", "logré", "conseguí", "acabé", "finalicé",
    "aprobé", "gané", "superé", "lo hice", "pude", "funcionó",
    "completado", "aprendí", "lo conseguí", "lo logramos"
]

# Tipos de logro para personalizar la celebración
TIPOS_LOGRO = {
    "proyecto": ["terminé el proyecto", "completé el proyecto", "acabé el proyecto", "finalicé el proyecto"],
    "habito": ["días seguidos", "semanas seguidas", "semana seguida", "días consecutivos"],
    "estudio": ["aprobé", "aprendí", "estudié", "terminé el curso", "pasé el examen"],
    "personal": ["lo hice", "pude", "superé", "lo logré", "gané"]
}


class EmotionEngine:
    """
    Analiza el estado emocional del usuario y genera respuestas apropiadas.
    """

    def analizar_mensaje(self, texto: str) -> Dict[str, Any]:
        """
        Analiza un mensaje individual en busca de señales emocionales.

        Returns:
            {
                "nivel_crisis": 0|1|2,  # 0=normal, 1=alerta, 2=crisis
                "es_logro": bool,
                "tipo_logro": str|None,
                "negatividad_score": int,
                "palabras_detectadas": list
            }
        """
        texto_lower = texto.lower()

        # Nivel 2: Crisis real
        es_crisis = any(p in texto_lower for p in PALABRAS_CRISIS)

        # Nivel 1: Malestar
        negatividad_score = sum(1 for p in PALABRAS_NEGATIVAS if p in texto_lower)
        palabras_encontradas = [p for p in PALABRAS_NEGATIVAS if p in texto_lower]

        # Logros
        es_logro = any(p in texto_lower for p in PALABRAS_LOGRO)
        tipo_logro = None
        if es_logro:
            for tipo, frases in TIPOS_LOGRO.items():
                if any(f in texto_lower for f in frases):
                    tipo_logro = tipo
                    break
            if not tipo_logro:
                tipo_logro = "personal"

        nivel_crisis = 0
        if es_crisis:
            nivel_crisis = 2
        elif negatividad_score >= 2:
            nivel_crisis = 1

        return {
            "nivel_crisis": nivel_crisis,
            "es_logro": es_logro,
            "tipo_logro": tipo_logro,
            "negatividad_score": negatividad_score,
            "palabras_detectadas": palabras_encontradas
        }

    async def detectar_patron_negativo_historico(
        self,
        historial_reciente: list
    ) -> Tuple[int, int]:
        """
        Analiza la bitácora para detectar patrones negativos acumulados.

        Returns:
            (nivel_alerta, dias_negativos_consecutivos)
            nivel_alerta: 0=normal, 1=alerta (3+ días negativos)
        """
        try:
            from src.data import db_handler, schemas

            bitacora = await db_handler.async_read_data("bitacora.json", schemas.GestorBitacora)
            historico_sorted = sorted(bitacora.historico_dias.items(), reverse=True)

            dias_negativos = 0
            for fecha, registro in historico_sorted[:7]:  # últimos 7 días
                es_negativo = (
                    registro.nivel_energia <= 3
                    or any(p in registro.estado_animo.lower() for p in ["triste", "mal", "deprim", "solo", "ansios"])
                )
                if es_negativo:
                    dias_negativos += 1
                else:
                    break  # Solo contamos consecutivos

            # Incluir día actual
            if bitacora.dia_actual:
                dia_act = bitacora.dia_actual
                if (dia_act.nivel_energia <= 3
                        or any(p in dia_act.estado_animo.lower() for p in ["triste", "mal", "deprim"])):
                    dias_negativos += 1

            nivel = 1 if dias_negativos >= 3 else 0
            return nivel, dias_negativos

        except Exception as e:
            logger.warning(f"Error analizando patrón histórico: {e}")
            return 0, 0

    def generar_respuesta_crisis(self, nivel: int, nombre: str = "amigo") -> str:
        """
        Genera un mensaje empático y apropiado para el nivel de crisis.

        Args:
            nivel: 1=alerta, 2=crisis real
            nombre: Nombre del usuario para personalizar
        """
        if nivel == 2:
            return (
                f"⚠️ {nombre}, lo que describes suena muy serio y quiero que sepas que "
                f"no estás solo/a en esto. Por favor, habla con alguien de confianza ahora mismo.\n\n"
                f"🆘 *Línea de ayuda emocional:*\n"
                f"🇵🇪 Perú: *113 opción 5* (MINSA, gratis 24h)\n"
                f"🌎 Internacional: findahelpline.com\n\n"
                f"Estoy aquí contigo, pero necesitas apoyo humano real. ❤️"
            )
        elif nivel == 1:
            return (
                f"He notado que llevas varios días sintiéndote con el ánimo bajo, {nombre}. "
                f"Eso es completamente válido y tiene sentido que así se sienta. "
                f"¿Quieres contarme qué está pasando? Puedo escucharte sin juzgar, "
                f"o si prefieres, puedo ayudarte a organizarte para que la semana se sienta más manejable. 🤗"
            )
        return ""

    def generar_mensaje_celebracion(
        self,
        texto_usuario: str,
        nombre: str = "campeón"
    ) -> str:
        """
        Genera un mensaje de celebración personalizado según el tipo de logro.
        """
        texto_lower = texto_usuario.lower()

        # Determinar tipo de celebración
        if any(p in texto_lower for p in ["días seguidos", "semanas seguidas", "días consecutivos"]):
            # Detectar número de días
            import re
            nums = re.findall(r'\d+', texto_lower)
            num_str = nums[0] if nums else ""
            if num_str:
                return (
                    f"🔥 ¡*{num_str} días seguidos*! Eso no es suerte, es disciplina pura. "
                    f"¿Cómo te sientes física y mentalmente después de mantener eso?"
                )
            return "🔥 ¡Racha activa! La consistencia es el superpoder más subestimado. ¡Sigue así!"

        elif any(p in texto_lower for p in ["terminé el proyecto", "completé el proyecto", "acabé el proyecto"]):
            return (
                "🎉 ¡*Proyecto cerrado*! Eso merece una pausa real para reconocerlo. "
                "¿Qué fue lo más valioso que aprendiste en el proceso?"
            )

        elif any(p in texto_lower for p in ["aprobé", "pasé el examen", "gané"]):
            return (
                "🏆 ¡*Lo lograste*! El esfuerzo que pusiste detrás de este resultado no se ve, "
                "pero tú sí lo sabes. ¿Cómo lo vas a celebrar hoy?"
            )

        elif any(p in texto_lower for p in ["aprendí", "terminé el curso"]):
            return (
                "🧠 ¡Nuevo conocimiento adquirido! El aprendizaje constante es uno de tus mayores activos. "
                "¿Ya piensas cómo vas a aplicar esto?"
            )

        else:
            return (
                "✅ ¡Eso es progreso real! Cada paso cuenta, aunque a veces se sientan pequeños. "
                "Cuéntame más sobre esto. 💪"
            )

    async def registrar_crisis(self, nivel: int) -> None:
        """Registra una crisis detectada en el estado emocional del sistema."""
        try:
            from src.data import db_handler, schemas
            estado = await db_handler.async_read_data("estado_emocional.json", schemas.EstadoEmocionalSistema)
            if nivel >= 1:
                estado.ultima_crisis_detectada = datetime.now().strftime("%Y-%m-%d")
                estado.dias_negativos_consecutivos = max(estado.dias_negativos_consecutivos + 1, nivel)
            else:
                # Racha positiva: resetear contador
                if estado.dias_negativos_consecutivos > 0:
                    estado.dias_negativos_consecutivos = max(0, estado.dias_negativos_consecutivos - 1)
            await db_handler.async_save_data("estado_emocional.json", estado)
        except Exception as e:
            logger.warning(f"No se pudo registrar crisis en estado emocional: {e}")

    async def verificar_followups_pendientes(self) -> Optional[str]:
        """
        Verifica si hay conversaciones profundas con follow-up para hoy.

        Returns:
            Mensaje de follow-up si hay alguno pendiente para hoy, None si no.
        """
        try:
            from src.data import db_handler, schemas
            estado = await db_handler.async_read_data("estado_emocional.json", schemas.EstadoEmocionalSistema)

            hoy = datetime.now().strftime("%Y-%m-%d")
            for conv in estado.conversaciones_profundas:
                if not conv.completado and conv.fecha_followup == hoy:
                    # Marcar como completado para no repetir
                    conv.completado = True
                    await db_handler.async_save_data("estado_emocional.json", estado)

                    tipo_emoji = {
                        "salud": "🏥", "relacion": "❤️", "meta": "🎯",
                        "trabajo": "💼", "crisis": "💙", "personal": "🌱"
                    }.get(conv.tipo, "💬")

                    return (
                        f"{tipo_emoji} Hace unos días hablamos de algo importante: "
                        f'"{conv.resumen}"\n\n'
                        f"¿Cómo resultó eso? ¿Pudiste avanzar o resolver algo al respecto? "
                        f"Genuinamente me interesa saber."
                    )

            return None

        except Exception as e:
            logger.warning(f"Error verificando follow-ups: {e}")
            return None

    async def verificar_triggers_metas(self, historial_reciente: list) -> Optional[str]:
        """
        Verifica si alguna meta del usuario lleva más de 5 días sin ser mencionada.
        Genera un mensaje espontáneo si detecta una meta olvidada.

        Returns:
            Mensaje de recordatorio de meta, o None.
        """
        try:
            from src.data import db_handler, schemas

            persona = await db_handler.async_read_data("persona.json", schemas.Persona)
            if not persona.metas_largo_plazo:
                return None

            estado = await db_handler.async_read_data("estado_emocional.json", schemas.EstadoEmocionalSistema)
            hoy = datetime.now().strftime("%Y-%m-%d")

            # Verificar cada meta
            for meta in persona.metas_largo_plazo[:3]:  # Máximo 3 metas
                meta_lower = meta.lower()
                ultima_mencion = estado.metas_ultima_mencion.get(meta)

                if ultima_mencion:
                    dias_desde_mencion = (
                        datetime.strptime(hoy, "%Y-%m-%d") -
                        datetime.strptime(ultima_mencion, "%Y-%m-%d")
                    ).days

                    if dias_desde_mencion >= 5:
                        # Buscar si la meta fue mencionada en el historial reciente
                        meta_en_historial = any(
                            meta_lower in ex.get("u", "").lower()
                            for ex in historial_reciente[-20:]
                        )
                        if not meta_en_historial:
                            return (
                                f"💭 Hace {dias_desde_mencion} días no mencionas tu meta de "
                                f'"{meta}". ¿Cómo va eso? ¿Avanzaste, se complicó, o ya no es prioridad?'
                            )
                else:
                    # Primera vez que se registra: guardar fecha de hoy
                    estado.metas_ultima_mencion[meta] = hoy

            await db_handler.async_save_data("estado_emocional.json", estado)
            return None

        except Exception as e:
            logger.warning(f"Error verificando triggers de metas: {e}")
            return None

    @staticmethod
    async def actualizar_mencion_meta(texto: str) -> None:
        """
        Si el texto menciona alguna meta del usuario, actualiza la fecha de última mención.
        Llamar en cada mensaje procesado.
        """
        try:
            from src.data import db_handler, schemas
            persona = await db_handler.async_read_data("persona.json", schemas.Persona)
            if not persona.metas_largo_plazo:
                return

            texto_lower = texto.lower()
            metas_mencionadas = [
                meta for meta in persona.metas_largo_plazo
                if any(palabra in texto_lower for palabra in meta.lower().split()[:3])
            ]

            if metas_mencionadas:
                estado = await db_handler.async_read_data("estado_emocional.json", schemas.EstadoEmocionalSistema)
                hoy = datetime.now().strftime("%Y-%m-%d")
                for meta in metas_mencionadas:
                    estado.metas_ultima_mencion[meta] = hoy
                await db_handler.async_save_data("estado_emocional.json", estado)

        except Exception as e:
            logger.debug(f"Error actualizando mención de meta: {e}")


# Singleton global
emotion_engine = EmotionEngine()
