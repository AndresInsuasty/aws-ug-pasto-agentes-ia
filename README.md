# 🚗 Agentes de IA en AWS: mismo motor, distintos autos

Charla del **AWS User Group Pasto** 🇨🇴. Explica qué es un agente de IA con una metáfora:

> El **LLM es el motor**. Un **agente es el auto completo**: motor + volante (instrucciones) + baúl (memoria) + ruedas (herramientas).
> Con el mismo motor se arman autos de carga, de carreras o de rescate. Con el mismo LLM se arman agentes de código, de imágenes, de música… y el tuyo.

| | |
|---|---|
| 🎤 **Diapositivas** | [`slides/`](slides/index.html): ábrelas en el navegador, no necesitan servidor |
| 🛠️ **Demo 1** | [`demo-1-simple/`](demo-1-simple/agente_simple.py): tu primer agente con Strands en ~20 líneas |
| 🌋 **Demo 2** | [`demo-2-pasto/`](demo-2-pasto/): el *Agente Galeras*, un guía de Pasto para que el público use desde el celular |
| 🏗️ **Infra** | [`infra/`](infra/app.py): AWS CDK → Fargate + ALB + CloudFront + alerta de presupuesto |

## Arquitectura de la demo 2

```
📱 celulares ──HTTPS──► CloudFront ──► Load Balancer ──► AWS Fargate (contenedor)
📺 muro en vivo ◄──SSE─────────────────────────────────┘   │  FastAPI + Strands Agents
                                                           ├─► 🧠 Amazon Bedrock · Nova Lite (motor)
                                                           ├─► 🎨 Stable Image Core en Bedrock (imágenes)
                                                           ├─► 🌦️ Open-Meteo (clima real)
                                                           └─► 📚 base de conocimiento de Pasto
```

## Requisitos

- Python 3.12+ y [uv](https://docs.astral.sh/uv/)
- Una cuenta de AWS con acceso a Amazon Bedrock (modelos Amazon Nova)
- AWS CLI configurado (`aws configure`) con un usuario IAM, **no root**
- Para desplegar: Node.js 18+ y Docker Desktop encendido

```bash
uv sync
```

## Demo 1: tu primer agente

```bash
uv run python demo-1-simple/agente_simple.py
```

## Demo 2: Agente Galeras en tu máquina

```bash
cd demo-2-pasto
uv run --project .. uvicorn app.main:app --reload --port 8080
# chat:  http://localhost:8080
# muro:  http://localhost:8080/muro
```

Variables opcionales: `ACCESS_CODE` (PIN), `MODEL_ID`, `AWS_REGION`, `IMAGE_MODEL_ID`, `IMAGE_REGION`, `MAX_IMAGENES_TOTAL`.

## Desplegar en AWS

```bash
cd infra
npx aws-cdk@2.1148.1 bootstrap                     # solo la primera vez por cuenta/región
npx aws-cdk@2.1148.1 deploy -c pin=TU_PIN -c email=tu@correo.com -c presupuesto=10
```

Al terminar verás `DemoUrl` (https://xxxx.cloudfront.net). En las diapositivas presiona **C** y pega la URL y el PIN para que el QR quede listo.

### 💸 Apagar todo después del evento

```bash
cd infra
npx aws-cdk@2.1148.1 destroy
```

Encendida, la demo cuesta aproximadamente **1–1.5 USD/día** (Fargate + Load Balancer), más el uso de Bedrock (Nova Lite cuesta centavos; cada imagen de Stable Image Core, unos 0.04 USD).

## Presentar

- Flechas o espacio para avanzar · **S** abre las notas del orador · **C** configura la URL y el PIN de la demo · **F** pantalla completa · **Esc** vista general.
- También puedes abrir `slides/index.html?demo=https://xxxx.cloudfront.net&pin=TU_PIN`.

## Recursos

- [Strands Agents](https://strandsagents.com)
- [Amazon Bedrock](https://aws.amazon.com/bedrock/)
- [AWS Skill Builder](https://skillbuilder.aws)
- [AWS Builder Center](https://builder.aws.com)
