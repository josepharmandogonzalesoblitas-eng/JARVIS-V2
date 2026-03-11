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

SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/tasks'
]

class ToolAgenda:
    def __init__(self):
        self.creds = None
        self._authenticate()
        
    def _authenticate(self):
        if os.path.exists('token.json'):
            self.creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    logger.error(f"Error refrescando token: {e}")
                    self.creds = None
            else:
                self.creds = None

    def crear_evento_calendar(self, resumen: str, fecha_inicio_iso: str, duracion_minutos: int = 60, descripcion: str = "") -> str:
        if not self.creds:
            return "Error: No hay conexión con Google Calendar (falta token.json)."
            
        try:
            service = build('calendar', 'v3', credentials=self.creds)
            inicio = datetime.datetime.fromisoformat(fecha_inicio_iso.replace('Z', '+00:00'))
            fin = inicio + datetime.timedelta(minutes=duracion_minutos)
            
            time_min = (inicio - datetime.timedelta(minutes=5)).isoformat() + "Z"
            time_max = (inicio + datetime.timedelta(minutes=5)).isoformat() + "Z"
            
            existing_events = service.events().list(
                calendarId='primary', timeMin=time_min, timeMax=time_max, q=resumen, singleEvents=True
            ).execute()
            
            if existing_events.get('items'):
                return f"⚠️ Ya existe un evento similar agendado para esa hora: '{resumen}'."

            evento = {
                'summary': resumen, 'description': descripcion,
                'start': {'dateTime': inicio.isoformat(), 'timeZone': 'America/Lima'},
                'end': {'dateTime': fin.isoformat(), 'timeZone': 'America/Lima'},
            }
            
            event = service.events().insert(calendarId='primary', body=evento).execute()
            return f"✅ Evento '{resumen}' agendado. Enlace: {event.get('htmlLink')}"
        except Exception as e:
            return f"❌ Fallo al agendar en Calendar: {str(e)}"

    def crear_tarea(self, titulo: str, notas: str = "", fecha_vencimiento_iso: Optional[str] = None) -> str:
        if not self.creds:
            return "Error: No hay conexión con Google Tasks (falta token.json)."
        try:
            service = build('tasks', 'v1', credentials=self.creds)
            
            task_list = service.tasks().list(tasklist='@default', showCompleted=False).execute()
            for task in task_list.get('items', []):
                if task.get('title', '').strip().lower() == titulo.strip().lower():
                    return f"⚠️ Ya existe una tarea pendiente con ese nombre: '{titulo}'."

            tarea = {'title': titulo, 'notes': notas}
            if fecha_vencimiento_iso:
                tarea['due'] = fecha_vencimiento_iso

            result = service.tasks().insert(tasklist='@default', body=tarea).execute()
            return f"✅ Tarea '{titulo}' añadida a Google Tasks."
        except Exception as e:
            return f"❌ Fallo al añadir tarea: {str(e)}"

    def borrar_eventos_mes_actual(self, texto_a_buscar: str) -> str:
        if not self.creds:
            return "Error: No hay conexión con Google Calendar (falta token.json)."
        try:
            service = build('calendar', 'v3', credentials=self.creds)
            
            now = datetime.datetime.now()
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = (start_of_month.replace(day=28) + datetime.timedelta(days=4))
            end_of_month = next_month - datetime.timedelta(days=next_month.day)
            
            time_min = start_of_month.isoformat() + 'Z'
            time_max = end_of_month.isoformat() + 'Z'

            events_result = service.events().list(
                calendarId='primary', timeMin=time_min, timeMax=time_max, q=texto_a_buscar, singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                return f"No encontré eventos con '{texto_a_buscar}' en el calendario para este mes."

            for event in events:
                service.events().delete(calendarId='primary', eventId=event['id']).execute()
            
            return f"✅ He borrado {len(events)} eventos que contenían '{texto_a_buscar}'."
        except Exception as e:
            return f"❌ Fallo al borrar eventos: {str(e)}"
