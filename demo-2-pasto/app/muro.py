"""Muro en vivo: difunde (broadcast) eventos a todas las pantallas conectadas por SSE."""

import asyncio
import time
from collections import Counter, OrderedDict, deque


class Muro:
    def __init__(self, max_imagenes: int = 60, historial: int = 40):
        self._suscriptores: set[asyncio.Queue] = set()
        self.historial: deque[dict] = deque(maxlen=historial)
        self.imagenes: "OrderedDict[str, tuple[bytes, str]]" = OrderedDict()
        self._max_imagenes = max_imagenes
        self.uso_herramientas: Counter = Counter()
        self.preguntas = 0
        self.personas: set[str] = set()
        self.imagenes_generadas = 0

    # --- suscripciones -------------------------------------------------
    def suscribir(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._suscriptores.add(q)
        return q

    def desuscribir(self, q: asyncio.Queue) -> None:
        self._suscriptores.discard(q)

    def publicar(self, evento: dict) -> None:
        evento = {**evento, "t": time.time()}
        if evento["tipo"] != "stats":
            self.historial.append(evento)
        for q in list(self._suscriptores):
            try:
                q.put_nowait(evento)
            except asyncio.QueueFull:
                pass  # pantalla lenta: se pierde el evento, no bloqueamos a nadie

    def stats(self) -> dict:
        return {
            "tipo": "stats",
            "preguntas": self.preguntas,
            "personas": len(self.personas),
            "imagenes": self.imagenes_generadas,
            "herramientas": dict(self.uso_herramientas),
        }

    # --- imágenes en memoria ------------------------------------------
    def guardar_imagen(self, id_: str, datos: bytes, ext: str = "png") -> None:
        self.imagenes[id_] = (datos, ext)
        while len(self.imagenes) > self._max_imagenes:
            self.imagenes.popitem(last=False)
