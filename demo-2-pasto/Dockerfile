FROM public.ecr.aws/docker/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

# Si wheels/ trae paquetes (.whl) se instalan SIN internet: útil cuando un proxy o
# antivirus que inspecciona HTTPS rompe las descargas dentro de Docker.
# Si está vacío, pip descarga normalmente desde PyPI.
COPY requirements.txt .
COPY wheels/ /tmp/wheels/
RUN set -e; \
    if ls /tmp/wheels/*.whl >/dev/null 2>&1; then \
      pip install --no-cache-dir --no-index --find-links /tmp/wheels -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi; \
    rm -rf /tmp/wheels

COPY app ./app

RUN useradd -m agente && chown -R agente /srv
USER agente

EXPOSE 8080
# Un solo proceso: el muro en vivo guarda su estado en memoria
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
