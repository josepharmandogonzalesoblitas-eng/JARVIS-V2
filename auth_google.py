import os
import sys

# Ensure requirements are met
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Installing requirements...")
    os.system(f"{sys.executable} -m pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/tasks'
]

def authenticate():
    if os.path.exists('token.json'):
        print("token.json ya existe. Borrando para generar uno nuevo...")
        os.remove('token.json')
        
    if not os.path.exists('credentials.json'):
        print("Error: No se encontró credentials.json en la carpeta.")
        return
        
    print("Iniciando flujo de autenticación de Google...")
    print("Se abrirá una ventana en tu navegador web. Por favor, inicia sesión y concédele permisos a Jarvis.")
    
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
        
    print("\n✅ ¡Éxito! token.json generado correctamente. Jarvis ya tiene acceso a Google Calendar y Tasks.")

if __name__ == '__main__':
    authenticate()