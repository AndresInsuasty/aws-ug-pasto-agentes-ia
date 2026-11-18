"""Las 'ruedas' del agente: herramientas que el motor (LLM) decide cuándo usar."""

import base64
import json
import logging
import os
import re
import threading
import time
import uuid
import xml.etree.ElementTree as ET

import boto3
import httpx
from botocore.config import Config
from strands import tool

from . import conocimiento

log = logging.getLogger("galeritas")

IMAGE_MODEL_ID = os.getenv("IMAGE_MODEL_ID", "stability.stable-image-core-v1:1")
IMAGE_REGION = os.getenv("IMAGE_REGION", os.getenv("AWS_REGION", "us-west-2"))
MAX_IMAGENES_TOTAL = int(os.getenv("MAX_IMAGENES_TOTAL", "250"))

MODEL_ID = os.getenv("MODEL_ID", "us.amazon.nova-lite-v1:0")
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")

# Sin reintentos: si el modelo de imágenes no tiene cuota, caemos rápido al plan B (SVG)
_bedrock_img = boto3.client("bedrock-runtime", region_name=IMAGE_REGION,
                            config=Config(retries={"max_attempts": 1, "mode": "standard"}, read_timeout=45))
_bedrock_txt = boto3.client("bedrock-runtime", region_name=AWS_REGION,
                            config=Config(retries={"max_attempts": 3, "mode": "adaptive"}, read_timeout=90))
_lock_contador = threading.Lock()
_stable_pausado_hasta = 0.0  # si Stable Image falla, no lo reintentamos por unos minutos

PROMPT_SVG = """You are a vector illustrator. Draw the requested scene as ONE self-contained SVG.
Rules:
- Output ONLY the SVG markup, starting with <svg and ending with </svg>. No markdown, no explanations.
- Use viewBox="0 0 512 512" and xmlns="http://www.w3.org/2000/svg".
- Flat, colorful, festive illustration style. Fill the whole canvas with a background.
- Use only basic shapes: rect, circle, ellipse, polygon, path, line, g, linearGradient, radialGradient.
- No <text>, no <script>, no <image>, no <foreignObject>, no external links, no event attributes.
- Keep it under 70 elements."""


def _imagen_stable(prompt: str) -> tuple[bytes, str] | None:
    global _stable_pausado_hasta
    if not IMAGE_MODEL_ID or time.time() < _stable_pausado_hasta:
        return None
    try:
        resp = _bedrock_img.invoke_model(
            modelId=IMAGE_MODEL_ID,
            body=json.dumps({
                "prompt": prompt[:1500],
                "negative_prompt": "text, letters, watermark, blurry, low quality",
                "aspect_ratio": "1:1",
                "output_format": "png",
            }),
        )
        return base64.b64decode(json.loads(resp["body"].read())["images"][0]), "png"
    except Exception as e:  # noqa: BLE001
        log.warning("Stable Image no disponible (%s); uso SVG por 10 min", e.__class__.__name__)
        _stable_pausado_hasta = time.time() + 600
        return None


def _limpiar_svg(svg: str) -> str | None:
    """Valida que sea SVG y quita cualquier cosa ejecutable (defensa extra: además se muestra con <img>)."""
    m = re.search(r"<svg[\s\S]*?</svg>", svg)
    if not m:
        return None
    try:
        raiz = ET.fromstring(m.group(0))
    except ET.ParseError:
        return None
    prohibidos = {"script", "foreignObject", "image", "iframe", "a", "use", "text"}
    for padre in raiz.iter():
        for hijo in list(padre):
            if hijo.tag.split("}")[-1] in prohibidos:
                padre.remove(hijo)
        for attr in list(padre.attrib):
            nombre = attr.split("}")[-1].lower()
            if nombre.startswith("on") or nombre == "href" or "javascript:" in padre.attrib[attr].lower():
                del padre.attrib[attr]
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(raiz, encoding="unicode")


def _imagen_svg(prompt: str) -> tuple[bytes, str] | None:
    try:
        resp = _bedrock_txt.converse(
            modelId=MODEL_ID,
            system=[{"text": PROMPT_SVG}],
            messages=[{"role": "user", "content": [{"text": prompt[:1500]}]}],
            inferenceConfig={"maxTokens": 4000, "temperature": 0.7},
        )
        texto = "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
        svg = _limpiar_svg(texto)
        return (svg.encode("utf-8"), "svg") if svg else None
    except Exception as e:  # noqa: BLE001
        log.warning("No se pudo dibujar SVG: %s", e)
        return None

LUGARES = {
    "pasto": (1.2136, -77.2811),
    "laguna de la cocha": (1.1167, -77.1500),
    "volcan galeras": (1.2208, -77.3594),
    "ipiales": (0.8303, -77.6444),
    "tumaco": (1.7986, -78.7656),
}

CODIGOS_CLIMA = {
    0: "despejado", 1: "mayormente despejado", 2: "parcialmente nublado", 3: "nublado",
    45: "niebla", 48: "niebla con escarcha", 51: "llovizna ligera", 53: "llovizna", 55: "llovizna fuerte",
    61: "lluvia ligera", 63: "lluvia", 65: "lluvia fuerte", 80: "chubascos", 81: "chubascos fuertes",
    82: "aguacero", 95: "tormenta", 96: "tormenta con granizo", 99: "tormenta fuerte con granizo",
}


def crear_herramientas(sesion) -> list:
    """Crea las herramientas 'atadas' a una sesión, para avisarle al celular y al muro qué se está usando."""

    def avisar(nombre: str, detalle: str) -> None:
        sesion.evento({"tipo": "herramienta", "nombre": nombre, "detalle": detalle})
        sesion.muro.uso_herramientas[nombre] += 1
        sesion.muro.publicar({"tipo": "herramienta", "nombre": nombre, "detalle": detalle, "apodo": sesion.apodo})
        sesion.muro.publicar(sesion.muro.stats())

    @tool
    def clima_actual(lugar: str = "pasto") -> str:
        """Consulta el clima REAL en este momento y el pronóstico de 3 días.

        Args:
            lugar: uno de: pasto, laguna de la cocha, volcan galeras, ipiales, tumaco.
        """
        clave = lugar.lower().strip()
        clave = next((k for k in LUGARES if k in clave or clave in k), "pasto")
        avisar("clima", clave)
        lat, lon = LUGARES[clave]
        try:
            r = httpx.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat, "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
                    "timezone": "America/Bogota", "forecast_days": 3,
                },
                timeout=8,
            )
            r.raise_for_status()
            d = r.json()
        except Exception as e:  # noqa: BLE001
            return f"No pude consultar el clima ahora ({e.__class__.__name__})."
        c = d["current"]
        dias = d["daily"]
        pron = [
            f"{dias['time'][i]}: {CODIGOS_CLIMA.get(dias['weather_code'][i], 'variable')}, "
            f"{dias['temperature_2m_min'][i]}–{dias['temperature_2m_max'][i]} °C, "
            f"prob. lluvia {dias['precipitation_probability_max'][i]}%"
            for i in range(len(dias["time"]))
        ]
        return json.dumps({
            "lugar": clave,
            "ahora": {
                "temperatura_c": c["temperature_2m"],
                "humedad_pct": c["relative_humidity_2m"],
                "lluvia_mm": c["precipitation"],
                "viento_kmh": c["wind_speed_10m"],
                "estado": CODIGOS_CLIMA.get(c["weather_code"], "variable"),
            },
            "pronostico": pron,
        }, ensure_ascii=False)

    @tool
    def buscar_info_pasto(consulta: str) -> str:
        """Busca en la base de conocimiento local sobre Pasto y Nariño: carnaval, comida, lugares,
        expresiones pastusas, barniz de Pasto y el AWS User Group Pasto. Úsala antes de responder datos.

        Args:
            consulta: palabras clave de lo que se quiere saber.
        """
        avisar("conocimiento", consulta[:60])
        docs = conocimiento.buscar(consulta)
        if not docs:
            return "No hay información en la base local sobre eso."
        return "\n\n".join(f"## {d['titulo']}\n{d['texto']}" for d in docs)

    @tool
    def generar_imagen(descripcion_en_ingles: str, titulo: str) -> str:
        """Genera una imagen (Stable Image Core en Bedrock o, si no está disponible, un dibujo SVG) y la muestra al usuario y en el muro en vivo.
        Úsala cuando pidan dibujar, diseñar o imaginar algo (p. ej. una carroza del carnaval).

        Args:
            descripcion_en_ingles: prompt visual detallado EN INGLÉS (estilo, colores, composición).
            titulo: título corto en español para mostrar con la imagen.
        """
        with _lock_contador:
            if sesion.muro.imagenes_generadas >= MAX_IMAGENES_TOTAL:
                return "Se alcanzó el límite de imágenes de la demo. Describe la idea con palabras."
            sesion.muro.imagenes_generadas += 1
        avisar("imagen", titulo[:60])
        sesion.evento({"tipo": "generando", "titulo": titulo})
        # 1) Intento con el modelo de imágenes; 2) si no hay cuota, el mismo motor dibuja en SVG
        resultado, motor_usado = _imagen_stable(descripcion_en_ingles), "Stable Image Core"
        if resultado is None:
            resultado, motor_usado = _imagen_svg(descripcion_en_ingles), "SVG dibujado por el LLM"
        if resultado is None:
            with _lock_contador:
                sesion.muro.imagenes_generadas -= 1
            return "No se pudo generar la imagen en este momento. Describe la idea con palabras."

        datos, ext = resultado
        id_ = uuid.uuid4().hex[:12]
        sesion.muro.guardar_imagen(id_, datos, ext)
        url = f"/img/{id_}.{ext}"
        sesion.evento({"tipo": "imagen", "url": url, "titulo": titulo, "motor": motor_usado})
        sesion.muro.publicar({"tipo": "imagen", "url": url, "titulo": titulo, "apodo": sesion.apodo, "motor": motor_usado})
        sesion.muro.publicar(sesion.muro.stats())
        return f"Imagen generada ({motor_usado}) y ya visible para el usuario con el título '{titulo}'. No incluyas enlaces."

    return [clima_actual, buscar_info_pasto, generar_imagen]
