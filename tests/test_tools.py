import pytest
from unittest.mock import MagicMock, patch

# Herramientas a probar
from src.TOOLS.tool_agenda import ToolAgenda
from src.TOOLS.tool_system import ejecutar_herramienta_sistema

@pytest.fixture
def mock_google_build():
    """Fixture para mockear el constructor de servicios de Google API."""
    with patch('src.TOOLS.tool_agenda.build') as mock_build:
        yield mock_build

def test_agenda_crear_evento_ok(mock_google_build):
    """Prueba la creación de un evento en Calendar cuando no hay duplicados."""
    # Configurar el mock para el servicio de Calendar
    mock_service = MagicMock()
    mock_google_build.return_value = mock_service
    
    # Simular que no se encontraron eventos existentes
    mock_service.events.return_value.list.return_value.execute.return_value = {'items': []}
    
    # Simular la respuesta del método insert
    mock_service.events.return_value.insert.return_value.execute.return_value = {
        'summary': 'Test Event',
        'htmlLink': 'http://test.link'
    }

    agenda = ToolAgenda()
    # Forzar credenciales mockeadas para que la herramienta funcione
    agenda.creds = MagicMock() 
    
    res = agenda.crear_evento_calendar("Test Event", "2024-01-01T10:00:00")
    
    assert "Evento 'Test Event' agendado" in res
    # Asegurarse de que se llamó al método insert
    mock_service.events.return_value.insert.assert_called_once()

def test_agenda_crear_evento_idempotencia(mock_google_build):
    """Prueba que no se cree un evento si ya existe uno similar (idempotencia)."""
    mock_service = MagicMock()
    mock_google_build.return_value = mock_service

    # Simular que SÍ se encontró un evento existente
    mock_service.events.return_value.list.return_value.execute.return_value = {
        'items': [{'summary': 'Test Event'}]
    }

    agenda = ToolAgenda()
    agenda.creds = MagicMock()
    
    res = agenda.crear_evento_calendar("Test Event", "2024-01-01T10:00:00")
    
    assert "Ya existe un evento similar" in res
    # El método insert NO debe ser llamado
    mock_service.events.return_value.insert.assert_not_called()

def test_agenda_crear_tarea_idempotencia(mock_google_build):
    """Prueba que no se cree una tarea si ya existe una con el mismo título."""
    mock_service = MagicMock()
    mock_google_build.return_value = mock_service

    # Simular que ya existe una tarea con ese nombre
    mock_service.tasks.return_value.list.return_value.execute.return_value = {
        'items': [{'title': 'Comprar Leche'}]
    }

    agenda = ToolAgenda()
    agenda.creds = MagicMock()

    res = agenda.crear_tarea("Comprar Leche")

    assert "Ya existe una tarea pendiente" in res
    mock_service.tasks.return_value.insert.assert_not_called()

@patch('src.TOOLS.tool_system.DDGS')
def test_system_buscar_web(mock_ddgs):
    """Prueba la herramienta de búsqueda web, mockeando la librería DDGS."""
    # Configurar el mock para el context manager y los resultados
    mock_ddgs_instance = mock_ddgs.return_value.__enter__.return_value
    mock_ddgs_instance.text.return_value = [
        {'title': 'Resultado 1', 'body': 'Cuerpo 1', 'href': 'url1'},
        {'title': 'Resultado 2', 'body': 'Cuerpo 2', 'href': 'url2'},
    ]

    res = ejecutar_herramienta_sistema("buscar_web", {"query": "test"})

    assert "Resultados web para 'test'" in res
    assert "Resultado 1" in res
    assert "Cuerpo 2" in res
    mock_ddgs_instance.text.assert_called_once_with("test", max_results=3)
