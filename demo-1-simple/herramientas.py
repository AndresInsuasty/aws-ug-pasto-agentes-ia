"""Ruedas extra para la demo 1: hechas por nosotros con @tool."""

import ast
import operator
from datetime import datetime
from zoneinfo import ZoneInfo

from strands import tool

_OPERADORES = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _evaluar(nodo):
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, (int, float)):
        return nodo.value
    if isinstance(nodo, ast.BinOp) and type(nodo.op) in _OPERADORES:
        return _OPERADORES[type(nodo.op)](_evaluar(nodo.left), _evaluar(nodo.right))
    if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _OPERADORES:
        return _OPERADORES[type(nodo.op)](_evaluar(nodo.operand))
    raise ValueError("Solo se permiten números y + - * / ** %")


@tool
def calcular(expresion: str) -> str:
    """Calcula una expresión matemática, por ejemplo '3111 * 37 / 4'."""
    try:
        return str(_evaluar(ast.parse(expresion, mode="eval").body))
    except Exception as e:  # noqa: BLE001
        return f"No pude calcular eso: {e}"


@tool
def hora_actual(zona_horaria: str = "America/Bogota") -> str:
    """Devuelve la fecha y hora actual en una zona horaria IANA (p. ej. 'America/Bogota')."""
    try:
        return datetime.now(ZoneInfo(zona_horaria)).strftime("%A %d/%m/%Y %H:%M:%S (%Z)")
    except Exception:  # noqa: BLE001
        return f"Zona horaria desconocida: {zona_horaria}"
