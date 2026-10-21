#!/usr/bin/env python3
"""Cliente LLM local para nodos de inferencia (A4.4).

Round-robin entre endpoints, reintentos con backoff exponencial,
y extracción robusta de JSON. Ampliación T65: soporta, además de
endpoints locales, un backend en la nube con cabecera Authorization
Bearer tomada de una variable de entorno, modelo propio por endpoint y
límite de concurrencia/tasa configurable (reintenta con backoff ante 429).
"""

from __future__ import annotations

import collections
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import requests


class RateLimitError(Exception):
    """HTTP 429: se superó el límite de tasa del proveedor."""

    def __init__(self, retry_after: Optional[str] = None):
        super().__init__("Límite de tasa HTTP 429")
        self.retry_after = retry_after

    @property
    def backoff(self) -> Optional[float]:
        """Segundos a esperar según `Retry-After`, o None si no aplica."""
        if self.retry_after is None:
            return None
        try:
            return max(float(self.retry_after), 0.0)
        except ValueError:
            return None


class ContenidoVacioError(Exception):
    """El modelo devolvió una respuesta vacía (`content=None`).

    Suele ocurrir cuando el modelo agota el presupuesto de tokens en
    razonamiento antes de emitir contenido visible (finish_reason=length).
    Es reintentable en `chat()`.
    """


class _LimitadorTasa:
    """Limita las peticiones a `max_por_minuto` por ventana de 60 s.

    Thread-safe: si se excede la tasa, `esperar()` bloquea hasta que hay
    hueco. Con `max_por_minuto <= 0` no limita (comportamiento por defecto).
    """

    def __init__(self, max_por_minuto: int):
        self.maximo = max(int(max_por_minuto), 0)
        self._lock = threading.Lock()
        self._marcas = collections.deque()

    def esperar(self) -> None:
        if self.maximo <= 0:
            return
        while True:
            with self._lock:
                ahora = time.time()
                while self._marcas and ahora - self._marcas[0] > 60:
                    self._marcas.popleft()
                if len(self._marcas) < self.maximo:
                    self._marcas.append(ahora)
                    return
                espera = self._marcas[0] + 60 - ahora
            time.sleep(max(espera, 0.01))


class LLMClient:
    """Cliente para LLM (OpenAI-compatible) con round-robin y reintentos.

    Ampliación T65: cada endpoint puede ser una cadena (local, sin auth), un
    `(url, modelo)` o un dict con `url`, `model` (opcional) y `api_key_env`
    (opcional, nombre de la variable de entorno con la clave para el Bearer).
    La clave se lee de la variable en tiempo de ejecución y nunca se registra.
    """

    def __init__(
        self,
        endpoints: Optional[List[Any]] = None,
        model: str = "halogen-qwen3.8-flash-next",
        timeout: float = 60.0,
        simulado: Optional[Callable[[str, str], str]] = None,
        api_key_env: Optional[str] = None,
        max_concurrencia: int = 1,
        tasa_max_por_minuto: int = 0,
        metricas: Optional[Dict[str, float]] = None,
        max_tokens_default: int = 1024,
        reasoning_effort: Optional[str] = None,
        max_completion_tokens: Optional[int] = None,
    ):
        """
        Args:
            endpoints: URLs base o especificaciones (ver doc de clase). Por
                defecto los nodos locales 10.0.0.3 / 10.0.0.4.
            model: Nombre del modelo por defecto (se usa si el endpoint no da
                el suyo propio).
            timeout: Timeout por petición en segundos.
            simulado: Función (sistema, usuario) -> respuesta (inyectable).
            api_key_env: Nombre de la variable de entorno con la clave para
                cabecera `Authorization: Bearer`. Se aplica a los endpoints que
                no la especifiquen. None = sin autenticación.
            max_concurrencia: Máximo de peticiones de red simultáneas.
            tasa_max_por_minuto: Máximo de peticiones por minuto; 0 = sin
                límite de tasa.
            metricas: Dict opcional donde se acumulan latencia y tokens
                (peticiones, latencia_total, max_latencia, prompt_tokens,
                completion_tokens). None = no registrar.
            max_tokens_default: Presupuesto de tokens por defecto cuando
                `chat()`/`chat_json()` no reciben `max_tokens` explícito.
            reasoning_effort: Nivel de esfuerzo de razonamiento del proveedor
                (p. ej. "instant", "low", "medium", "high"). None = omitir el
                parámetro (usa el valor por defecto del proveedor).
            max_completion_tokens: Cota superior de tokens de la completion
                (incluye razonamiento). Si se indica, el proveedor la
                prioriza sobre `max_tokens`.
        """
        self.endpoints = list(endpoints or [
            "http://10.0.0.3:8000/v1",
            "http://10.0.0.4:8000/v1",
        ])
        self.model = model
        self.timeout = timeout
        self.simulado = simulado
        self.api_key_env = api_key_env
        self.metricas = metricas
        self.max_tokens_default = int(max_tokens_default)
        self.reasoning_effort = reasoning_effort
        self.max_completion_tokens = max_completion_tokens
        self._idx = 0  # round-robin index
        self._specs = [self._normalizar_endpoint(ep) for ep in self.endpoints]
        self._sem = threading.BoundedSemaphore(max(int(max_concurrencia), 1))
        self._tasa = _LimitadorTasa(tasa_max_por_minuto)

    def _normalizar_endpoint(self, ep: Any) -> Dict[str, Any]:
        """Convierte una especificación de endpoint en un dict normalizado."""
        if isinstance(ep, str):
            return {"url": ep, "model": self.model,
                    "api_key_env": self.api_key_env}
        if isinstance(ep, tuple):
            url, m = ep
            return {"url": url, "model": m,
                    "api_key_env": self.api_key_env}
        if isinstance(ep, dict):
            spec = dict(ep)
            spec.setdefault("model", self.model)
            spec.setdefault("api_key_env", self.api_key_env)
            if not spec.get("url"):
                raise ValueError("Endpoint sin 'url'")
            return spec
        raise TypeError("Endpoint no reconocido: %s" % type(ep).__name__)

    def _siguiente_endpoint(self) -> Any:
        """Selecciona el siguiente endpoint round-robin."""
        ep = self.endpoints[self._idx % len(self.endpoints)]
        self._idx += 1
        return ep

    def _headers_de_endpoint(self, spec: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Cabecera Authorization Bearer desde variable de entorno.

        Si el endpoint no pide clave, devuelve None. Si la pide y la variable
        no existe, lanza un error claro que nombra la variable sin filtrar
        ningún secreto.
        """
        env = spec.get("api_key_env")
        if not env:
            return None
        clave = os.environ.get(env)
        if not clave:
            raise RuntimeError(
                "No se encontró la variable de entorno %r para autenticar "
                "el endpoint %s; defínela antes de usar este backend."
                % (env, spec["url"]))
        return {"Authorization": "Bearer %s" % clave}

    def _registrar_metricas(self, latencia: float, data: Dict[str, Any]) -> None:
        if self.metricas is None:
            return
        uso = data.get("usage") or {}
        self.metricas["peticiones"] = self.metricas.get("peticiones", 0) + 1
        self.metricas["latencia_total"] = (
            self.metricas.get("latencia_total", 0.0) + latencia)
        self.metricas["max_latencia"] = max(
            self.metricas.get("max_latencia", 0.0), latencia)
        self.metricas["prompt_tokens"] = (
            self.metricas.get("prompt_tokens", 0)
            + int(uso.get("prompt_tokens") or 0))
        self.metricas["completion_tokens"] = (
            self.metricas.get("completion_tokens", 0)
            + int(uso.get("completion_tokens") or 0))

    def _chat_real(self, sistema: str, usuario: str, max_tokens: int,
                   temperature: float,
                   max_completion_tokens: Optional[int] = None) -> str:
        """Ejecuta una petición real al endpoint.

        `max_completion_tokens` permite fijar el presupuesto por petición
        (p. ej. una familia de fase 1); si es None se usa el del cliente.
        """
        idx = self._idx % len(self.endpoints)
        endpoint = self._siguiente_endpoint()
        spec = self._specs[idx]
        url = "%s/chat/completions" % spec["url"]
        payload = {
            "model": spec["model"],
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        tope = (max_completion_tokens if max_completion_tokens is not None
                else self.max_completion_tokens)
        if tope:
            payload["max_completion_tokens"] = int(tope)
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        headers = self._headers_de_endpoint(spec)
        kwargs: Dict[str, Any] = {"json": payload, "timeout": self.timeout}
        if headers:
            kwargs["headers"] = headers
        inicio = time.time()
        with self._sem:
            self._tasa.esperar()
            resp = requests.post(url, **kwargs)
        latencia = time.time() - inicio
        if resp.status_code == 429:
            raise RateLimitError(resp.headers.get("Retry-After"))
        resp.raise_for_status()
        data = resp.json()
        self._registrar_metricas(latencia, data)
        contenido = data["choices"][0]["message"].get("content")
        if contenido is None:
            raise ContenidoVacioError()
        return contenido

    def chat(
        self,
        sistema: str,
        usuario: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.2,
        max_reintentos: int = 3,
        max_completion_tokens: Optional[int] = None,
    ) -> str:
        """Envía una petición de chat con reintentos y backoff exponencial.

        Ante HTTP 429 se espera según `Retry-After` si el servidor lo indica;
        en caso contrario se usa el backoff exponencial habitual.

        Args:
            sistema: Prompt de sistema
            usuario: Prompt de usuario
            max_tokens: Tokens máximos de respuesta
            temperature: Temperatura de muestreo
            max_reintentos: Número máximo de reintentos ante fallo
            max_completion_tokens: Cota de tokens de la completion para esta
                petición; None usa la del cliente (compatibilidad total).

        Returns:
            Texto de la respuesta

        Raises:
            Exception: Si se agotan los reintentos
        """
        if max_tokens is None:
            max_tokens = self.max_tokens_default
        if self.simulado:
            return self.simulado(sistema, usuario)

        espera = 1.0
        ultima_exc = None
        for intento in range(max_reintentos + 1):
            try:
                return self._chat_real(
                    sistema, usuario, max_tokens, temperature,
                    max_completion_tokens=max_completion_tokens)
            except RateLimitError as e:
                ultima_exc = e
                if intento < max_reintentos:
                    bo = e.backoff
                    time.sleep(bo if bo is not None else espera)
                    espera *= 2  # backoff exponencial
                else:
                    raise
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

        # Buscar el primer { ... } balanceado que sea JSON válido
        inicio = texto.find("{")
        while inicio != -1:
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
            inicio = texto.find("{", inicio + 1)

        raise ValueError("No se encontró JSON válido en la respuesta")

    def chat_json(
        self,
        sistema: str,
        usuario: str,
        validar: Callable[[Dict[str, Any]], None],
        max_tokens: Optional[int] = None,
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
