"""
Demo 1 — Mi primer agente con Strands Agents + Amazon Bedrock (Nova).

Un agente = MOTOR (LLM) + VOLANTE (instrucciones) + RUEDAS (herramientas).

Ejecutar:
    uv run python demo-1-simple/agente_simple.py
"""

from strands import Agent, tool
from strands.models import BedrockModel
from herramientas import calcular, hora_actual

# 1) EL MOTOR: un LLM en Amazon Bedrock
motor = BedrockModel(
    model_id="us.amazon.nova-lite-v1:0",
    region_name="us-west-2",
)


# 2) UNA RUEDA HECHA POR NOSOTROS: cualquier función de Python es una herramienta
@tool
def contar_letras(palabra: str, letra: str) -> int:
    """Cuenta cuántas veces aparece una letra en una palabra."""
    return palabra.lower().count(letra.lower())


# 3) EL AUTO: motor + volante + ruedas
agente = Agent(
    model=motor,
    system_prompt="Eres un asistente pastuso, amable y breve. Responde en español.",
    tools=[calcular, hora_actual, contar_letras],
)

if __name__ == "__main__":
    agente(
        "Tengo tres preguntas:\n"
        "1. ¿Qué hora es en Bogotá?\n"
        "2. ¿Cuánto es 3111 * 37 / 4?\n"
        "3. ¿Cuántas letras 'a' tiene la palabra 'Ananay'?"
    )
    print("\n")
