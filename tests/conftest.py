import pytest
import os
import sys

# Añadir el directorio raíz del proyecto al sys.path para que pytest encuentre el módulo 'src'
# Esto asegura que las pruebas se puedan ejecutar desde cualquier directorio.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Configura el entorno para todas las pruebas.
    Se ejecuta una vez por sesión.
    """
    # Establecer una variable de entorno para indicar que estamos en modo de prueba
    os.environ["TEST_MODE"] = "1"
    
    # Aquí se podrían añadir más configuraciones globales, como crear
    # directorios de prueba o configurar una base de datos de prueba.
    
    print("--- Entorno de Pruebas Configurado ---")
    
    yield
    
    # Código de limpieza que se ejecuta al final de todas las pruebas
    del os.environ["TEST_MODE"]
    print("--- Entorno de Pruebas Limpio ---")

import asyncio

@pytest.fixture(scope="function")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_db_path(tmp_path, monkeypatch):
    """
    Crea un directorio temporal para la base de datos de prueba y se asegura
    de que el db_handler lo utilice, sobreescribiendo la constante MEMORY_PATH.
    """
    test_memory_path = tmp_path / "MEMORIA_TEST"
    test_memory_path.mkdir()
    
    # Usamos monkeypatch para cambiar la constante global en db_handler
    monkeypatch.setattr('src.data.db_handler.MEMORY_PATH', str(test_memory_path))

    # CRÍTICO PARA ASYNCIO: Monkeypatch del lock para que use el loop del test actual
    # Esto evita el error "is bound to a different event loop"
    monkeypatch.setattr('src.data.db_handler._db_lock_async', asyncio.Lock())
    
    yield test_memory_path
