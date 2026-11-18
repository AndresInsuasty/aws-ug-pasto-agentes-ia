"""Base de conocimiento local (curada a mano) sobre Pasto y Nariño.

Es intencionalmente pequeña: sirve para mostrar que un agente puede
consultar NUESTROS datos en vez de inventar. En producción esto sería
una Knowledge Base de Bedrock, una base vectorial o una API.
"""

import unicodedata

DOCUMENTOS: list[dict] = [
    {
        "titulo": "San Juan de Pasto",
        "claves": ["pasto", "ciudad", "historia", "altura", "clima", "sorpresa", "nariño", "capital"],
        "texto": (
            "San Juan de Pasto es la capital del departamento de Nariño, al suroccidente de Colombia. "
            "Está a unos 2.500 metros sobre el nivel del mar, en el Valle de Atriz, a los pies del volcán Galeras. "
            "Su temperatura promedio ronda los 13-14 °C, así que el saco es casi obligatorio. "
            "Es conocida como la 'Ciudad Sorpresa de Colombia'."
        ),
    },
    {
        "titulo": "Carnaval de Negros y Blancos",
        "claves": ["carnaval", "negros", "blancos", "enero", "unesco", "carroza", "desfile", "castañeda", "fiesta"],
        "texto": (
            "El Carnaval de Negros y Blancos es la fiesta más grande del sur de Colombia y fue declarado por la UNESCO "
            "Patrimonio Cultural Inmaterial de la Humanidad en 2009. Se vive entre finales de diciembre y el 7 de enero. "
            "Momentos clave: el Carnaval del Agua (28 de dic.), el desfile de Años Viejos (31 de dic.), "
            "la llegada de la Familia Castañeda (4 de ene.), el Día de Negros (5 de ene., la gente se pinta con cosmético negro) "
            "y el Día de Blancos con el Gran Desfile Magno (6 de ene.), donde desfilan carrozas monumentales "
            "hechas por artesanos con papel maché, icopor y mecanismos que las hacen moverse. "
            "El talco y la espuma son protagonistas del Día de Blancos."
        ),
    },
    {
        "titulo": "Barniz de Pasto (mopa-mopa)",
        "claves": ["barniz", "mopa", "artesania", "artesanía", "unesco", "madera", "arte"],
        "texto": (
            "El barniz de Pasto es una técnica artesanal que usa la resina del arbusto mopa-mopa, de la selva del Putumayo. "
            "La resina se mastica/ablanda, se tiñe, se estira en láminas finísimas y se aplica sobre madera. "
            "En 2020 la UNESCO lo inscribió en la Lista del Patrimonio Cultural Inmaterial que requiere medidas urgentes de salvaguardia."
        ),
    },
    {
        "titulo": "Laguna de la Cocha",
        "claves": ["cocha", "laguna", "lago", "guamuez", "corota", "trucha", "encano", "paseo"],
        "texto": (
            "La Laguna de la Cocha (o lago Guamuez) está a unos 25 km de Pasto, cerca del corregimiento de El Encano, "
            "a casi 2.800 m de altura. Es uno de los lagos más grandes de Colombia. En su interior está la Isla La Corota, "
            "un santuario de flora. Plan típico: paseo en lancha, casas de colores en el muelle y trucha arcoíris al almuerzo."
        ),
    },
    {
        "titulo": "Volcán Galeras",
        "claves": ["galeras", "volcan", "volcán", "montaña", "santuario", "fauna", "flora"],
        "texto": (
            "El Galeras es un volcán activo de unos 4.270 m que vigila a Pasto. Es uno de los más monitoreados de Colombia "
            "(Servicio Geológico Colombiano). Su zona alta es el Santuario de Fauna y Flora Galeras, con páramo y frailejones. "
            "El acceso a la cima depende del nivel de actividad volcánica."
        ),
    },
    {
        "titulo": "Santuario de Las Lajas",
        "claves": ["lajas", "ipiales", "santuario", "iglesia", "guaitara", "guáitara", "puente"],
        "texto": (
            "El Santuario de Nuestra Señora de Las Lajas queda en Ipiales, a unas 2 horas de Pasto, cerca de la frontera con Ecuador. "
            "Es una basílica de estilo neogótico construida sobre un puente en el cañón del río Guáitara, "
            "y es considerada una de las iglesias más impresionantes del mundo."
        ),
    },
    {
        "titulo": "Comida típica de Nariño",
        "claves": ["comida", "cuy", "hervido", "empanada", "añejo", "quimbolito", "helado", "paila", "frito", "comer", "gastronomia", "gastronomía", "plato"],
        "texto": (
            "Imperdibles: el cuy asado (el plato estrella), el frito pastuso, las empanadas de añejo, "
            "el quimbolito, el helado de paila (batido a mano en una paila de cobre sobre hielo) "
            "y el hervido: bebida caliente de fruta (lulo, maracuyá, mora) que para los adultos lleva aguardiente. "
            "Perfecto para el frío pastuso."
        ),
    },
    {
        "titulo": "Expresiones pastusas",
        "claves": ["achichay", "ananay", "atatay", "expresion", "expresión", "dicho", "hablar", "palabra", "quechua"],
        "texto": (
            "Expresiones de origen quechua que se escuchan en Pasto: '¡Achichay!' (¡qué frío!), "
            "'¡Ananay!' (¡qué bonito!), '¡Atatay!' (¡qué asco / qué feo!) y '¡Arrarray!' (¡qué calor / quema!)."
        ),
    },
    {
        "titulo": "AWS User Group Pasto",
        "claves": ["aws", "user group", "comunidad", "meetup", "nube", "cloud", "grupo", "evento"],
        "texto": (
            "El AWS User Group Pasto es la comunidad de AWS en Pasto, Nariño, parte de la red global de AWS User Groups "
            "(más de 590 grupos en más de 100 países). Organiza meetups gratuitos para aprender sobre la nube, "
            "inteligencia artificial y carrera profesional, con charlas, demos en vivo y networking."
        ),
    },
]


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")


def buscar(consulta: str, max_resultados: int = 3) -> list[dict]:
    """Búsqueda simple por palabras clave (sin vectores, para que se entienda)."""
    palabras = set(_normalizar(consulta).split())
    puntajes = []
    for doc in DOCUMENTOS:
        claves = {_normalizar(c) for c in doc["claves"]}
        cuerpo = _normalizar(doc["titulo"] + " " + doc["texto"])
        puntaje = sum(3 for p in palabras if p in claves) + sum(1 for p in palabras if len(p) > 3 and p in cuerpo)
        if puntaje:
            puntajes.append((puntaje, doc))
    puntajes.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in puntajes[:max_resultados]]
