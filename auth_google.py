import os
import sys
import logging

# Configuración de logging simple para este script standalone
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# Ensure requirements are met
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    logging.info("Dependencias de Google no encontradas. Instalando...")
    # Usar sys.executable para asegurar que se usa el pip del entorno correcto
    os.system(f'"{sys.executable}" -m pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib')
    from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/tasks'
]

def authenticate():
    """
    Ejecuta el flujo de autenticación de OAuth2 de Google para obtener un token.json.
    """
    if os.path.exists('token.json'):
        logging.warning("token.json ya existe. Se borrará para generar uno nuevo.")
        os.remove('token.json')
        
    if not os.path.exists('credentials.json'):
        logging.error("FATAL: No se encontró el archivo 'credentials.json'. Descárgalo desde Google Cloud Console.")
        return
        
    logging.info("Iniciando flujo de autenticación de Google...")
    logging.info("Se abrirá una ventana en tu navegador web. Por favor, inicia sesión y concede los permisos solicitados.")
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        # run_local_server es para ejecución local. Para un servidor, el flujo es diferente.
        creds = flow.run_local_server(port=0)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
        logging.info("\n✅ ¡Éxito! token.json generado correctamente. Jarvis ahora tiene acceso a Google Calendar y Tasks.")
    except Exception as e:
        logging.error(f"Ocurrió un error durante la autenticación: {e}", exc_info=True)

if __name__ == '__main__':
    authenticate()
