"""
Demo 1 — Mi primer agente con Strands Agents + Amazon Bedrock (gpt-oss).

Un agente = MOTOR (LLM) + VOLANTE (instrucciones) + RUEDAS (herramientas).

Requiere un archivo .env en la raíz del proyecto (ver .env.example).

Ejecutar:
    uv run python demo-1-simple/agente_simple.py
"""

import os

from dotenv import load_dotenv
from strands import Agent, tool
from strands.models.openai import OpenAIModel

from herramientas import calcular, hora_actual, tablero

load_dotenv()
BEDROCK_URL = os.environ["OPENAI_BASE_URL"]  # endpoint de Bedrock compatible con OpenAI
API_KEY = os.environ["OPENAI_API_KEY"]  # API key de Amazon Bedrock

# 1) EL MOTOR: un LLM en Amazon Bedrock
motor = OpenAIModel(
    model_id="openai.gpt-oss-120b",
    client_args={"base_url": BEDROCK_URL, "api_key": API_KEY},
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
        "3. ¿Cuántas letras 'a' tiene la palabra 'Ananay'?"
    )
    print("\n")
