"""Configuración de los 'motores' (LLMs) en Amazon Bedrock.

Usamos el endpoint de Bedrock compatible con la API de OpenAI (bedrock-mantle), que permite
elegir entre muchos modelos: gpt-oss, Qwen, Kimi, GLM, DeepSeek, Mistral...
"""

import os

from openai import OpenAI

LLM_BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://bedrock-mantle.us-east-2.api.aws/v1"
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or ""

# Motor que conversa y decide qué herramientas usar
MODEL_ID = os.getenv("MODEL_ID", "openai.gpt-oss-120b")
# Motor 'ilustrador': otro modelo, especializado, que usamos como herramienta
ILUSTRADOR_ID = os.getenv("ILUSTRADOR_ID", "moonshotai.kimi-k2.5")

cliente = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY, timeout=120, max_retries=2)
