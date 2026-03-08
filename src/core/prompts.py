"""
Módulo dedicado exclusivamente a la gestión de Prompts del sistema.
Cumple con SRP (Single Responsibility Principle).

NOTA: En la V3.0 el system_prompt principal se ha migrado e integrado directamente 
dentro de CerebroDigital (src/core/cerebro.py) para mantener cohesión con la clase 
y las intenciones de memoria. Este archivo se mantiene por retrocompatibilidad o 
para futuros prompts auxiliares.
"""

def get_system_prompt() -> str:
    from src.core.cerebro import CerebroDigital
    # Fallback/referencia al prompt real
    return CerebroDigital()._get_system_prompt()
