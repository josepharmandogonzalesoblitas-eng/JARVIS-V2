import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# Módulos a probar y sus dependencias
from src.core.orquestador import Orquestador
from src.data import schemas
from src.core.interfaces import IDataRepository, IVectorRepository, IToolsRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_data_repo():
    repo = MagicMock(spec=IDataRepository)
    repo.async_read_data = AsyncMock()
    repo.async_save_data = AsyncMock()
    repo.async_read_bitacora_summary = AsyncMock()
    
    # Configurar respuestas por defecto
    repo.async_read_data.return_value = schemas.Persona(edad=30, profesion="Ingeniero")
    
    bitacora_mock = schemas.BitacoraSummary(
        dia_actual=None,
        tendencia_energia="Estable"
    )
    repo.async_read_bitacora_summary.return_value = bitacora_mock
    
    return repo

@pytest.fixture
def mock_vector_repo():
    repo = MagicMock(spec=IVectorRepository)
    repo.buscar_contexto = MagicMock(return_value="Contexto vectorial de prueba")
    return repo

@pytest.fixture
def mock_tools_repo():
    repo = MagicMock(spec=IToolsRepository)
    repo.async_ejecutar_memoria = AsyncMock(return_value="Memoria actualizada mock")
    repo.ejecutar_herramienta.return_value = "Herramienta ejecutada mock"
    return repo

@pytest.fixture
def orquestador_con_mocks(mock_data_repo, mock_vector_repo, mock_tools_repo):
    with patch('src.core.orquestador.FSMOrquestador', autospec=True) as mock_fsm_class:
        mock_fsm_instance = mock_fsm_class.return_value
        
        # Mocks para los steps
        mock_fsm_instance.step_1_route = AsyncMock()
        mock_fsm_instance.step_2_extract = AsyncMock()
        mock_fsm_instance.step_3_execute = AsyncMock()
        mock_fsm_instance.step_4_synthesize = AsyncMock()
        
        orquestador = Orquestador(
            data_repo=mock_data_repo,
            vector_repo=mock_vector_repo,
            tools_repo=mock_tools_repo
        )
        # Reemplazamos fsm instanciado con el mock
        orquestador.fsm = mock_fsm_instance
        yield orquestador

async def test_orquestador_flujo_charla(orquestador_con_mocks):
    """Prueba que una intención de 'charla' devuelve la respuesta sin llamar a herramientas."""
    orquestador_con_mocks.fsm.step_1_route.return_value = {
        "intencion": "charla",
        "herramienta": None,
        "memoria": None
    }
    orquestador_con_mocks.fsm.step_4_synthesize.return_value = "Hola, ¿cómo estás?"

    respuesta = await orquestador_con_mocks.procesar_mensaje("user1", "hola", None)
    
    assert respuesta == "Hola, ¿cómo estás?"
    orquestador_con_mocks.fsm.step_1_route.assert_called_once()
    orquestador_con_mocks.fsm.step_3_execute.assert_not_called()

async def test_orquestador_flujo_comando(orquestador_con_mocks):
    """Prueba que una intención de 'comando' ejecuta los steps correctos."""
    orquestador_con_mocks.fsm.step_1_route.return_value = {
        "intencion": "comando",
        "herramienta": "buscar_web",
        "memoria": None
    }
    orquestador_con_mocks.fsm.step_2_extract.return_value = {"query": "clima"}
    orquestador_con_mocks.fsm.step_3_execute.return_value = "Resultado de busqueda web"
    orquestador_con_mocks.fsm.step_4_synthesize.return_value = "El clima es soleado."
    
    respuesta = await orquestador_con_mocks.procesar_mensaje("user1", "busca el clima", None)
    
    orquestador_con_mocks.fsm.step_3_execute.assert_called_once_with("buscar_web", {"query": "clima"})
    assert respuesta == "El clima es soleado."

async def test_orquestador_flujo_memoria(orquestador_con_mocks):
    """Prueba que una intención de memoria llama al MemoryManager."""
    orquestador_con_mocks.fsm.step_1_route.return_value = {
        "intencion": "guardar_recordatorio",
        "herramienta": None,
        "memoria": "nuevo_recordatorio"
    }
    orquestador_con_mocks.fsm.step_2_extract.return_value = {"descripcion": "comprar pan", "contexto": "supermercado"}
    orquestador_con_mocks.fsm.step_4_synthesize.return_value = "Recordatorio guardado."
    
    with patch('src.core.orquestador.MemoryManager') as mock_memory_manager_class:
        mock_memory_manager = mock_memory_manager_class.return_value
        mock_memory_manager.procesar_intencion_memoria = AsyncMock(return_value="Guardado")
        orquestador_con_mocks.memory_manager = mock_memory_manager
        
        respuesta = await orquestador_con_mocks.procesar_mensaje("user1", "recuérdame comprar pan", None)
        
        mock_memory_manager.procesar_intencion_memoria.assert_called_once_with(
            "nuevo_recordatorio",
            {"descripcion": "comprar pan", "contexto": "supermercado"}
        )
        assert respuesta == "Recordatorio guardado."

async def test_orquestador_manejo_excepciones(orquestador_con_mocks):
    """Prueba que si ocurre una excepción no controlada, el orquestador no crashea."""
    orquestador_con_mocks.fsm.step_1_route.side_effect = Exception("Fallo catastrófico simulado")
    
    respuesta = await orquestador_con_mocks.procesar_mensaje("user1", "hola", None)
    
    assert "Error del Sistema" in respuesta
    assert "Fallo catastrófico simulado" in respuesta
