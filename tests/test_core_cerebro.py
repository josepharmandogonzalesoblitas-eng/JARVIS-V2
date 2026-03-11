import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock

from src.core.llm.interfaces import ILLMProvider
from src.core.pipeline.router import IntentionRouter, RouterSchema
from src.core.pipeline.extractor import ParameterExtractor
from src.core.pipeline.synthesizer import ResponseSynthesizer

class MockProvider(ILLMProvider):
    async def classify_intent(self, system_prompt, user_message, context, response_model=None):
        if response_model == RouterSchema:
            return RouterSchema(intencion="comando", herramienta_sugerida="buscar_web")
        elif response_model is None:
            return {"query": "python"}

    async def generate_response(self, system_prompt, user_message, context, tool_result=None, audio_file_path=None, image_file_path=None):
        return "Respuesta sintetizada"

@pytest.fixture
def mock_provider():
    return MockProvider()

@pytest.mark.asyncio
async def test_router(mock_provider):
    router = IntentionRouter(mock_provider)
    result = await router.route("busca python", "contexto")
    assert result.intencion == "comando"
    assert result.herramienta_sugerida == "buscar_web"

@pytest.mark.asyncio
async def test_extractor(mock_provider):
    extractor = ParameterExtractor(mock_provider)
    params = await extractor.extract("busca python", "contexto", "buscar_web")
    assert params == {"query": "python"}

@pytest.mark.asyncio
async def test_synthesizer(mock_provider):
    synth = ResponseSynthesizer(mock_provider)
    response = await synth.synthesize("busca python", "contexto", tool_result="Python es un lenguaje")
    assert response == "Respuesta sintetizada"
