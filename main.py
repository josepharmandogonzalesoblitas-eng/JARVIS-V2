import logging
import sys
from src.INTERFACES.telegram_bot import iniciar_bot
from src.core.cron import iniciar_cron, detener_cron

# --- CONFIGURACIÓN DE LOGS (TRAZABILIDAD GLOBAL) ---
# Usamos Loguru si lo instalaste, o logging estándar.
# Vamos con logging estándar para máxima compatibilidad (KISS).

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("sistema.log"), # Persistencia de logs
        logging.StreamHandler(sys.stdout)   # Salida en consola
    ]
)

logger = logging.getLogger("MAIN")

def main():
    print("""
       _   _    _  ______     _____  _____   __      _____  
      | | | |  | | | ___ \   |  _  |/  ___|  \ \    / /__ \ 
      | | | |  | | | |_/ /   | | | |\ `--.    \ \  / /   ) |
  _   | | | |/\| | |    /    | | | | `--. \    \ \/ /   / / 
 | |__| | \  /\  / | |\ \    \ \_/ //\__/ /     \  /   |_|  
  \____/   \/  \/  \_| \_|    \___/ \____/       \/    (_)  
    """)
    
    logger.info("=== INICIANDO SECUENCIA DE ARRANQUE ===")
    
    try:
        # Iniciar CRON en segundo plano
        iniciar_cron()
        
        # Arrancar la interfaz principal (bloqueante)
        iniciar_bot()
        
    except KeyboardInterrupt:
        logger.info("Apagado manual solicitado por el usuario.")
    except Exception as e:
        logger.critical(f"FALLO CATASTRÓFICO EN MAIN: {e}", exc_info=True)
    finally:
        detener_cron()
        logger.info("=== SISTEMA APAGADO ===")

if __name__ == '__main__':
    main()