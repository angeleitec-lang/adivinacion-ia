#!/usr/bin/env python3
"""Cliente LLM local para nodos de inferencia (A4.4).

Round-robin entre endpoints, reintentos con backoff exponencial,
y extracción robusta de JSON.
"""

from __future__ import annotations

import json
import random
import time
from typing import Any, Callable, Dict, List, Optional

import requests


class LLMClient:
    """Cliente para LLM local (OpenAI-compatible) con round-robin y reintentos."""

    def __init__(
        self,
        endpoints: Optional[List[str]] = None,
        model: str = "halogen-qwen3.8-flash-next",
        timeout: float = 60.0,
        simulado: Optional[Callable[[str, str], str]] = None,
    ):
        """
        Args:
            endpoints: URLs base de los endpoints (ej. ["http://10.0.0.3:8000/v1", "http://10.0.0.4:8000/v1"])
            model: Nombre del modelo a usar
            timeout: Timeout por petición en segundos
            simulado: Función (sistema, usuario) -> respuesta para tests (inyectable)
        """
        self.endpoints = endpoints or [
            "http://10.0.0.3:8000/v1",
            "http://10.0.0.4:8000/v1",
        ]
        self.model = model
        self.timeout = timeout
        self.simulado = simulado
        self._idx = 0  # round-robin index

    def _siguiente_endpoint(self) -> str:
        """Selecciona el siguiente endpoint round-robin."""
        ep = self.endpoints[self._idx % len(self.endpoints)]
        self._idx += 1
        return ep

    def _chat_real(self, sistema: str, usuario: str, max_tokens: int, temperature: float) -> str:
        """Ejecuta una petición real al endpoint."""
        endpoint = self._siguiente_endpoint()
        url = f"{endpoint}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        resp = requests.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def chat(
        self,
        sistema: str,
        usuario: str,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        max_reintentos: int = 3,
    ) -> str:
        """Envía una petición de chat con reintentos y backoff exponencial.

        Args:
            sistema: Prompt de sistema
            usuario: Prompt de usuario
            max_tokens: Tokens máximos de respuesta
            temperature: Temperatura de muestreo
            max_reintentos: Número máximo de reintentos ante fallo

        Returns:
            Texto de la respuesta

        Raises:
            Exception: Si se agotan los reintentos
        """
        if self.simulado:
            return self.simulado(sistema, usuario)

        espera = 1.0
        ultima_exc = None
        for intento in range(max_reintentos + 1):
            try:
                return self._chat_real(sistema, usuario, max_tokens, temperature)
            except Exception as e:
                ultima_exc = e
                if intento < max_reintentos:
                    time.sleep(espera)
                    espera *= 2  # backoff exponencial
                else:
                    raise
        raise ultima_exc  # type: ignore

    def _extraer_json(self, texto: str) -> Dict[str, Any]:
        """Extrae el primer objeto JSON válido del texto.

        Tolera bloques ```json ... ``` y texto circundante.
        """
        # Buscar bloque ```json ... ```
        inicio = texto.find("```json")
        if inicio != -1:
            fin = texto.find("```", inicio + 7)
            if fin != -1:
                candidato = texto[inicio + 7:fin].strip()
                try:
                    return json.loads(candidato)
                except json.JSONDecodeError:
                    pass

        # Buscar bloque ``` ... ``` genérico
        inicio = texto.find("```")
        if inicio != -1:
            fin = texto.find("```", inicio + 3)
            if fin != -1:
                candidato = texto[inicio + 3:fin].strip()
                try:
                    return json.loads(candidato)
                except json.JSONDecodeError:
                    pass

        # Buscar primer { ... } balanceado
        inicio = texto.find("{")
        if inicio != -1:
            nivel = 0
            for i, ch in enumerate(texto[inicio:], start=inicio):
                if ch == "{":
                    nivel += 1
                elif ch == "}":
                    nivel -= 1
                    if nivel == 0:
                        candidato = texto[inicio:i + 1]
                        try:
                            return json.loads(candidato)
                        except json.JSONDecodeError:
                            break

        raise ValueError("No se encontró JSON válido en la respuesta")

    def chat_json(
        self,
        sistema: str,
        usuario: str,
        validar: Callable[[Dict[str, Any]], None],
        max_tokens: int = 1024,
        temperature: float = 0.2,
        intentos: int = 3,
    ) -> Dict[str, Any]:
        """Ejecuta chat y valida la respuesta JSON con reintentos.

        Args:
            sistema: Prompt de sistema
            usuario: Prompt de usuario
            validar: Función que recibe el dict y lanza ValueError si no es válido
            max_tokens: Tokens máximos
            temperature: Temperatura
            intentos: Intentos totales (incluye el primero)

        Returns:
            Dict validado

        Raises:
            ValueError: Si no se obtiene JSON válido tras los intentos
        """
        ultima_exc = None
        for intento in range(intentos):
            try:
                texto = self.chat(sistema, usuario, max_tokens, temperature)
                data = self._extraer_json(texto)
                validar(data)
                return data
            except Exception as e:
                ultima_exc = e
                # En el siguiente intento, añadir el error al prompt de usuario
                if intento < intentos - 1:
                    usuario = (
                        f"{usuario}\n\n"
                        f"[INTENTO {intento + 1} FALLÓ: {e}]\n"
                        f"Por favor, responde SOLO con el JSON corregido."
                    )
        raise ValueError(f"JSON inválido tras {intentos} intentos: {ultima_exc}")


if __name__ == "__main__":
    # Test rápido con simulado
    def simulado_ok(sistema, usuario):
        return '```json\n{"tipo": "lectura_individual", "familia": "tarot-lectura", "tirada": "tres_cartas", "n_cartas": 3, "calidad": 4, "motivo": "ok"}\n```'

    client = LLMClient(simulado=simulado_ok)
    print(client.chat("sys", "user"))
    print(client.chat_json("sys", "user", lambda d: None))
