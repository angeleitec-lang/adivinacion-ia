# ESTADO — T143: quitar la restricción «nodo1 reservado» (levantada por el usuario el 23/10)

Rama: `track/t143-nodo1-permitido`. Git solo local.

## Tarea 1 — Puntos de la restricción nodo1 (grep `reservad|10\.0\.0\.3`)

Ficheros propios con rechazo/comentario de nodo1 (a modificar):

- `clasicos_pd_a_evidencias.py`
  - L39-40: comentario + `NODO1_RESERVADO = "10.0.0.3"`
  - L275-293: `construir_cliente_endpoints` rechaza nodo1 (docstring L282, `raise` L288-291)
  - L414-417: argparse `--endpoints` help «Nunca 10.0.0.3 (reservado por el usuario)»
- `libro_comprado_nichols.py`
  - L22: docstring módulo «LLM fijado a nodo2 (nodo1 reservado)»
  - L54-55: `NODO2_ENDPOINT` / `NODO1_RESERVADO`
  - L426-446: `construir_cliente_endpoints` rechaza nodo1 (docstring L430, `raise` L438-442)
  - L712-714: argparse `--endpoints` help «(solo nodo2; nunca 10.0.0.3)»
- `libros_comprados_baraja.py`
  - L71-72: `NODO2_ENDPOINT` / `NODO1_RESERVADO`
  - L784-796: `construir_cliente_endpoints` rechaza nodo1 (docstring L785, `raise` L791-794)
  - L874: argparse `--endpoints` default=`NODO2_ENDPOINT`
- `libros_comprados_en.py`
  - L23: docstring módulo «(10.0.0.3) está reservado por el usuario»
  - L55-56: `NODO1_RESERVADO` / `ENDPOINT_NODO2`
  - L115-130: `construir_cliente_endpoints` rechaza nodo1 (docstring L118, `raise` L124-128)
  - L971-973: argparse `--endpoints` help «Nunca 10.0.0.3 (reservado)»
- `libros_comprados_astro.py`
  - L27: docstring módulo «LLM fijado a nodo2 (nodo1 reservado)»
  - L47-48: `NODO2_ENDPOINT` / `NODO1_RESERVADO`
  - L373-385: `construir_cliente_endpoints` rechaza nodo1 (`raise` L377-381)
  - L643: argparse `--endpoints` default=`NODO2_ENDPOINT`
- `libro_comprado_greene.py` (delegado en astro)
  - L31: docstring módulo «fijado a nodo2 (nodo1 reservado)»
  - L66-67: `NODO2_ENDPOINT = astro.NODO2_ENDPOINT` / `NODO1_RESERVADO = astro.NODO1_RESERVADO`
  - L817-818: argparse `--endpoints` help «(solo nodo2)»
  - L879/890: delega el rechazo en `astro.construir_cliente_endpoints`
- `traducir_afirmaciones.py`
  - L16-17: docstring «nodo1 esta reservado para entrenamiento, no usarlo aqui»
  - L46-47: comentario «Endpoints por defecto: NODO2. El nodo1 esta reservado...»
  - L417-419: default local = `ENDPOINT_LOCAL_POR_DEFECTO` (nodo2)
  - L530-532: argparse `--endpoint` help «(nodo2)»
- `txt_naipes_tarot.py`
  - L24: docstring «LLM solo en nodo2»
  - L52-53: `NODO2_ENDPOINT` / `NODO1_RESERVADO`
  - L650: comentario «Etapas LLM (nodo2, reanudables)»
  - L654-657: `construir_cliente` rechaza nodo1 (`raise` L655-656)
  - L788: argparse `--endpoints` default=`NODO2_ENDPOINT`
- `linea_base.py` (SOLO comentario; `MODELOS` no se toca)
  - L19-21: docstring «El nodo1 está reservado: no se usa»

Tests propios que esperan el rechazo de nodo1 (a actualizar en T3):

- `tests/test_clasicos_pd_a_evidencias.py` L248-267 (`TestConstruirClienteEndpoints`)
- `tests/test_libro_comprado_greene.py` L247-250 (`test_nodo1_reservado`, vía astro)
- `tests/test_libro_comprado_nichols.py` L245-251 (`test_rechaza_nodo1`)
- `tests/test_t115_comprados_en.py` L227-240 (`test_rechaza_nodo1`, `test_endpoints_vacios`)
- `tests/test_traducir_afirmaciones.py` L192-197 (`test_local_default_es_nodo2_y_nunca_nodo1`)
- `tests/test_txt_naipes_tarot.py` L283-285 (`test_rechaza_nodo1`)
- `tests/test_linea_base.py` L108-110 (`test_flash_next_usa_solo_nodo2`): NO es rechazo de
  cliente, es registro `MODELOS`; se MANTIENE (solo se toca el comentario del módulo).

Fueras de alcance (NO tocar): `regenerar_fuera_alcance.py` L269, `regenerar_etica_espanola1.py`,
`translate_dataset.py` L27 (default nodo1, no es restricción), `llm_client.py` (defaults),
y todos los «reservad» de semillas de evaluación / copyright / derechos reservados.

## Diseño acordado (T2)

- Hosts locales permitidos: `10.0.0.3` (nodo1) y `10.0.0.4` (nodo2). Cualquier otro host
  (p. ej. `example.com`) se rechaza. Validación por `urlparse(...).hostname`, no por substring.
- `LLMClient` ya soporta round-robin sobre `endpoints=[...]` (`_next_endpoint` cíclico), así que
  por defecto se reparte entre ambos nodos.
- CSV vacío/None → por defecto ambos nodos (round-robin). CSV explícito → se valida host a host.
- Se mantienen los nombres de constante (`NODO1_RESERVADO`, `NODO2_ENDPOINT`, `ENDPOINT_NODO2`)
  por compatibilidad de imports (`greene` importa de `astro`; `txt_ocultismo_numerologia` importa
  `baraja.NODO2_ENDPOINT`); solo cambian su comentario y la lógica de validación.

## Tarea 2 — Lógica de clientes (commit `89fd7d1`)

Patrón aplicado en cada `construir_cliente_endpoints` (o equivalente): parse CSV → si vacío,
`endpoints = split(ENDPOINTS_POR_DEFECTO)` (ambos nodos); por cada URL,
`if urlparse(url).hostname not in HOSTS_LOCALES_PERMITIDOS: raise ValueError("endpoint no permitido (solo nodo1 y nodo2): %r")`;
luego `LLMClient(endpoints=endpoints, ...)` (round-robin cíclico). Nuevas constantes por fichero:
`HOSTS_LOCALES_PERMITIDOS = ("10.0.0.3", "10.0.0.4")` y
`ENDPOINTS_POR_DEFECTO = "http://10.0.0.3:8000/v1,http://10.0.0.4:8000/v1"`.

- `clasicos_pd_a_evidencias.py`: lógica nueva + `import urlparse`; argparse `--endpoints` default `""` → ambos.
- `libro_comprado_nichols.py`: lógica nueva (rama `acotar`); argparse default `NODO2_ENDPOINT` → `ENDPOINTS_POR_DEFECTO`.
- `libros_comprados_baraja.py`: lógica nueva (imports internos en la función); argparse default → `ENDPOINTS_POR_DEFECTO`.
- `libros_comprados_en.py`: lógica nueva (siempre `_ClienteAcotado`); argparse default → `ENDPOINTS_POR_DEFECTO`.
- `libros_comprados_astro.py`: lógica nueva (rama `acotar`); argparse default → `ENDPOINTS_POR_DEFECTO`.
- `libro_comprado_greene.py`: sin lógica propia (delega en `astro`); argparse default → `astro.ENDPOINTS_POR_DEFECTO`.
- `txt_naipes_tarot.py`: `construir_cliente` deja de rechazar nodo1 y delega en `libros_comprados_en.construir_cliente_endpoints`; argparse default → `libros_comprados_en.ENDPOINTS_POR_DEFECTO`.
- `traducir_afirmaciones.py`: nueva constante `ENDPOINTS_LOCALES_POR_DEFECTO = ("http://10.0.0.3:8000/v1", "http://10.0.0.4:8000/v1")`; fallback local en `crear_cliente` = ambos nodos. No se añadió rechazo duro (nunca lo tuvo y soporta specs `url=modelo`).

Smoke test sin red: 7/7 OK (aceptan nodo1/nodo2/ambos; vacío → ambos; rechazan `http://example.com/v1`).

## Tarea 3 — Tests (commit `6af138c`)

Cada test de endpoints ahora: acepta nodo1 solo, acepta nodo2 solo, acepta ambos (round-robin,
`endpoints == [nodo1, nodo2]`), vacío → `set == {nodo1, nodo2}`, rechaza `http://example.com/v1`.

- `test_clasicos_pd_a_evidencias.py`: clase `TestConstruirClienteEndpoints` reescrita.
- `test_libro_comprado_nichols.py`: `test_acepta_nodo1` / `test_acepta_nodo2` / `test_vacio_reparte_ambos` / `test_rechaza_host_ajeno`.
- `test_libro_comprado_greene.py`: `test_acepta_nodo1_y_nodo2` + `test_rechaza_host_ajeno` (vía `astro`).
- `test_t115_comprados_en.py`: acepta nodo1/nodo2/ambos/vacío + rechaza host ajeno (vía `lce`).
- `test_traducir_afirmaciones.py`: renombrado a `test_local_default_son_ambos_nodos` (`assertIn` 10.0.0.4 Y 10.0.0.3).
- `test_txt_naipes_tarot.py`: `test_acepta_nodo1` + `test_rechaza_host_ajeno`.
- AÑADIDAS clases `TestConstruirClienteEndpoints` (5 tests) en `test_libros_comprados_baraja.py` y `test_libros_comprados_astro.py` (antes no tenían test de rechazo).
- `test_linea_base.py` `test_flash_next_usa_solo_nodo2`: se MANTIENE (registro `MODELOS`, no rechazo de cliente).

## Tarea 4 — Docstrings / comentarios / help (commit `6196bfb`)

En los 9 ficheros se cambió «nodo1 reservado / reservado por el usuario / solo nodo2 / nunca
10.0.0.3 / fijado a nodo2 / no usarlo aquí» por «nodo1 y nodo2 permitidos (autorizado por el
usuario el 23/10)» o equivalente. `linea_base.py`: solo el docstring («ya no está reservado;
este modelo sigue apuntando a nodo2»), `MODELOS` intacto. Verificado por grep: no queda ninguna
frase de restricción antigua en los 9 ficheros objetivo.

## Verificación

- Suite de los 9 ficheros: `Ran 241 tests ... OK`.
- `./finetune/scripts/check.sh` → `Ran 2913 tests ... OK (skipped=1)` + scraper `Ran 23 tests ... OK` → **CHECK OK**.
- Los avisos LSP/pyright (unión `LLMClient|_ClienteAcotado` al leer `._cliente`, y `None`-subscriptable
  preexistentes en baraja L281/320/345/559) NO los ejecuta `check.sh` (solo `compileall` + `unittest`); runtime correcto.

## Commits (git log main..HEAD)

- `dc30f69` T143-1: listado de puntos de la restricción nodo1 (grep) en ESTADO.md
- `89fd7d1` T143-2: permitir nodo1 y nodo2 en los clientes LLM (round-robin por defecto)
- `6af138c` T143-3: tests de endpoints aceptan nodo1/nodo2 y rechazan host ajeno
- `6196bfb` T143-4: docstrings/comentarios/help reflejan nodo1 y nodo2 permitidos (autorizado 23/10)

TRACK COMPLETO
