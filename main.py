# --- TRAZABILIDAD ---
# Cargar la configuración de logging ANTES que cualquier otro módulo
from src.utils import logger_config
import logging

from src.INTERFACES.telegram_bot import iniciar_bot
from src.core.cron import iniciar_cron, detener_cron

logger = logging.getLogger("main")

def main():
    logger.info("\n"
        "       _   _    _  ______     _____  _____   __      _____  \n"
        "      | | | |  | | | ___ \\   |  _  |/  ___|  \\ \\    / /__ \\ \n"
        "      | | | |  | | | |_/ /   | | | |\\ `--.    \\ \\  / /   ) |\n"
        "  _   | | | |/\\| | |    /    | | | | `--. \\    \\ \\/ /   / / \n"
        " | |__| | \\  /\\  / | |\\ \\    \\ \\_/ //\\__/ /     \\  /   |_|  \n"
        "  \\____/   \\/  \\/  \\_| \\_|    \\___/ \\____/       \\/    (_)  \n"
    )
    
    logger.info("=== INICIANDO SECUENCIA DE ARRANQUE ===")
    
    try:
        # Arrancar la interfaz principal (bloqueante)
        # El cron se inicia automáticamente dentro del bot a través de post_init
        iniciar_bot()
        
    except KeyboardInterrupt:
        logger.info("Apagado manual solicitado por el usuario.")
    except Exception as e:
        logger.critical(f"FALLO CATASTRÓFICO EN MAIN: {e}", exc_info=True)
    finally:
        logger.info("=== SISTEMA APAGADO ===")

if __name__ == '__main__':
    main()