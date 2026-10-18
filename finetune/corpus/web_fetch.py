"""Cliente HTTP educado para el rastreo dirigido de páginas por entidad (track A3).

Reglas de cortesía: máximo 1 petición cada `min_interval` por dominio, robots.txt
con caché por dominio, reintentos con espera exponencial ante 429 (y pausa del
dominio tras agotarlos) y detección de antibot (Cloudflare) sin insistir.
Manifiesto `manifest.jsonl` reanudable: las URLs ya descargadas `ok` no se repiten.
"""
import json
import os
import time
from urllib import robotparser
from urllib.parse import urlparse

import requests

USER_AGENT = "adivinacion-ia-corpus/1.0 (investigacion local)"
ANTIBOT_MARCAS = ("checking your browser", "just a moment", "captcha")


class Cliente:
    """Descarga URLs con cortesía por dominio, robots.txt y reanudación por manifiesto."""

    def __init__(self, user_agent=USER_AGENT, min_interval=1.2,
                 backoff=(10.0, 30.0, 90.0), manifest_path=None, session=None,
                 timeout=30):
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.backoff = tuple(backoff)
        self.manifest_path = manifest_path
        self.session = session or requests.Session()
        self.timeout = timeout
        self._ultimo = {}      # dominio -> monotonic del último request
        self._robots = {}      # dominio -> RobotFileParser o None (permitir todo)
        self._pausados = set()  # dominios en pausa por 429
        self._ok = {}          # url -> registro del manifiesto
        if manifest_path and os.path.exists(manifest_path):
            with open(manifest_path, encoding="utf-8") as f:
                for linea in f:
                    linea = linea.strip()
                    if not linea:
                        continue
                    try:
                        reg = json.loads(linea)
                    except json.JSONDecodeError:
                        continue
                    if reg.get("estado") == "ok":
                        self._ok[reg.get("url")] = reg

    def _esperar_cortesia(self, dominio):
        ultimo = self._ultimo.get(dominio)
        if ultimo is not None:
            restante = self.min_interval - (time.monotonic() - ultimo)
            if restante > 0:
                time.sleep(restante)

    def _obtener_robots(self, dominio, esquema):
        if dominio in self._robots:
            return self._robots[dominio]
        rp = robotparser.RobotFileParser()
        try:
            resp = self._request(f"{esquema}://{dominio}/robots.txt")
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp = None  # sin robots.txt: permitir todo
        except requests.RequestException:
            rp = None
        self._robots[dominio] = rp
        return rp

    def _request(self, url):
        dominio = urlparse(url).netloc
        self._esperar_cortesia(dominio)
        resp = self.session.get(url, headers={"User-Agent": self.user_agent},
                               timeout=self.timeout)
        self._ultimo[dominio] = time.monotonic()
        return resp

    @staticmethod
    def _es_antibot(resp):
        if any(k.lower().startswith("cf-") for k in resp.headers):
            return True
        cuerpo = (resp.text or "").lower()
        return any(marca in cuerpo for marca in ANTIBOT_MARCAS)

    def _registrar(self, url, estado, status, bytes_):
        if not self.manifest_path:
            return
        reg = {"url": url, "estado": estado, "status": status,
               "bytes": bytes_, "fecha": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with open(self.manifest_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")

    def get(self, url):
        """Descarga `url` y devuelve {estado, status, html, bytes, intentos}."""
        parsed = urlparse(url)
        dominio, esquema = parsed.netloc, parsed.scheme or "https"
        if url in self._ok:
            reg = self._ok[url]
            return {"estado": "ya_descargada", "status": reg.get("status"),
                    "html": None, "bytes": reg.get("bytes", 0), "intentos": 0}
        if dominio in self._pausados:
            return {"estado": "pausado_429", "status": None, "html": None,
                    "bytes": 0, "intentos": 0}
        rp = self._obtener_robots(dominio, esquema)
        if rp is not None and not rp.can_fetch(self.user_agent, url):
            self._registrar(url, "bloqueada_robots", None, 0)
            return {"estado": "bloqueada_robots", "status": None, "html": None,
                    "bytes": 0, "intentos": 0}
        intentos = 0
        for k in range(len(self.backoff) + 1):
            intentos += 1
            try:
                resp = self._request(url)
            except requests.RequestException:
                self._registrar(url, "error", None, 0)
                return {"estado": "error", "status": None, "html": None,
                        "bytes": 0, "intentos": intentos}
            if resp.status_code == 429:
                if k < len(self.backoff):
                    time.sleep(self.backoff[k])
                    continue
                self._pausados.add(dominio)
                self._registrar(url, "pausado_429", 429, 0)
                return {"estado": "pausado_429", "status": 429, "html": None,
                        "bytes": 0, "intentos": intentos}
            if resp.status_code in (403, 503) and self._es_antibot(resp):
                self._registrar(url, "bloqueado_antibot", resp.status_code, 0)
                return {"estado": "bloqueado_antibot", "status": resp.status_code,
                        "html": None, "bytes": 0, "intentos": intentos}
            if resp.status_code == 200:
                contenido = resp.content
                if not resp.encoding:
                    resp.encoding = resp.apparent_encoding
                html = resp.text
                self._registrar(url, "ok", 200, len(contenido))
                return {"estado": "ok", "status": 200, "html": html,
                        "bytes": len(contenido), "intentos": intentos}
            self._registrar(url, "error", resp.status_code, 0)
            return {"estado": "error", "status": resp.status_code, "html": None,
                    "bytes": 0, "intentos": intentos}
        self._pausados.add(dominio)
        return {"estado": "pausado_429", "status": None, "html": None,
                "bytes": 0, "intentos": intentos}
