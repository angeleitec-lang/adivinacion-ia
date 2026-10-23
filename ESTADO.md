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
