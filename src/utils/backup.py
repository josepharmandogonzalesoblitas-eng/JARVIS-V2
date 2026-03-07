import os
import shutil
from datetime import datetime
import logging

logger = logging.getLogger("backup")

def crear_backup():
    """Crea un ZIP de la carpeta MEMORIA y lo guarda en LOGS/backups."""
    try:
        origen = "MEMORIA"
        destino_base = "LOGS/backups"
        
        if not os.path.exists(origen):
            logger.warning("No se encontró la carpeta MEMORIA para hacer backup.")
            return

        os.makedirs(destino_base, exist_ok=True)
        
        fecha = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_zip = f"memoria_backup_{fecha}"
        ruta_zip = os.path.join(destino_base, nombre_zip)
        
        # shutil.make_archive añade el .zip automáticamente
        shutil.make_archive(ruta_zip, 'zip', origen)
        logger.info(f"Backup creado exitosamente: {ruta_zip}.zip")
        
        # Eliminar backups de más de 7 días para no saturar el servidor (Rolling Backups)
        limpiar_backups_antiguos(destino_base, dias_retencion=7)
        
    except Exception as e:
        logger.error(f"Fallo al crear backup de memoria: {e}")

def limpiar_backups_antiguos(directorio: str, dias_retencion: int = 7):
    """
    Busca y elimina archivos en el directorio que sean más viejos que la retención configurada.
    """
    ahora = datetime.now().timestamp()
    eliminados = 0
    for archivo in os.listdir(directorio):
        ruta_archivo = os.path.join(directorio, archivo)
        if os.path.isfile(ruta_archivo) and archivo.startswith("memoria_backup_"):
            # Si el archivo tiene más de N días (días * 24h * 60m * 60s)
            tiempo_modificacion = os.path.getmtime(ruta_archivo)
            if ahora - tiempo_modificacion > (dias_retencion * 86400):
                try:
                    os.remove(ruta_archivo)
                    eliminados += 1
                except Exception as e:
                    logger.error(f"No se pudo eliminar el backup antiguo {archivo}: {e}")
                    
    if eliminados > 0:
        logger.info(f"Limpieza completada: Se eliminaron {eliminados} backups de más de {dias_retencion} días.")

if __name__ == "__main__":
    crear_backup()
