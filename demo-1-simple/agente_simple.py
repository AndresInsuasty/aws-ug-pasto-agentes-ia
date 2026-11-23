"""
Demo 1 — Mi primer agente con Strands Agents + Amazon Bedrock (gpt-oss).

Un agente = MOTOR (LLM) + VOLANTE (instrucciones) + RUEDAS (herramientas).

No necesita API key: usa tus credenciales de AWS (`aws login`). Strands genera llaves
temporales de Bedrock y las renueva solo.

Ejecutar:
    uv run python demo-1-simple/agente_simple.py
"""

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.openai import OpenAIModel

from herramientas import calcular, hora_actual, tablero

load_dotenv()  # opcional: p. ej. AWS_CA_BUNDLE si un antivirus inspecciona HTTPS

# 1) EL MOTOR: un LLM en Amazon Bedrock (endpoint compatible con OpenAI)
motor = OpenAIModel(
    model_id="openai.gpt-oss-120b",
    bedrock_mantle_config={"region": "us-east-2"},  # sin API keys: usa IAM
    params={"reasoning_effort": "low"},
)


# 2) UNA RUEDA HECHA POR NOSOTROS: cualquier función de Python es una herramienta
@tool
def contar_letras(palabra: str, letra: str) -> int:
    """Cuenta cuántas veces aparece una letra en una palabra."""
    return palabra.lower().count(letra.lower())


# 3) EL AUTO: motor + volante + ruedas
agente = Agent(
    model=motor,
    system_prompt="Eres un asistente pastuso, amable y breve. Responde en español. Usa SIEMPRE tus herramientas para horas, cálculos y conteos.",
    tools=[calcular, hora_actual, contar_letras],
    callback_handler=tablero,  # muestra 💭 pensar → 🔧 actuar → ✅ responder
)

if __name__ == "__main__":
    agente(
        "Tengo tres preguntas:\n"
        "1. ¿Qué hora es en Bogotá?\n"
        "2. ¿Cuánto es 3111 * 37 / 4?\n"
        "3. ¿Cuántas letras 'a' tiene la palabra 'Achichay'?"
    )
    print("\n")
