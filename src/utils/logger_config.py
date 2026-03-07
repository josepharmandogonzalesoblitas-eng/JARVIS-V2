import logging
import logging.handlers
import os

def setup_logging():
    """
    Configura un sistema de logging centralizado, rotativo y estructurado.
    """
    LOG_DIR = "LOGS"
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    log_formatter = logging.Formatter(
        "%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s] [%(name)-15.15s] %(message)s"
    )
    
    # --- Handler para Archivo Rotativo ---
    # Rotará cuando el log alcance 1MB, manteniendo 3 archivos de respaldo.
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, "jarvis_v2.log"),
        maxBytes=1*1024*1024, 
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)

    # --- Handler para la Consola ---
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)

    # --- Configuración del Logger Raíz ---
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Evitar duplicación de handlers si la función es llamada más de una vez
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

    logging.info("=========================================")
    logging.info("Sistema de Logging Inicializado")
    logging.info("=========================================")

# Ejecutar la configuración al importar el módulo
setup_logging()
