"""Agente Galeras (guía de Pasto) — FastAPI + Strands Agents + Amazon Bedrock (gpt-oss + Kimi).

Rutas:
  /            app para el celular (chat)
  /muro        pantalla grande para proyectar (muro en vivo)
  /api/...     API (SSE para streaming)
"""

import asyncio
import json
import os
import re
import secrets
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from strands import Agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from strands.models.openai import OpenAIModel

from .herramientas import crear_herramientas
from .motor import MODEL_ID, config_motor
from .muro import Muro

ACCESS_CODE = os.getenv("ACCESS_CODE", "").strip()
MAX_SESIONES = int(os.getenv("MAX_SESIONES", "400"))
MAX_CHARS = 400
HILOS = int(os.getenv("HILOS", "64"))

STATIC = Path(__file__).parent / "static"

SYSTEM_PROMPT = """Eres el "Agente Galeras", un guía turístico pastuso, alegre y orgulloso de Nariño.
Hablas español de Colombia y de vez en cuando usas expresiones pastusas como "¡Achichay!" (qué frío).

Reglas:
- Respuestas CORTAS (máximo 5-6 líneas): la gente te lee desde el celular en un meetup.
- Para datos de Pasto/Nariño usa SIEMPRE la herramienta buscar_info_pasto; si no encuentras el dato, dilo con honestidad.
- Para clima, ropa recomendada o planes al aire libre usa clima_actual (datos reales).
- Si piden dibujar, diseñar o imaginar algo (carrozas, cuyes astronautas, paisajes...) usa generar_imagen
  con una descripción visual detallada en inglés. Para carrozas del carnaval describe: giant colorful parade float
  with big papier-mâché sculptures, Carnaval de Negros y Blancos in Pasto Colombia, festive crowd, Andean mountains, Galeras volcano.
- Mientras se dibuja la imagen, el usuario la ve aparecer en vivo: no describas el SVG ni pongas enlaces.
- Puedes combinar varias herramientas en una misma respuesta.
- Mantente en temas de Pasto, Nariño, turismo, cultura, la nube de AWS y la IA. Sé respetuoso siempre.
"""

@asynccontextmanager
async def ciclo_de_vida(_app):
    # Las herramientas síncronas (dibujar, clima) corren en hilos que casi siempre esperan a la red.
    # El grupo por defecto de Python solo trae ~5 hilos con 1 vCPU: con más gente dibujando, harían cola.
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=HILOS))
    yield


app = FastAPI(title="Agente guía de Pasto", lifespan=ciclo_de_vida)
muro = Muro()


class Sesion:
    def __init__(self, apodo: str):
        self.id = secrets.token_urlsafe(16)
        self.apodo = apodo
        self.muro = muro
        self.lock = asyncio.Lock()
        self.creada = time.time()
        self._cola: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.agente = Agent(
            model=OpenAIModel(
                model_id=MODEL_ID, params={"temperature": 0.6, "max_tokens": 1200}, **config_motor(),
            ),
            system_prompt=SYSTEM_PROMPT,
            tools=crear_herramientas(self),
            conversation_manager=SlidingWindowConversationManager(window_size=12),
            callback_handler=None,
        )

    def evento(self, ev: dict) -> None:
        """Envía un evento al celular de esta sesión (seguro desde hilos de herramientas)."""
        if self._cola and self._loop:
            self._loop.call_soon_threadsafe(self._cola.put_nowait, ev)


sesiones: "OrderedDict[str, Sesion]" = OrderedDict()


def limpiar(texto: str) -> str:
    """Algunos modelos 'piensan en voz alta' con <thinking>...</thinking>; eso no se muestra."""
    texto = re.sub(r"<thinking>.*?</thinking>", "", texto, flags=re.S)
    texto = re.sub(r"<thinking>.*", "", texto, flags=re.S)
    return re.sub(r"</?response>", "", texto).strip()


# ---------------------------------------------------------------- páginas
@app.get("/")
def pagina_chat():
    return FileResponse(STATIC / "index.html")


@app.get("/muro")
def pagina_muro():
    return FileResponse(STATIC / "muro.html")


@app.get("/health")
def health():
    return {"ok": True, "modelo": MODEL_ID}


TIPOS_IMAGEN = {"png": "image/png", "svg": "image/svg+xml"}


@app.get("/img/{id_}.{ext}")
def imagen(id_: str, ext: str):
    guardada = muro.imagenes.get(id_)
    if not guardada or guardada[1] != ext:
        raise HTTPException(404)
    return Response(guardada[0], media_type=TIPOS_IMAGEN[ext], headers={
        "Cache-Control": "public, max-age=86400",
        # aunque un SVG se abra directo, no puede ejecutar nada
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        "X-Content-Type-Options": "nosniff",
    })


# ---------------------------------------------------------------- API
class Entrada(BaseModel):
    apodo: str = Field(min_length=1, max_length=24)
    pin: str = ""


class Mensaje(BaseModel):
    sesion: str
    mensaje: str = Field(min_length=1, max_length=MAX_CHARS)


@app.get("/api/config")
def config():
    return {"pin_requerido": bool(ACCESS_CODE), "modelo": MODEL_ID}


@app.post("/api/entrar")
def entrar(datos: Entrada):
    if ACCESS_CODE and datos.pin.strip().upper() != ACCESS_CODE.upper():
        raise HTTPException(403, "Código de acceso incorrecto")
    apodo = re.sub(r"[<>]", "", datos.apodo.strip())[:24] or "Anónimo"
    s = Sesion(apodo)
    sesiones[s.id] = s
    while len(sesiones) > MAX_SESIONES:
        sesiones.popitem(last=False)
    muro.personas.add(s.id)
    muro.publicar({"tipo": "llegada", "apodo": apodo})
    muro.publicar(muro.stats())
    return {"sesion": s.id, "apodo": apodo}


def sse(ev: dict) -> str:
    return f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
async def chat(datos: Mensaje):
    s = sesiones.get(datos.sesion)
    if not s:
        raise HTTPException(401, "Sesión expirada, vuelve a entrar")
    if s.lock.locked():
        raise HTTPException(429, "Espera a que termine la respuesta anterior")

    async def flujo():
        async with s.lock:
            cola: asyncio.Queue = asyncio.Queue()
            s._cola, s._loop = cola, asyncio.get_running_loop()
            muro.preguntas += 1
            muro.publicar({"tipo": "pregunta", "apodo": s.apodo, "texto": datos.mensaje})
            muro.publicar(muro.stats())

            async def correr():
                try:
                    async for ev in s.agente.stream_async(datos.mensaje):
                        if "data" in ev and ev["data"]:
                            cola.put_nowait({"tipo": "texto", "delta": ev["data"]})
                except Exception as e:  # noqa: BLE001
                    cola.put_nowait({"tipo": "error", "mensaje": f"{e.__class__.__name__}: {str(e)[:200]}"})
                finally:
                    cola.put_nowait(None)

            tarea = asyncio.create_task(correr())
            respuesta = ""
            try:
                while True:
                    try:
                        ev = await asyncio.wait_for(cola.get(), timeout=10)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"  # mantiene viva la conexión (CloudFront/ALB) mientras se dibuja
                        continue
                    if ev is None:
                        break
                    if ev["tipo"] == "texto":
                        respuesta += ev["delta"]
                    yield sse(ev)
            finally:
                if not tarea.done():
                    await tarea
                s._cola = None
            final = limpiar(respuesta)
            if final:
                muro.publicar({"tipo": "respuesta", "apodo": s.apodo, "texto": final[:320]})
            yield sse({"tipo": "fin"})

    return StreamingResponse(flujo(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/muro/stream")
async def muro_stream(request: Request):
    async def flujo():
        q = muro.suscribir()
        try:
            yield sse(muro.stats())
            for ev in list(muro.historial):
                yield sse({**ev, "historial": True})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield sse(ev)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            muro.desuscribir(q)

    return StreamingResponse(flujo(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
