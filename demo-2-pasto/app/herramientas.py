"""Las 'ruedas' del agente: herramientas que el motor (LLM) decide cuándo usar."""

import base64
import json
import os
import threading
import uuid

import boto3
import httpx
from strands import tool

from . import conocimiento

IMAGE_MODEL_ID = os.getenv("IMAGE_MODEL_ID", "stability.stable-image-core-v1:1")
IMAGE_REGION = os.getenv("IMAGE_REGION", os.getenv("AWS_REGION", "us-west-2"))
MAX_IMAGENES_TOTAL = int(os.getenv("MAX_IMAGENES_TOTAL", "250"))

_bedrock_img = boto3.client("bedrock-runtime", region_name=IMAGE_REGION)
_lock_contador = threading.Lock()

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
        """Genera una imagen con Stable Image Core (Bedrock) y la muestra al usuario y en el muro en vivo.
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
        try:
            resp = _bedrock_img.invoke_model(
                modelId=IMAGE_MODEL_ID,
                body=json.dumps({
                    "prompt": descripcion_en_ingles[:1500],
                    "negative_prompt": "text, letters, watermark, blurry, low quality",
                    "aspect_ratio": "1:1",
                    "output_format": "png",
                }),
            )
            b64 = json.loads(resp["body"].read())["images"][0]
        except Exception as e:  # noqa: BLE001
            with _lock_contador:
                sesion.muro.imagenes_generadas -= 1
            return f"No se pudo generar la imagen ({e.__class__.__name__}: {str(e)[:120]})."

        id_ = uuid.uuid4().hex[:12]
        sesion.muro.guardar_imagen(id_, base64.b64decode(b64))
        url = f"/img/{id_}.png"
        sesion.evento({"tipo": "imagen", "url": url, "titulo": titulo})
        sesion.muro.publicar({"tipo": "imagen", "url": url, "titulo": titulo, "apodo": sesion.apodo})
        sesion.muro.publicar(sesion.muro.stats())
        return f"Imagen generada y ya visible para el usuario con el título '{titulo}'. No incluyas enlaces."

    return [clima_actual, buscar_info_pasto, generar_imagen]
