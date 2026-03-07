import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from google.api_core import exceptions as google_exceptions

# Importar la clase a probar
from src.core.cerebro import CerebroDigital, PensamientoJarvis

# Usar pytest-asyncio para marcar tests asíncronos
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_genai():
    """Fixture para mockear el módulo google.generativeai."""
    with patch('src.core.cerebro.genai') as mock_genai_module:
        # Mockear el modelo generativo y su método async
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock()
        
        # Mockear el constructor del modelo para que devuelva nuestro mock
        mock_genai_module.GenerativeModel.return_value = mock_model
        
        # Mockear la subida de archivos
        mock_genai_module.upload_file = MagicMock()
        
        # Devolver el módulo mockeado para poder acceder a los mocks en las pruebas
        yield mock_genai_module

async def test_cerebro_pensar_ok(mock_genai):
    """
    Prueba el flujo normal de 'pensar' con una respuesta JSON válida.
    """
    # Configurar el valor de retorno del mock
    mock_response = MagicMock()
    mock_response.text = '''
    {
        "intencion": "charla",
        "razonamiento": "El usuario saludó.",
        "respuesta_usuario": "Hola, ¿en qué puedo ayudarte?",
        "herramienta_sugerida": null,
        "datos_extra": {}
    }
    '''
    mock_genai.GenerativeModel.return_value.generate_content_async.return_value = mock_response
    
    cerebro = CerebroDigital()
    pensamiento = await cerebro.pensar("Hola", "contexto")
    
    assert isinstance(pensamiento, PensamientoJarvis)
    assert pensamiento.intencion == "charla"
    assert pensamiento.respuesta_usuario == "Hola, ¿en qué puedo ayudarte?"
    # Verificar que la llamada a la API se hizo
    mock_genai.GenerativeModel.return_value.generate_content_async.assert_called_once()

async def test_cerebro_fail_safe_timeout(mock_genai):
    """
    Prueba el Fail-Safe cuando la API de Gemini sufre un timeout.
    """
    # Configurar el mock para que lance un TimeoutError
    mock_genai.GenerativeModel.return_value.generate_content_async.side_effect = asyncio.TimeoutError
    
    cerebro = CerebroDigital()
    pensamiento = await cerebro.pensar("Hola", "contexto")
    
    assert pensamiento.intencion == "fallback_error"
    assert "sobrecargados" in pensamiento.respuesta_usuario

async def test_cerebro_fail_safe_google_api_error(mock_genai):
    """
    Prueba el Fail-Safe cuando la API de Google devuelve un error genérico.
    """
    mock_genai.GenerativeModel.return_value.generate_content_async.side_effect = google_exceptions.ServiceUnavailable("API Down")
    
    cerebro = CerebroDigital()
    pensamiento = await cerebro.pensar("Hola", "contexto")
    
    assert pensamiento.intencion == "fallback_error"
    assert "desconectados" in pensamiento.respuesta_usuario

async def test_cerebro_graceful_degradation_hora(mock_genai):
    """
    Prueba el Graceful Degradation: si falla la API pero el usuario pregunta la hora,
    el Cerebro debe responder con un comando local.
    """
    mock_genai.GenerativeModel.return_value.generate_content_async.side_effect = asyncio.TimeoutError
    
    cerebro = CerebroDigital()
    pensamiento = await cerebro.pensar("¿Qué hora es?", "contexto")
    
    # Debe degradar a un comando local en vez de fallar completamente
    assert pensamiento.intencion == "comando"
    assert pensamiento.herramienta_sugerida == "consultar_hora"
    assert "hora local" in pensamiento.respuesta_usuario

async def test_cerebro_graceful_degradation_sistema(mock_genai):
    """
    Prueba el Graceful Degradation para comandos de estado del sistema.
    """
    mock_genai.GenerativeModel.return_value.generate_content_async.side_effect = google_exceptions.InternalServerError("Down")
    
    cerebro = CerebroDigital()
    pensamiento = await cerebro.pensar("dame un reporte del sistema", "contexto")
    
    assert pensamiento.intencion == "comando"
    assert pensamiento.herramienta_sugerida == "estado_sistema"

async def test_cerebro_json_malformed(mock_genai):
    """
    Prueba el manejo de errores cuando Gemini devuelve un JSON malformado.
    """
    mock_response = MagicMock()
    mock_response.text = '{"intencion": "charla", "razonamiento": "mal" "formado"}'
    mock_genai.GenerativeModel.return_value.generate_content_async.return_value = mock_response

    cerebro = CerebroDigital()
    pensamiento = await cerebro.pensar("Hola", "contexto")

    assert pensamiento.intencion == "fallback_error"
    assert "formato inválido" in pensamiento.respuesta_usuario

async def test_cerebro_with_audio(mock_genai, tmp_path):
    """
    Prueba que el cerebro maneje correctamente un archivo de audio.
    """
    # Crear un archivo de audio falso
    audio_file = tmp_path / "test.ogg"
    audio_file.write_text("fake audio data")
    
    # Configurar respuesta normal
    mock_response = MagicMock()
    mock_response.text = '{"intencion": "charla", "razonamiento": "Audio recibido", "respuesta_usuario": "Entendido."}'
    mock_genai.GenerativeModel.return_value.generate_content_async.return_value = mock_response

    cerebro = CerebroDigital()
    await cerebro.pensar("Transcripción", "contexto", audio_file_path=str(audio_file))

    # Verificar que se intentó subir el archivo
    mock_genai.upload_file.assert_called_once_with(path=str(audio_file))
    # Verificar que el prompt contiene la referencia al audio
    call_args = mock_genai.GenerativeModel.return_value.generate_content_async.call_args
    # call_args[0][0] es la lista 'contenidos'
    prompt_enviado = call_args[0][0][0]
    archivo_enviado = call_args[0][0][1]

    assert "Se adjuntó una nota de voz" in prompt_enviado
    assert archivo_enviado == mock_genai.upload_file.return_value
