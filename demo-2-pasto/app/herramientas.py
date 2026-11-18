"""Las 'ruedas' del agente: herramientas que el motor (LLM) decide cuándo usar."""

import json
import logging
import os
import re
import threading
import time
import uuid
import xml.etree.ElementTree as ET

import httpx
from strands import tool

from . import conocimiento
from .motor import ILUSTRADOR_ID, MODEL_ID, cliente

log = logging.getLogger("agente-galeras")

MAX_IMAGENES_TOTAL = int(os.getenv("MAX_IMAGENES_TOTAL", "250"))
_lock_contador = threading.Lock()

PROMPT_SVG = """You are a vector illustrator. Draw the requested scene as ONE self-contained SVG.
Rules:
- Output ONLY the SVG markup, starting with <svg and ending with </svg>. No markdown, no explanations.
- Use viewBox="0 0 512 512" and xmlns="http://www.w3.org/2000/svg".
- Draw in painter's order: background and sky first, then landscape, then the main subject, then small details.
- Flat, colorful, festive illustration style. Make the main subject big, centered and clearly recognizable.
- Use only basic shapes: rect, circle, ellipse, polygon, path, line, g, linearGradient, radialGradient.
- No <text>, no <script>, no <image>, no <foreignObject>, no external links, no event attributes.
- Keep it under 90 elements."""

_ETIQUETA = re.compile(r"<(/?)([a-zA-Z][\w:-]*)[^<>]*?(/?)>")
_PROHIBIDOS = {"script", "foreignObject", "image", "iframe", "a", "use", "text", "style"}


def _limpiar_svg(svg: str) -> str | None:
    """Valida que sea SVG y quita cualquier cosa ejecutable (defensa extra: además se muestra con <img>)."""
    m = re.search(r"<svg[\s\S]*?</svg>", svg)
    if not m:
        return None
    try:
        raiz = ET.fromstring(m.group(0))
    except ET.ParseError:
        return None
    for padre in raiz.iter():
        for hijo in list(padre):
            if hijo.tag.split("}")[-1] in _PROHIBIDOS:
                padre.remove(hijo)
        for attr in list(padre.attrib):
            nombre = attr.split("}")[-1].lower()
            if nombre.startswith("on") or nombre == "href" or "javascript:" in padre.attrib[attr].lower():
                del padre.attrib[attr]
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(raiz, encoding="unicode")


def _svg_parcial(texto: str) -> str | None:
    """Convierte un SVG a medio escribir en uno válido: corta en la última etiqueta completa y cierra las abiertas."""
    i = texto.find("<svg")
    if i < 0:
        return None
    s = texto[i:]
    if "</svg>" in s:
        return _limpiar_svg(s)
    s = s[: s.rfind(">") + 1]
    pila: list[str] = []
    for m in _ETIQUETA.finditer(s):
        cierre, nombre, auto = m.groups()
        if cierre:
            if pila and pila[-1] == nombre:
                pila.pop()
        elif not auto:
            pila.append(nombre)
    if not pila:
        return None
    return _limpiar_svg(s + "".join(f"</{n}>" for n in reversed(pila)))


def dibujar_en_vivo(descripcion: str, al_avanzar, modelo: str = ILUSTRADOR_ID) -> str | None:
    """Pide el SVG en streaming y va mostrando el boceto mientras el modelo lo escribe."""
    stream = cliente.chat.completions.create(
        model=modelo, stream=True, max_tokens=9000, temperature=0.7,
        messages=[{"role": "system", "content": PROMPT_SVG}, {"role": "user", "content": descripcion[:1500]}],
    )
    texto, ultimo_envio, ultimo_bueno = "", 0.0, None
    for chunk in stream:
        if not chunk.choices:
            continue
        pedazo = chunk.choices[0].delta.content
        if not pedazo:
            continue
        texto += pedazo
        if time.time() - ultimo_envio > 0.35:
            parcial = _svg_parcial(texto)
            if parcial:
                ultimo_bueno = parcial
                al_avanzar(parcial)
                ultimo_envio = time.time()
    return _limpiar_svg(texto) or ultimo_bueno


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

NOMBRE_ILUSTRADOR = {"moonshotai.kimi-k2.5": "Kimi K2.5", "zai.glm-4.7": "GLM-4.7", "openai.gpt-oss-120b": "gpt-oss-120b"}


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
                verify=os.getenv("SSL_CERT_FILE") or True,  # en local respeta un bundle propio (p. ej. antivirus)
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
        """Le pide a un modelo ilustrador que dibuje una imagen (SVG) y la muestra en vivo al usuario y en el muro.
        Úsala cuando pidan dibujar, diseñar o imaginar algo (p. ej. una carroza del carnaval).

        Args:
            descripcion_en_ingles: descripción visual detallada EN INGLÉS (sujeto principal, colores, fondo).
            titulo: título corto en español para mostrar con la imagen.
        """
        with _lock_contador:
            if sesion.muro.imagenes_generadas >= MAX_IMAGENES_TOTAL:
                return "Se alcanzó el límite de imágenes de la demo. Describe la idea con palabras."
            sesion.muro.imagenes_generadas += 1
        avisar("imagen", titulo[:60])
        id_ = uuid.uuid4().hex[:12]
        sesion.evento({"tipo": "generando", "id": id_, "titulo": titulo})

        def al_avanzar(svg: str) -> None:
            ev = {"tipo": "boceto", "id": id_, "svg": svg, "titulo": titulo}
            sesion.evento(ev)
            sesion.muro.publicar({**ev, "apodo": sesion.apodo})

        svg, ilustrador = None, ILUSTRADOR_ID
        for modelo in dict.fromkeys([ILUSTRADOR_ID, MODEL_ID]):  # plan B: el mismo motor dibuja
            try:
                ilustrador = modelo
                svg = dibujar_en_vivo(descripcion_en_ingles, al_avanzar, modelo)
                if svg:
                    break
            except Exception as e:  # noqa: BLE001
                log.warning("El ilustrador %s falló: %s", modelo, e)
        if not svg:
            with _lock_contador:
                sesion.muro.imagenes_generadas -= 1
            sesion.evento({"tipo": "imagen_error", "id": id_})
            sesion.muro.publicar({"tipo": "imagen_error", "id": id_})
            return "No se pudo generar la imagen en este momento. Describe la idea con palabras."

        nombre = NOMBRE_ILUSTRADOR.get(ilustrador, ilustrador)
        sesion.muro.guardar_imagen(id_, svg.encode("utf-8"), "svg")
        ev = {"tipo": "imagen", "id": id_, "url": f"/img/{id_}.svg", "titulo": titulo, "motor": f"dibujado por {nombre}"}
        sesion.evento(ev)
        sesion.muro.publicar({**ev, "apodo": sesion.apodo})
        sesion.muro.publicar(sesion.muro.stats())
        return f"Imagen dibujada por {nombre} y ya visible para el usuario con el título '{titulo}'. No incluyas enlaces ni código."

    return [clima_actual, buscar_info_pasto, generar_imagen]
