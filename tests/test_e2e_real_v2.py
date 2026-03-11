import pytest
import os
import asyncio
import uuid
import hashlib
from datetime import datetime
import pytz

from dotenv import load_dotenv
load_dotenv()

from chromadb.api.types import EmbeddingFunction, Documents, Embeddings

from src.core.orquestador import Orquestador
from src.core.repositories import JSONDataRepository, ChromaVectorRepository, DefaultToolsRepository
from src.data import db_handler, schemas

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e]


def _make_hash_embedding_fn():
    """
    Crea una función de embedding determinista basada en hash.
    No requiere ninguna API externa: ideal para tests E2E aislados donde
    lo que se valida es el FLUJO de datos, no la calidad semántica.
    Con colecciones pequeñas (1-3 items) ChromaDB devuelve todos los
    resultados independientemente de la distancia.
    """
    class _HashEmbeddingFn(EmbeddingFunction[Documents]):
        """
        Embedding determinista para tests: hereda de EmbeddingFunction[Documents]
        para que chromadb 1.5+ pueda llamar embed_query() (método concreto heredado).
        """
        def __init__(self):
            pass  # Requerido por chromadb 1.5+ para evitar DeprecationWarning

        @staticmethod
        def name() -> str:
            return "hash_embedding_fn_test"

        def get_config(self) -> dict:
            return {"type": "hash_md5", "dims": 768}

        @staticmethod
        def build_from_config(config: dict) -> "_HashEmbeddingFn":
            return _HashEmbeddingFn()

        def __call__(self, input: Documents) -> Embeddings:
            result = []
            for text in input:
                h = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
                vec = [(h >> (i % 64)) % 100 / 100.0 for i in range(768)]
                result.append(vec)
            return result
    return _HashEmbeddingFn()


def setup_test_environment(tmp_path, monkeypatch):
    """
    Setup test environment with temp memory directory.

    CORRECCIÓN: El patched_init ahora usa EphemeralClient (in-memory) con una
    función de embedding basada en hash. Esto garantiza:
    - Aislamiento total entre tests (cada test tiene su propia colección fresca)
    - Sin dependencia de la API de Google para la parte vectorial
    - Sin warnings de chromadb sobre api_key deprecated
    - Las escrituras de MemoryManager van a la MISMA colección que el test lee,
      ya que Orquestador inyecta vector_repo en MemoryManager.
    """
    # La API key sigue siendo necesaria para el LLM (Gemini)
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY no encontrado, saltando prueba E2E.")

    test_memory_path = tmp_path / "MEMORIA_E2E_REAL"
    test_memory_path.mkdir(exist_ok=True)

    monkeypatch.setattr(db_handler, 'MEMORY_PATH', str(test_memory_path))

    def patched_init(self):
        import chromadb
        self.persist_directory = str(test_memory_path / "vector_db")
        self._lock = asyncio.Lock()
        # EphemeralClient: in-memory, sin persistencia, sin problemas de api_key
        self.client = chromadb.EphemeralClient()
        # Colección única por test para aislamiento total
        self.collection = self.client.create_collection(
            name=f"test_{uuid.uuid4().hex}",
            embedding_function=_make_hash_embedding_fn()
        )

    monkeypatch.setattr(ChromaVectorRepository, '__init__', patched_init)

    db_handler.init_db()

    return Orquestador(
        data_repo=JSONDataRepository(),
        vector_repo=ChromaVectorRepository(),
        tools_repo=DefaultToolsRepository()
    )


async def test_guardar_nombre(tmp_path, monkeypatch):
    """Verifica que el nombre se guarda correctamente en JSON"""
    orq = setup_test_environment(tmp_path, monkeypatch)

    await orq.procesar_mensaje("user1", "Me llamo Joseph")

    persona = await orq.data_repo.async_read_data("persona.json", schemas.Persona)
    assert persona.nombre == "Joseph", f"Nombre esperado 'Joseph', obtenido '{persona.nombre}'"


async def test_guardar_recordatorio(tmp_path, monkeypatch):
    """Verifica que los recordatorios se guardan correctamente"""
    orq = setup_test_environment(tmp_path, monkeypatch)

    await orq.procesar_mensaje("user1", "Recuérdame comprar leche")

    contexto = await orq.data_repo.async_read_data("contexto.json", schemas.GestorContexto)
    recordatorios = [r.descripcion for r in contexto.recordatorios_pendientes if not r.completado]

    assert any("leche" in r.lower() for r in recordatorios), (
        f"Recordatorio de leche no encontrado. Recordatorios: {recordatorios}"
    )


async def test_guardar_recuerdo_largo_plazo(tmp_path, monkeypatch):
    """
    Verifica que los recuerdos a largo plazo se guardan correctamente.
    """
    orq = setup_test_environment(tmp_path, monkeypatch)
    await orq.procesar_mensaje("user1", "Mi hijo nació el 16 de febrero")
    await asyncio.sleep(1)
    recuerdos = await orq.vector_repo.async_buscar_recuerdos_relevantes("cumpleaños hijo", n_results=1)
    assert len(recuerdos) > 0, "Recuerdo no encontrado en base vectorial"
    assert "16" in recuerdos[0] or "febrero" in recuerdos[0].lower(), f"Fecha no encontrada en: {recuerdos[0]}"

async def test_alarma_rapida_real(tmp_path, monkeypatch):
    """Verifica que Jarvis usa la herramienta alarma_rapida y SIDE-EFFECT en memoria"""
    orq = setup_test_environment(tmp_path, monkeypatch)
    from src.core.cron import cron_manager
    cron_manager._alarmas_dinamicas.clear() # Asegurar memoria limpia
    
    response = await orq.procesar_mensaje("user1", "Pon alarma en 2 minutos para pedir la cuenta")
    
    assert "cuenta" in response.lower() or "alarma" in response.lower() or "timer" in response.lower(), f"Respuesta inesperada: {response}"
    assert "generarplancalendario" not in response.lower(), "JARVIS intentó usar una herramienta inventada."
    
    # Comprobar Side-Effect: la alarma realmente se insertó en el cron_manager
    assert len(cron_manager._alarmas_dinamicas) == 1, "La alarma NO se guardó en memoria RAM."
    assert "cuenta" in cron_manager._alarmas_dinamicas[0][1].lower(), "La alarma guardada no contiene el mensaje."

async def test_agendar_recordatorio_real(tmp_path, monkeypatch):
    orq = setup_test_environment(tmp_path, monkeypatch)
    from src.core.cron import cron_manager
    cron_manager._alarmas_dinamicas.clear()

    response = await orq.procesar_mensaje("user1", "Avísame a las 15:30 que tengo reunión")
    
    assert "reunión" in response.lower() or "reunion" in response.lower() or "agendad" in response.lower(), f"Respuesta inesperada: {response}"
    
    # Comprobar Side-Effect
    assert len(cron_manager._alarmas_dinamicas) == 1, "El recordatorio NO se guardó en memoria RAM."
    assert "15:30" in cron_manager._alarmas_dinamicas[0][0], "La hora agendada no coincide."
    assert "reunión" in cron_manager._alarmas_dinamicas[0][1].lower() or "reunion" in cron_manager._alarmas_dinamicas[0][1].lower(), "El mensaje no coincide."

async def test_google_calendar_real(tmp_path, monkeypatch):
    orq = setup_test_environment(tmp_path, monkeypatch)
    # Side-Effect: Si la ejecución llega a ToolAgenda real pero no hay token, responderá esto. 
    # Si sí hay token, responderá "Evento agendado". Lo importante es que no diga "Herramienta no encontrada".
    response = await orq.procesar_mensaje("user1", "Agendar en google calendar reunión de equipo mañana a las 10 am por 60 minutos")
    
    assert "token" in response.lower() or "google calendar" in response.lower() or "agend" in response.lower() or "fallo" in response.lower(), f"Respuesta inesperada: {response}"
    assert "generar" not in response.lower() and "herramienta" not in response.lower() and "encontrada" not in response.lower(), "Falló el enrutamiento a Google Calendar."

async def test_google_tasks_real(tmp_path, monkeypatch):
    orq = setup_test_environment(tmp_path, monkeypatch)
    response = await orq.procesar_mensaje("user1", "Añade a google tasks: comprar pan")
    
    assert "token" in response.lower() or "tasks" in response.lower() or "pan" in response.lower() or "fallo" in response.lower(), f"Respuesta inesperada: {response}"
    assert "herramienta" not in response.lower(), "Falló el enrutamiento a Google Tasks."

async def test_buscar_web_real(tmp_path, monkeypatch):
    orq = setup_test_environment(tmp_path, monkeypatch)
    response = await orq.procesar_mensaje("user1", "Busca en la web cuál es el precio del bitcoin hoy")
    
    # DuckDuckGo realiza request real.
    assert "bitcoin" in response.lower() or "precio" in response.lower() or "resultados" in response.lower() or "encontré" in response.lower(), f"Respuesta inesperada: {response}"

async def test_clima_actual_real(tmp_path, monkeypatch):
    orq = setup_test_environment(tmp_path, monkeypatch)
    response = await orq.procesar_mensaje("user1", "¿Cómo está el clima hoy en Lima?")
    
    assert "clima" in response.lower() or "lima" in response.lower() or "temperatura" in response.lower() or "api" in response.lower() or "error" in response.lower(), f"Respuesta inesperada: {response}"

async def test_modos_conversacion_real(tmp_path, monkeypatch):
    orq = setup_test_environment(tmp_path, monkeypatch)
    from src.core.conversation_state import conversation_state_manager
    conversation_state_manager.desactivar_modo() # Reset

    response_foco = await orq.procesar_mensaje("user1", "Activa modo foco por 30 minutos")
    assert "foco" in response_foco.lower() or "trabajo profundo" in response_foco.lower() or "concentrar" in response_foco.lower(), f"Respuesta inesperada: {response_foco}"
    
    # Comprobar Side-Effect
    assert conversation_state_manager.modo.value == "trabajo_profundo", f"El modo interno no cambió a Foco. Es: {conversation_state_manager.modo.value}"

    # Resetear modo antes de pedir escucha, porque en Foco el LLM ignora comandos proactivos y solo da 1 línea
    conversation_state_manager.desactivar_modo()
    
    # Nuevo orquestador para borrar el historial de buffer RAM que pueda confundir al modelo
    orq2 = setup_test_environment(tmp_path, monkeypatch)

    response_escucha = await orq2.procesar_mensaje("user1", "Quiero que actives la herramienta activar_modo con modo escucha_profunda para hablar de algo")
    assert "escucha" in response_escucha.lower() or "siento" in response_escucha.lower() or "aquí estoy" in response_escucha.lower() or "claro" in response_escucha.lower(), f"Respuesta inesperada: {response_escucha}"
    
    # Comprobar Side-Effect
    assert conversation_state_manager.modo.value == "escucha_profunda", f"El modo interno no cambió a Escucha Profunda. Es: {conversation_state_manager.modo.value}"

async def test_graficos_energia_real(tmp_path, monkeypatch):
    orq = setup_test_environment(tmp_path, monkeypatch)
    
    # Llenamos datos falsos en bitácora para asegurar que Genere imagen y no devuelva "datos insuficientes"
    bitacora = await orq.data_repo.async_read_data("bitacora.json", schemas.GestorBitacora)
    bitacora.historico_dias = {
        "2026-08-01": schemas.RegistroDiario(fecha="2026-08-01", nivel_energia=5, estado_animo="normal"),
        "2026-08-02": schemas.RegistroDiario(fecha="2026-08-02", nivel_energia=8, estado_animo="bien")
    }
    await orq.data_repo.async_save_data("bitacora.json", bitacora)
    
    # Al pedir gráfico, el _pending_attachment se llenará si la herramienta se ejecutó bien.
    response = await orq.procesar_mensaje("user1", "Muéstrame mi progreso de energía")
    
    # Side-Effect: Validar que el Orquestador atrapó la orden de adjuntar PNG
    assert orq._pending_attachment is not None, "El gráfico NO se generó. '_pending_attachment' está vacío."
    assert orq._pending_attachment.endswith(".png"), "El archivo adjunto no es una imagen PNG."

async def test_analisis_emocional_logro_real(tmp_path, monkeypatch):
    orq = setup_test_environment(tmp_path, monkeypatch)
    response = await orq.procesar_mensaje("user1", "Por fin terminé la maestría que me tomó 2 años de esfuerzo")
    
    # Side-Effect: Se le inyectó el mensaje de celebración al final
    assert "🎉" in response or "logro" in response.lower() or "felicidades" in response.lower() or "esfuerzo" in response.lower(), f"Respuesta inesperada (no hubo celebración): {response}"

async def test_analisis_emocional_crisis_real(tmp_path, monkeypatch):
    orq = setup_test_environment(tmp_path, monkeypatch)
    
    # Limpiamos el json emocional
    estado_emocional = await orq.data_repo.async_read_data("estado_emocional.json", schemas.EstadoEmocionalSistema)
    estado_emocional.ultima_crisis_detectada = ""
    await orq.data_repo.async_save_data("estado_emocional.json", estado_emocional)
    
    # Mandar mensaje de crisis severa
    response = await orq.procesar_mensaje("user1", "Siento que no vale la pena seguir, quiero terminar con todo")
    
    # Validar respuesta
    assert "solo" in response.lower() or "ayuda" in response.lower() or "aquí estoy" in response.lower(), f"Respuesta inesperada (no detectó crisis Nivel 2): {response}"
    
    # Comprobar Side-Effect: ¿Cambió el archivo estado_emocional.json?
    estado_despues = await orq.data_repo.async_read_data("estado_emocional.json", schemas.EstadoEmocionalSistema)
    assert estado_despues.ultima_crisis_detectada != "", "El motor emocional no registró la fecha de crisis en el JSON."
