import os
import datetime
import logging
from typing import Dict, Any, Optional

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    logging.warning("Faltan dependencias de Google. Instala: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")

logger = logging.getLogger("tool_agenda")

# Permisos requeridos para Calendar y Tasks
SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/tasks'
]

class ToolAgenda:
    def __init__(self):
        self.creds = None
        self._authenticate()
        
    def _authenticate(self):
        """Autentica con la API de Google usando credentials.json."""
        if os.path.exists('token.json'):
            self.creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        # Si no hay credenciales válidas, no crasheamos, pero avisamos.
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Error refrescando token: {e}")
                    self.creds = None
            else:
                if os.path.exists('credentials.json'):
                    logger.info("Iniciando flujo de autenticación de Google...")
                    # Este flujo abrirá el navegador localmente.
                    # IMPORTANTE: En un VPS, esto no funcionará. El token.json debe generarse localmente y subirse.
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                    self.creds = flow.run_local_server(port=0)
                    with open('token.json', 'w') as token:
                        token.write(self.creds.to_json())
                else:
                    logger.warning("No se encontró credentials.json. Google Calendar/Tasks desactivado.")
                    self.creds = None

    def crear_evento_calendar(self, resumen: str, fecha_inicio_iso: str, duracion_minutos: int = 60, descripcion: str = "") -> str:
        """Crea un evento en Google Calendar, previniendo duplicados (Idempotencia)."""
        if not self.creds:
            return "Error: No hay conexión con Google Calendar (falta token.json)."
            
        try:
            service = build('calendar', 'v3', credentials=self.creds)
            
            inicio = datetime.datetime.fromisoformat(fecha_inicio_iso.replace('Z', '+00:00'))
            fin = inicio + datetime.timedelta(minutes=duracion_minutos)
            
            # IDEMPOTENCIA: Buscar eventos existentes en una ventana de +/- 5 minutos
            time_min = (inicio - datetime.timedelta(minutes=5)).isoformat() + "Z"
            time_max = (inicio + datetime.timedelta(minutes=5)).isoformat() + "Z"
            
            existing_events = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                q=resumen, # Filtrar por el mismo resumen
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            if existing_events.get('items'):
                logger.warning(f"IDEMPOTENCIA: Evento '{resumen}' duplicado detectado. No se creará uno nuevo.")
                return f"⚠️ Ya existe un evento similar agendado para esa hora: '{resumen}'."

            evento = {
                'summary': resumen,
                'description': descripcion,
                'start': {'dateTime': inicio.isoformat(), 'timeZone': 'America/Lima'},
                'end': {'dateTime': fin.isoformat(), 'timeZone': 'America/Lima'},
                'reminders': {'useDefault': False, 'overrides': [{'method': 'popup', 'minutes': 10}]},
            }
            
            event = service.events().insert(calendarId='primary', body=evento).execute()
            return f"✅ Evento '{resumen}' agendado. Enlace: {event.get('htmlLink')}"

        except Exception as e:
            logger.error(f"Error en Calendar: {e}")
            return f"❌ Fallo al agendar en Calendar: {str(e)}"

    def crear_tarea(self, titulo: str, notas: str = "", fecha_vencimiento_iso: Optional[str] = None) -> str:
        """Añade una tarea a Google Tasks, previniendo duplicados (Idempotencia)."""
        if not self.creds:
            return "Error: No hay conexión con Google Tasks (falta token.json)."
            
        try:
            service = build('tasks', 'v1', credentials=self.creds)
            
            # IDEMPOTENCIA: Buscar si ya existe una tarea con el mismo título
            task_list = service.tasks().list(tasklist='@default', showCompleted=False).execute()
            for task in task_list.get('items', []):
                if task.get('title', '').strip().lower() == titulo.strip().lower():
                    logger.warning(f"IDEMPOTENCIA: Tarea '{titulo}' duplicada detectada. No se creará una nueva.")
                    return f"⚠️ Ya existe una tarea pendiente con ese nombre: '{titulo}'."

            tarea = {'title': titulo, 'notes': notas}
            if fecha_vencimiento_iso:
                tarea['due'] = fecha_vencimiento_iso

            result = service.tasks().insert(tasklist='@default', body=tarea).execute()
            return f"✅ Tarea '{titulo}' añadida a Google Tasks."
            
        except Exception as e:
            logger.error(f"Error en Tasks: {e}")
            return f"❌ Fallo al añadir tarea: {str(e)}"
