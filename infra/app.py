#!/usr/bin/env python3
"""Infraestructura de la demo 'Galeritas' (AWS CDK).

Celulares ─HTTPS─► CloudFront ─► Application Load Balancer ─► Fargate (contenedor) ─► Bedrock (Nova)

Parámetros (contexto CDK):
  -c pin=CODIGO         código de acceso que pide la app (recomendado)
  -c email=tu@correo    correo para la alerta de presupuesto (opcional)
  -c presupuesto=10     límite mensual en USD para la alerta (opcional)
  -c modelo=...         id del modelo de texto en Bedrock (opcional)
"""

import aws_cdk as cdk
from aws_cdk import (
    aws_budgets as budgets,
    aws_cloudfront as cf,
    aws_cloudfront_origins as origins,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class GaleritasStack(cdk.Stack):
    def __init__(self, scope: Construct, id_: str, **kwargs) -> None:
        super().__init__(scope, id_, **kwargs)

        pin = self.node.try_get_context("pin") or ""
        email = self.node.try_get_context("email")
        presupuesto = float(self.node.try_get_context("presupuesto") or 10)
        modelo = self.node.try_get_context("modelo") or "us.amazon.nova-lite-v1:0"
        modelo_imagen = self.node.try_get_context("modeloImagen") or "amazon.nova-canvas-v1:0"
        region_imagen = self.node.try_get_context("regionImagen") or "us-east-1"

        # Red: solo subredes públicas (sin NAT Gateway = más barato)
        vpc = ec2.Vpc(
            self, "Vpc", max_azs=2, nat_gateways=0,
            subnet_configuration=[ec2.SubnetConfiguration(name="publica", subnet_type=ec2.SubnetType.PUBLIC)],
        )
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)

        servicio = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "Galeritas",
            cluster=cluster,
            cpu=1024, memory_limit_mib=2048,
            desired_count=1,  # el muro en vivo vive en memoria: una sola tarea
            public_load_balancer=True,
            assign_public_ip=True,
            task_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=ecs.CpuArchitecture.X86_64,
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
            ),
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("../demo-2-pasto", platform=ecr_assets.Platform.LINUX_AMD64),
                container_port=8080,
                environment={
                    "AWS_REGION": self.region,
                    "MODEL_ID": modelo,
                    "IMAGE_MODEL_ID": modelo_imagen,
                    "IMAGE_REGION": region_imagen,
                    "ACCESS_CODE": pin,
                },
                log_driver=ecs.LogDrivers.aws_logs(stream_prefix="galeritas", log_retention=logs.RetentionDays.ONE_WEEK),
            ),
            min_healthy_percent=0, max_healthy_percent=100,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
        )
        servicio.target_group.configure_health_check(path="/health", healthy_threshold_count=2, interval=cdk.Duration.seconds(15))
        servicio.target_group.set_attribute("deregistration_delay.timeout_seconds", "5")
        servicio.load_balancer.set_attribute("idle_timeout.timeout_seconds", "120")  # streaming SSE

        # Permiso para usar el motor (Bedrock)
        servicio.task_definition.task_role.add_to_principal_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse", "bedrock:ConverseStream"],
            resources=["*"],
        ))

        # HTTPS gratis con el dominio *.cloudfront.net
        distribucion = cf.Distribution(
            self, "Cdn",
            default_behavior=cf.BehaviorOptions(
                origin=origins.LoadBalancerV2Origin(
                    servicio.load_balancer,
                    protocol_policy=cf.OriginProtocolPolicy.HTTP_ONLY,
                    read_timeout=cdk.Duration.seconds(60),
                ),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cf.AllowedMethods.ALLOW_ALL,
                cache_policy=cf.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
                compress=False,  # no comprimir para que el streaming fluya
            ),
            price_class=cf.PriceClass.PRICE_CLASS_ALL,
        )

        # Alerta de presupuesto por correo
        if email:
            budgets.CfnBudget(
                self, "Presupuesto",
                budget=budgets.CfnBudget.BudgetDataProperty(
                    budget_name="aws-ug-pasto-demo",
                    budget_type="COST", time_unit="MONTHLY",
                    budget_limit=budgets.CfnBudget.SpendProperty(amount=presupuesto, unit="USD"),
                ),
                notifications_with_subscribers=[
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            comparison_operator="GREATER_THAN", notification_type=tipo,
                            threshold=umbral, threshold_type="PERCENTAGE",
                        ),
                        subscribers=[budgets.CfnBudget.SubscriberProperty(address=email, subscription_type="EMAIL")],
                    )
                    for tipo, umbral in (("ACTUAL", 50), ("ACTUAL", 100), ("FORECASTED", 100))
                ],
            )

        cdk.CfnOutput(self, "DemoUrl", value=f"https://{distribucion.distribution_domain_name}")
        cdk.CfnOutput(self, "MuroUrl", value=f"https://{distribucion.distribution_domain_name}/muro")


app = cdk.App()
GaleritasStack(app, "GaleritasPasto", env=cdk.Environment(region=app.node.try_get_context("region") or "us-west-2"))
cdk.Tags.of(app).add("proyecto", "aws-ug-pasto")
app.synth()
