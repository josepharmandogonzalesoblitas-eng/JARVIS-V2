import logging
from typing import Dict, Any, Optional

from src.core.pipeline.router import IntentionRouter
from src.core.pipeline.extractor import ParameterExtractor
from src.core.pipeline.synthesizer import ResponseSynthesizer
from src.core.llm.gemini_provider import GeminiProvider
from src.core.interfaces import IToolsRepository, IVectorRepository
from src.core.memory_manager import MemoryManager

logger = logging.getLogger("fsm_orquestador")

class PipelineCerebro:
    """
    Facade para el Pipeline del Cerebro. 
    (High-Cohesion, Facade Pattern)
    Reemplaza la antigua clase CerebroDigital monolítica.
    """
    def __init__(self):
        # DIP: Inyección del proveedor de LLM
        # En el futuro aquí se puede inyectar un FallbackProvider
        self.provider = GeminiProvider()
        
        self.router = IntentionRouter(self.provider)
        self.extractor = ParameterExtractor(self.provider)
        self.synthesizer = ResponseSynthesizer(self.provider)


class FSMOrquestador:
    """
    State Machine pattern para controlar el flujo determinístico (Poka-Yoke, MECE).
    """
    def __init__(self, tools_repo: IToolsRepository, memory_manager: MemoryManager):
        self.pipeline = PipelineCerebro()
        self.tools_repo = tools_repo
        self.memory_manager = memory_manager

    async def step_1_route(self, text: str, context: str) -> Dict[str, Any]:
        """Estado 1: Clasificar."""
        result = await self.pipeline.router.route(text, context)
        return {
            "intencion": result.intencion,
            "herramienta": result.herramienta_sugerida,
            "memoria": result.memoria_intencion
        }

    async def step_2_extract(self, text: str, context: str, herramienta: str) -> Dict[str, Any]:
        """Estado 2: Extraer (Zero-Trust)."""
        return await self.pipeline.extractor.extract(text, context, herramienta)

    async def step_3_execute(self, herramienta: str, params: Dict[str, Any]) -> str:
        """Estado 3: Ejecutar Herramienta."""
        logger.info(f"FSM Executing Tool: {herramienta} con params {params}")
        if herramienta == "gestionar_memoria":
            return await self.tools_repo.async_ejecutar_memoria(params)
        return self.tools_repo.ejecutar_herramienta(herramienta, params)

    async def step_4_synthesize(self, text: str, context: str, tool_result: Optional[str] = None, 
                                audio: Optional[str] = None, image: Optional[str] = None) -> str:
        """Estado 4: Sintetizar respuesta (Graceful Degradation en caso de fallo final)."""
        return await self.pipeline.synthesizer.synthesize(text, context, tool_result, audio, image)
