"""
HERRAMIENTAS DE MEMORIA.
Funciones que Gemini puede invocar para leer/escribir JSONs.
"""

import logging
from typing import Dict, Any
from src.data import db_handler, schemas
from datetime import datetime

logger = logging.getLogger("tool_memory")

async def async_ejecutar_memoria(datos: Dict[str, Any]) -> str:
    """
    Versión asíncrona para manejar la persistencia de datos solicitada por la IA.
    """
    if not datos or "archivo" not in datos or "accion" not in datos:
        return "Error: La IA no especificó qué archivo actualizar."

    archivo = datos["archivo"]
    accion = datos["accion"]
    contenido = datos.get("contenido", {})

    try:
        if archivo == "proyectos":
            gestor = await db_handler.async_read_data("proyectos.json", schemas.GestorProyectos)
            
            if accion == "nuevo_proyecto":
                nuevo_proy = schemas.Proyecto(**contenido)
                gestor.proyectos_activos[nuevo_proy.nombre] = nuevo_proy
                await db_handler.async_save_data("proyectos.json", gestor)
                return f"Proyecto '{nuevo_proy.nombre}' creado exitosamente."
                
            elif accion == "consultar_proyecto":
                nombre_proy = contenido.get("nombre")
                if not nombre_proy or nombre_proy not in gestor.proyectos_activos:
                    proyectos_disp = ", ".join(gestor.proyectos_activos.keys())
                    return f"Error: Proyecto '{nombre_proy}' no encontrado. Proyectos disponibles: {proyectos_disp}"
                
                proy_actual = gestor.proyectos_activos[nombre_proy]
                return f"Detalles del proyecto '{nombre_proy}':\n" + proy_actual.model_dump_json(indent=2)

            elif accion == "actualizar_proyecto":
                nombre_proy = contenido.get("nombre")
                if not nombre_proy or nombre_proy not in gestor.proyectos_activos:
                    return f"Error: Proyecto '{nombre_proy}' no encontrado."
                
                proy_actual = gestor.proyectos_activos[nombre_proy]
                if "estado_actual" in contenido:
                    proy_actual.estado_actual = contenido["estado_actual"]
                if "descripcion" in contenido:
                    proy_actual.descripcion = contenido["descripcion"]
                if "nueva_tarea" in contenido:
                    import uuid
                    task_data = contenido["nueva_tarea"]
                    if "id" not in task_data or task_data["id"] in [t.id for t in proy_actual.tareas_pendientes]:
                        task_data["id"] = str(uuid.uuid4())[:8]
                    nueva_tarea = schemas.Tarea(**task_data)
                    proy_actual.tareas_pendientes.append(nueva_tarea)
                proy_actual.ultima_actualizacion = datetime.now()
                await db_handler.async_save_data("proyectos.json", gestor)
                return f"Proyecto '{nombre_proy}' actualizado exitosamente."

            elif accion == "eliminar_proyecto":
                nombre_proy = contenido.get("nombre")
                if nombre_proy in gestor.proyectos_activos:
                    del gestor.proyectos_activos[nombre_proy]
                    await db_handler.async_save_data("proyectos.json", gestor)
                    return f"Proyecto '{nombre_proy}' eliminado exitosamente."
                return f"Error: Proyecto '{nombre_proy}' no encontrado."

        elif archivo == "bitacora":
            gestor_bitacora = await db_handler.async_read_data("bitacora.json", schemas.GestorBitacora)
            hoy_str = datetime.now().strftime('%Y-%m-%d')
            
            if accion == "actualizar_bitacora":
                if not gestor_bitacora.dia_actual or gestor_bitacora.dia_actual.fecha != hoy_str:
                    if gestor_bitacora.dia_actual:
                        gestor_bitacora.historico_dias[gestor_bitacora.dia_actual.fecha] = gestor_bitacora.dia_actual
                    gestor_bitacora.dia_actual = schemas.RegistroDiario(fecha=hoy_str, nivel_energia=5, estado_animo="Neutro")

                dia = gestor_bitacora.dia_actual
                if "nivel_energia" in contenido and contenido["nivel_energia"] is not None:
                    try:
                        dia.nivel_energia = int(contenido["nivel_energia"])
                    except (ValueError, TypeError):
                        pass
                if "estado_animo" in contenido and contenido["estado_animo"] is not None:
                    dia.estado_animo = str(contenido["estado_animo"])
                if "nuevo_evento" in contenido: dia.eventos_importantes.append(contenido["nuevo_evento"])
                if "notas_ia" in contenido: dia.notas_ia = contenido["notas_ia"]
                await db_handler.async_save_data("bitacora.json", gestor_bitacora)
                return "Bitácora actualizada exitosamente."

        elif archivo == "persona":
            persona = await db_handler.async_read_data("persona.json", schemas.Persona)
            
            if accion == "actualizar_persona":
                if "nombre" in contenido: persona.nombre = contenido["nombre"]
                if "edad" in contenido: persona.edad = contenido["edad"]
                if "profesion" in contenido: persona.profesion = contenido["profesion"]
                if "nuevo_valor" in contenido and contenido["nuevo_valor"] not in persona.valores_clave:
                    persona.valores_clave.append(contenido["nuevo_valor"])
                if "nueva_meta" in contenido and contenido["nueva_meta"] not in persona.metas_largo_plazo:
                    persona.metas_largo_plazo.append(contenido["nueva_meta"])
                await db_handler.async_save_data("persona.json", persona)
                return "Perfil de usuario (persona) actualizado exitosamente."

        elif archivo == "contexto":
            contexto = await db_handler.async_read_data("contexto.json", schemas.GestorContexto)
            
            if accion == "nuevo_recordatorio":
                if not contenido.get("contexto_asociado"):
                    contenido["contexto_asociado"] = "general"
                nuevo_record = schemas.Recordatorio(**contenido)
                contexto.recordatorios_pendientes.append(nuevo_record)
                await db_handler.async_save_data("contexto.json", contexto)
                return f"Recordatorio para '{nuevo_record.contexto_asociado}' guardado."
                
            elif accion == "marcar_completado":
                id_rec = contenido.get("id")
                for rec in contexto.recordatorios_pendientes:
                    if rec.id == id_rec:
                        rec.completado = True
                        await db_handler.async_save_data("contexto.json", contexto)
                        return f"Recordatorio '{id_rec}' completado."
                return f"No se encontró el recordatorio '{id_rec}'."

        elif archivo == "largo_plazo":
            from src.data.vector_db import vector_db
            if accion == "guardar_recuerdo":
                texto = contenido.get("texto")
                tipo = contenido.get("tipo", "general")
                if texto:
                    return await vector_db.async_agregar_recuerdo(texto, tipo)
                return "Error: No se proporcionó texto para el recuerdo."

        return f"Acción '{accion}' en archivo '{archivo}' no reconocida o no soportada."

    except Exception as e:
        logger.error(f"Error al ejecutar memoria async: {e}", exc_info=True)
        return f"Fallo crítico al modificar memoria async: {str(e)}"

def ejecutar_memoria(datos: Dict[str, Any]) -> str:
    """
    Maneja la persistencia de datos solicitada por la IA.
    Aplica: Atomicidad (db_handler) y Validación (schemas).
    """
    if not datos or "archivo" not in datos or "accion" not in datos:
        return "Error: La IA no especificó qué archivo actualizar."

    archivo = datos["archivo"]
    accion = datos["accion"] # 'nuevo_proyecto', 'actualizar_proyecto', 'actualizar_bitacora', 'actualizar_persona'
    contenido = datos.get("contenido", {})

    try:
        # --- PROYECTOS ---
        if archivo == "proyectos":
            gestor = db_handler.read_data("proyectos.json", schemas.GestorProyectos)
            
            if accion == "nuevo_proyecto":
                nuevo_proy = schemas.Proyecto(**contenido)
                gestor.proyectos_activos[nuevo_proy.nombre] = nuevo_proy
                db_handler.save_data("proyectos.json", gestor)
                return f"Proyecto '{nuevo_proy.nombre}' creado exitosamente."
                
            elif accion == "consultar_proyecto":
                nombre_proy = contenido.get("nombre")
                if not nombre_proy or nombre_proy not in gestor.proyectos_activos:
                    proyectos_disp = ", ".join(gestor.proyectos_activos.keys())
                    return f"Error: Proyecto '{nombre_proy}' no encontrado. Proyectos disponibles: {proyectos_disp}"
                
                proy_actual = gestor.proyectos_activos[nombre_proy]
                return f"Detalles del proyecto '{nombre_proy}':\n" + proy_actual.model_dump_json(indent=2)
                
            elif accion == "actualizar_proyecto":
                nombre_proy = contenido.get("nombre")
                if not nombre_proy or nombre_proy not in gestor.proyectos_activos:
                    return f"Error: Proyecto '{nombre_proy}' no encontrado."
                
                proy_actual = gestor.proyectos_activos[nombre_proy]
                # Actualizar campos permitidos
                if "estado_actual" in contenido:
                    proy_actual.estado_actual = contenido["estado_actual"]
                if "descripcion" in contenido:
                    proy_actual.descripcion = contenido["descripcion"]
                
                # Actualizar tareas
                if "nueva_tarea" in contenido:
                    nueva_tarea = schemas.Tarea(**contenido["nueva_tarea"])
                    proy_actual.tareas_pendientes.append(nueva_tarea)
                    
                proy_actual.ultima_actualizacion = datetime.now()
                db_handler.save_data("proyectos.json", gestor)
                return f"Proyecto '{nombre_proy}' actualizado exitosamente."

            elif accion == "eliminar_proyecto":
                nombre_proy = contenido.get("nombre")
                if nombre_proy in gestor.proyectos_activos:
                    del gestor.proyectos_activos[nombre_proy]
                    db_handler.save_data("proyectos.json", gestor)
                    return f"Proyecto '{nombre_proy}' eliminado exitosamente."
                return f"Error: Proyecto '{nombre_proy}' no encontrado."

        # --- BITACORA ---
        elif archivo == "bitacora":
            gestor_bitacora = db_handler.read_data("bitacora.json", schemas.GestorBitacora)
            hoy_str = datetime.now().strftime('%Y-%m-%d')
            
            if accion == "actualizar_bitacora":
                # Si no hay registro de hoy, lo creamos
                if not gestor_bitacora.dia_actual or gestor_bitacora.dia_actual.fecha != hoy_str:
                    # Guardamos el día anterior en el histórico si existía
                    if gestor_bitacora.dia_actual:
                        gestor_bitacora.historico_dias[gestor_bitacora.dia_actual.fecha] = gestor_bitacora.dia_actual
                    
                    gestor_bitacora.dia_actual = schemas.RegistroDiario(
                        fecha=hoy_str,
                        nivel_energia=5,
                        estado_animo="Neutro"
                    )

                dia = gestor_bitacora.dia_actual
                if "nivel_energia" in contenido and contenido["nivel_energia"] is not None:
                    try:
                        dia.nivel_energia = int(contenido["nivel_energia"])
                    except (ValueError, TypeError):
                        pass
                if "estado_animo" in contenido and contenido["estado_animo"] is not None:
                    dia.estado_animo = str(contenido["estado_animo"])
                if "nuevo_evento" in contenido:
                    dia.eventos_importantes.append(contenido["nuevo_evento"])
                if "notas_ia" in contenido:
                    dia.notas_ia = contenido["notas_ia"]
                    
                db_handler.save_data("bitacora.json", gestor_bitacora)
                return "Bitácora actualizada exitosamente."

        # --- PERSONA ---
        elif archivo == "persona":
            persona = db_handler.read_data("persona.json", schemas.Persona)
            
            if accion == "actualizar_persona":
                if "edad" in contenido:
                    persona.edad = contenido["edad"]
                if "profesion" in contenido:
                    persona.profesion = contenido["profesion"]
                if "nuevo_valor" in contenido:
                    if contenido["nuevo_valor"] not in persona.valores_clave:
                        persona.valores_clave.append(contenido["nuevo_valor"])
                if "nueva_meta" in contenido:
                    if contenido["nueva_meta"] not in persona.metas_largo_plazo:
                        persona.metas_largo_plazo.append(contenido["nueva_meta"])
                        
                db_handler.save_data("persona.json", persona)
                return "Perfil de usuario (persona) actualizado exitosamente."

        # --- CONTEXTO / RECORDATORIOS RAPIDOS ---
        elif archivo == "contexto":
            contexto = db_handler.read_data("contexto.json", schemas.GestorContexto)
            
            if accion == "nuevo_recordatorio":
                nuevo_record = schemas.Recordatorio(**contenido)
                contexto.recordatorios_pendientes.append(nuevo_record)
                db_handler.save_data("contexto.json", contexto)
                return f"Recordatorio para '{nuevo_record.contexto_asociado}' guardado."
                
            elif accion == "marcar_completado":
                id_rec = contenido.get("id")
                for rec in contexto.recordatorios_pendientes:
                    if rec.id == id_rec:
                        rec.completado = True
                        db_handler.save_data("contexto.json", contexto)
                        return f"Recordatorio '{id_rec}' completado."
                return f"No se encontró el recordatorio '{id_rec}'."

        # --- MEMORIA A LARGO PLAZO (VECTORIAL) ---
        elif archivo == "largo_plazo":
            from src.data.vector_db import vector_db
            if accion == "guardar_recuerdo":
                texto = contenido.get("texto")
                tipo = contenido.get("tipo", "general")
                if texto:
                    return vector_db.agregar_recuerdo(texto, tipo)
                return "Error: No se proporcionó texto para el recuerdo."

        return f"Acción '{accion}' en archivo '{archivo}' no reconocida o no soportada."

    except Exception as e:
        logger.error(f"Error al ejecutar memoria: {e}", exc_info=True)
        return f"Fallo crítico al modificar memoria: {str(e)}"
