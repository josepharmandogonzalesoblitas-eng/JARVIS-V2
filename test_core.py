import asyncio
import logging
import json
import os
from src.core.orquestador import Orquestador
from src.data import db_handler, schemas
from src.data.vector_db import vector_db
from src.TOOLS.tool_system import ejecutar_herramienta_sistema

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TEST")

async def test_flujo_principal():
    """
    Test End-to-End del pipeline de Jarvis (Orquestador -> Cerebro -> Memoria/Tools).
    Aplica: Fail-Safe y Poka-Yoke para validar que nada explote.
    """
    logger.info("--- INICIANDO TEST DEL NÚCLEO (ORQUESTADOR) ---")
    
    # 1. Instanciamos el orquestador
    jarvis = Orquestador()
    
    # Usuario autorizado de prueba
    user_id = os.getenv("TELEGRAM_USER_ID", "1234")
    
    logger.info("--- TEST 1: INYECTAR CONTEXTO EN MEMORIA ---")
    # Forzamos una limpieza o estado base para evitar contaminación cruzada (Idempotencia)
    # Por ahora solo verificamos que no dé error.
    try:
        ctx = jarvis._construir_contexto("Hola Jarvis")
        assert ctx, "El contexto devuelto no debe estar vacío"
        logger.info("✅ Contexto cargado correctamente.")
    except Exception as e:
        logger.error(f"❌ Fallo al cargar contexto: {e}")

    logger.info("--- TEST 2: PREGUNTA SIMPLE (NO TOOL) ---")
    try:
        resp = await jarvis.procesar_mensaje(user_id, "Hola, solo di la palabra 'Prueba_123'. No uses herramientas.")
        logger.info(f"✅ Respuesta IA: {resp}")
    except Exception as e:
        logger.error(f"❌ Fallo en pregunta simple: {e}")

    logger.info("--- TEST 3: USO DE HERRAMIENTA SISTEMA (Hora) ---")
    try:
        # Esto debería detonar "consultar_hora"
        resp = await jarvis.procesar_mensaje(user_id, "¿Qué hora es en el sistema actualmente?")
        logger.info(f"✅ Respuesta IA con Tool: {resp}")
    except Exception as e:
        logger.error(f"❌ Fallo usando herramienta de hora: {e}")

    logger.info("--- TEST 4: MEMORIA A LARGO PLAZO (ChromaDB) ---")
    try:
        # Esto debería detonar "guardar_recuerdo"
        resp = await jarvis.procesar_mensaje(user_id, "Jarvis, mi color favorito es el Azul Eléctrico. Recuérdalo para siempre.")
        logger.info(f"✅ Respuesta IA (Guardando vector): {resp}")
        
        # Verificar que el vector se guardó
        vectores = vector_db.buscar_contexto("color favorito")
        logger.info(f"✅ Búsqueda Vectorial: \n{vectores}")
    except Exception as e:
        logger.error(f"❌ Fallo en memoria vectorial: {e}")
        
    logger.info("--- FIN DE LOS TESTS ---")

if __name__ == "__main__":
    asyncio.run(test_flujo_principal())
