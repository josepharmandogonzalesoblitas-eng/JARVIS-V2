import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

# Módulos a probar y sus dependencias
from src.core.orquestador import Orquestador
from src.core.cerebro import PensamientoJarvis
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
    repo.buscar_contexto.return_value = "Contexto vectorial de prueba"
    return repo

@pytest.fixture
def mock_tools_repo():
    repo = MagicMock(spec=IToolsRepository)
    repo.async_ejecutar_memoria = AsyncMock(return_value="Memoria actualizada mock")
    repo.ejecutar_herramienta.return_value = "Herramienta ejecutada mock"
    return repo

@pytest.fixture
def orquestador_con_mocks(mock_data_repo, mock_vector_repo, mock_tools_repo):
    with patch('src.core.orquestador.CerebroDigital', autospec=True) as mock_cerebro_class:
        mock_cerebro_instance = mock_cerebro_class.return_value
        mock_cerebro_instance.pensar = AsyncMock()
        
        orquestador = Orquestador(
            data_repo=mock_data_repo,
            vector_repo=mock_vector_repo,
            tools_repo=mock_tools_repo
        )
        orquestador.cerebro = mock_cerebro_instance
        yield orquestador

async def test_orquestador_flujo_charla(orquestador_con_mocks):
    """Prueba que una intención de 'charla' devuelve la respuesta de la IA sin llamar a herramientas."""
    pensamiento = PensamientoJarvis(
        intencion="charla",
        razonamiento="N/A",
        respuesta_usuario="Hola, ¿cómo estás?"
    )
    orquestador_con_mocks.cerebro.pensar.return_value = pensamiento

    respuesta = await orquestador_con_mocks.procesar_mensaje("user1", "hola", None)
    
    assert respuesta == "Hola, ¿cómo estás?"
    orquestador_con_mocks.cerebro.pensar.assert_called_once()
    orquestador_con_mocks.tools_repo.ejecutar_herramienta.assert_not_called()
    orquestador_con_mocks.tools_repo.async_ejecutar_memoria.assert_not_called()

async def test_orquestador_flujo_comando(orquestador_con_mocks):
    """Prueba que una intención de 'comando' llama al repositorio de herramientas correcto."""
    pensamiento = PensamientoJarvis(
        intencion="comando",
        razonamiento="N/A",
        respuesta_usuario="Ejecutando comando...",
        herramienta_sugerida="buscar_web",
        datos_extra={"query": "clima"}
    )
    orquestador_con_mocks.cerebro.pensar.return_value = pensamiento
    
    respuesta = await orquestador_con_mocks.procesar_mensaje("user1", "busca el clima", None)
    
    orquestador_con_mocks.tools_repo.ejecutar_herramienta.assert_called_once_with("buscar_web", {"query": "clima"})
    assert "Ejecutando comando..." in respuesta
    assert "Herramienta ejecutada mock" in respuesta

async def test_orquestador_flujo_memoria(orquestador_con_mocks):
    """Prueba que una intención de 'actualizar_memoria' llama al repositorio de memoria asíncrono."""
    pensamiento = PensamientoJarvis(
        intencion="actualizar_memoria",
        razonamiento="N/A",
        respuesta_usuario="Memoria actualizada.",
        datos_extra={"accion": "nuevo_recordatorio"}
    )
    orquestador_con_mocks.cerebro.pensar.return_value = pensamiento
    
    await orquestador_con_mocks.procesar_mensaje("user1", "recuérdame comprar pan", None)
    
    orquestador_con_mocks.tools_repo.async_ejecutar_memoria.assert_called_once_with({"accion": "nuevo_recordatorio"})

async def test_orquestador_fail_safe_fallback(orquestador_con_mocks):
    """Prueba el Graceful Degradation del orquestador si Gemini devuelve fallback."""
    pensamiento = PensamientoJarvis(
        intencion="fallback_error",
        razonamiento="API falló",
        respuesta_usuario="Sistemas desconectados."
    )
    orquestador_con_mocks.cerebro.pensar.return_value = pensamiento
    
    respuesta = await orquestador_con_mocks.procesar_mensaje("user1", "hola", None)
    
    assert respuesta == "Sistemas desconectados."
    orquestador_con_mocks.tools_repo.ejecutar_herramienta.assert_not_called()

async def test_orquestador_manejo_excepciones(orquestador_con_mocks):
    """Prueba que si ocurre una excepción no controlada, el orquestador no crashea."""
    orquestador_con_mocks.cerebro.pensar.side_effect = Exception("Fallo catastrófico simulado")
    
    respuesta = await orquestador_con_mocks.procesar_mensaje("user1", "hola", None)
    
    assert "Error del Sistema" in respuesta
    assert "Fallo catastrófico simulado" in respuesta
