"""Configuración de los 'motores' (LLMs) en Amazon Bedrock.

Usamos el endpoint de Bedrock compatible con la API de OpenAI (bedrock-mantle), que permite
elegir entre muchos modelos: gpt-oss, Qwen, Kimi, GLM, DeepSeek, Mistral...

Sin API keys guardadas: la llave se genera con las credenciales de IAM (el rol de la tarea
en Fargate, o tu `aws login` en local) y se renueva sola, porque vence en máximo 12 horas.
Si defines LLM_API_KEY se usa esa llave fija en su lugar.
"""

import os
import time

from aws_bedrock_token_generator import provide_token
from openai import OpenAI

REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-2"
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or f"https://bedrock-mantle.{REGION}.api.aws/v1"
LLAVE_FIJA = os.getenv("LLM_API_KEY", "").strip()

# Motor que conversa y decide qué herramientas usar
MODEL_ID = os.getenv("MODEL_ID", "openai.gpt-oss-120b")
# Motor 'ilustrador': otro modelo, especializado, que usamos como herramienta
ILUSTRADOR_ID = os.getenv("ILUSTRADOR_ID", "moonshotai.kimi-k2.5")

_cache = {"llave": "", "creada": 0.0}


def llave() -> str:
    """Devuelve una llave vigente para Bedrock (se renueva cada hora)."""
    if LLAVE_FIJA:
        return LLAVE_FIJA
    if time.time() - _cache["creada"] > 3600:
        _cache.update(llave=provide_token(region=REGION), creada=time.time())
    return _cache["llave"]


def config_motor() -> dict:
    """Argumentos para strands.models.openai.OpenAIModel."""
    if LLAVE_FIJA:
        return {"client_args": {"base_url": LLM_BASE_URL, "api_key": LLAVE_FIJA}}
    return {"bedrock_mantle_config": {"region": REGION}}  # Strands genera y renueva la llave


# El cliente llama a llave() en cada petición
cliente = OpenAI(base_url=LLM_BASE_URL, api_key=llave, timeout=120, max_retries=2)
