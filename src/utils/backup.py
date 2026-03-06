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
    except Exception as e:
        logger.error(f"Fallo al crear backup de memoria: {e}")

if __name__ == "__main__":
    crear_backup()
