# ESTADO — T134 Paráfrasis de las 320 afirmaciones de baraja con backend local (nodo2)

Rama: `track/t134-parafrasis-baraja-local`. Worktree:
`/Users/angelgonzalez/adivinacion-ia/.worktrees/t134-parafrasis-baraja-local`.

## Resultado

**320/320 afirmaciones aceptadas (100 %)** — objetivo ≥300/320 cumplido.

- Pasada `--limite 10` (revisión manual): 10 aceptadas.
- Pasada completa `--resume` contra nodo2: 309 nuevas aceptadas, **1 rechazada**
  (motivo: `copia literal de la cita (>8 palabras consecutivas)`, naipe-copas-07,
  luz_sombra, revés), 10 omitidas (ya aceptadas).
- Reintento del rechazado con `--temperatura 0.7`: **aceptada**.
- Estado final: `salida=320`, `procesados=320`, `rechazadas=0`.

Verificación independiente sobre las 320 filas finales (punto final, 1-2
oraciones, anti-copia >8 palabras frente a `cita_original`, orientación
derecho/revés conservada, español estándar sin otra lengua ni «asistente de
IA»): **0 problemas**.

Distribución: 40 entidades (naipes), 160 al derecho / 160 al revés; fuentes:
`libro_salas_baraja` (160) y `libro_tiradas_baraja_espanola` (160).

Procedencia registrada en cada fila: `comprado por el usuario, uso interno, libro con copyright`.

## Comandos usados

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
BASE=/Users/angelgonzalez/fase0/libros_comprados_baraja/afirmaciones
cd /Users/angelgonzalez/adivinacion-ia/finetune/corpus

# sintaxis
$PY parafrasear_baraja.py --help
$PY parafrasear_baraja.py --entrada $BASE/afirmaciones_baraja.jsonl \
  --backend local --endpoint "http://10.0.0.4:8000/v1=halogen-qwen3.8-flash-next" \
  --workers 1 --limite 5 --dry-run

# revisión manual (10)
$PY parafrasear_baraja.py --entrada $BASE/afirmaciones_baraja.jsonl \
  --salida $BASE/afirmaciones_baraja_parafraseadas.jsonl --backend local \
  --endpoint "http://10.0.0.4:8000/v1=halogen-qwen3.8-flash-next" \
  --workers 1 --limite 10

# pasada completa reanudable (1 worker, nodo2)
nohup $PY -u parafrasear_baraja.py --entrada $BASE/afirmaciones_baraja.jsonl \
  --salida $BASE/afirmaciones_baraja_parafraseadas.jsonl --backend local \
  --endpoint "http://10.0.0.4:8000/v1=halogen-qwen3.8-flash-next" \
  --workers 1 --resume > /tmp/t134_parafrasis.log 2>&1 &

# reintento del único rechazado con temperatura mayor
$PY parafrasear_baraja.py --entrada /tmp/t134_reintento.jsonl \
  --salida /tmp/t134_reintento_out.jsonl --backend local \
  --endpoint "http://10.0.0.4:8000/v1=halogen-qwen3.8-flash-next" \
  --workers 1 --temperatura 0.7
```

## 10 ejemplos antes/después

| Carta | Orientación | Antes (cita recortada) | Después (paráfrasis) |
|---|---|---|---|
| As de Oros | derecho | Felicidad. Prosperidad. Triunfo. Grandes alegrías. Satisfacción. Riqueza. Es la carta más favorable… | El As de Oros al derecho representa la máxima fortuna en la baraja española. Anuncia prosperidad, éxito y una profunda satisfacción material. |
| As de Oros | derecho | Felicidad. Prosperidad. Triunfo… Es la carta más favorable… | El As de Oros al derecho anuncia felicidad, prosperidad y triunfo, junto con grandes alegrías, satisfacción y riqueza. Representa la carta más favorable de la baraja. |
| As de Oros | revés | Fortuna. Riquezas. Dinero. Objetos valiosos… mucho menos que si sale al derecho | Al revés, el As de Oros sigue siendo una carta favorable, aunque su influencia en la fortuna, la riqueza, el dinero y los objetos valiosos es mucho menor que cuando aparece al derecho. |
| As de Oros | revés | Fortuna. Riquezas. Dinero… | Al revés, esta carta indica fortuna, riqueza, dinero y objetos valiosos, aunque su influencia positiva es mucho menor que cuando aparece al derecho. |
| Dos de Oros | derecho | Obstáculos. Turbación. Agitación… | El Dos de Oros al derecho señala obstáculos, turbación y agitación. Representa emociones que paralizan a quien las experimenta. |
| Tres de Oros | derecho | Nobleza. Dignidad. Renombre. Poder. Magnanimidad… | El Tres de Oros al derecho representa la nobleza, la dignidad, el renombre, el poder y la magnanimidad. Es la carta que expresa la nobleza tanto de linaje como de espíritu. |
| Siete de Copas | revés | Proyectos. Planes. Intenciones. Deseos… Cuando el siete sale al revés… | Al salir invertido, este naipe señala proyectos, planes e intenciones, así como deseos, voluntad, resolución y determinación. También representa una idea, un bosquejo, la premeditación y el ingenio. |
| Rey de Espadas | derecho | hombre maduro, moreno de pelo oscuro… posición social, poder… | El Rey de Espadas al derecho representa a un hombre maduro, de cabello oscuro, negro o canoso, con posición social, poder e inteligencia… |
| Rey de Espadas | revés | Al revés | El Rey de Espadas al revés indica una energía bloqueada o invertida en su significado habitual. |
| Rey de Espadas | revés | Al revés | El Rey de Espadas al revés se interpreta como una energía bloqueada o mal canalizada, asociada a la frialdad, la dureza o el uso negativo de la inteligencia y la autoridad. |

(Tabla resumida para lectura; los 320 pares completos quedan en los JSONL de `fase0`.)

## AJUSTE (2026-10-23): defecto grave detectado por el usuario

**Defecto**: 80 de las 320 paráfrasis (todas las de orientación revés de los
naipes 1-10 de los cuatro palos) tenían `cita_original` = «Al revés» (8
caracteres): el libro, tal como lo extrajo T129, NO aportaba contenido y el
modelo INVENTÓ el significado. Las rechazadas.jsonl estaban vacías y el
verificador no lo detectaba.

**Causa raíz (investigada)**: el significado al revés SÍ existe en el libro
«Tiradas de cartas españolas» (`TiradasDeCartasEspanolas.pdf`). El bug estaba
en `libros_comprados_baraja.py`: `_REVES_RE` tenía un GRUPO CAPTURADOR, así
que `_REVES_RE.split(crudo, maxsplit=1)` insertaba el delimitador capturado
«Al revés» como `partes[1]`, perdiendo el contenido real. Ejemplos reales:
- As de Oros: «Al revés, significa problemas de dinero o problemas en el
  trabajo. No es momento de cambiar de trabajo ni de hacer inversiones.»
- Sota de Bastos: «persona débil, depresiva, emocionalmente enferma»
- Siete de Bastos (reves): «obstáculos laborales, bloqueo de los asuntos
  laborales por culpa de un señor mayor…»

**Corrección 1 (parseo)**: `_REVES_RE` cambiado a grupo NO capturador. Test
nuevo `test_reves_captura_texto_completo` (regresión). 19/19 tests OK.
Regeneración determinista en fichero NUEVO `afirmaciones_baraja_v2.jsonl`
(320 filas; antes 80 con «Al revés», tras el fix 0 con cita <40 caracteres) y
`afirmaciones_reves_afectadas.jsonl` (las 80 filas afectadas).

**Corrección 2 (verificador)**: `parafrasear_baraja.py` ampliado con reglas
deterministas: rechazar si la cita tiene <40 caracteres (`CITA_MIN_CARACTERES`)
o si la paráfrasis solo contiene fórmulas genéricas (`es_formula_generica`,
conjunto `_FÓRMULA_GENÉRICA`). Tests adversos nuevos (casos reales). 26/26 tests OK.

**Re-paráfrasis de las 80 filas afectadas** (con la cita real, nodo2, 1 worker):
`parafrasear_baraja.py --entrada afirmaciones_reves_afectadas.jsonl
--salida afirmaciones_reves_parafraseadas.jsonl --backend local
--endpoint "http://10.0.0.4:8000/v1=halogen-qwen3.8-flash-next"
--workers 1 --resume` → **80/80 aceptadas, 0 rechazadas**.

**`afirmaciones_baraja_validas.jsonl`** (dataset final válido): 240 filas
originales no afectadas + 80 re-paráfrasis = **320 filas**. Verificación con el
verificador ampliado: 320/320 OK, 0 rechazos. Recuentos: 160 derecho / 160
revés; libros_salas_baraja 160 / libro_tiradas_baraja_espanola 160; facetas:
derecha_invertida 160, significado_general 80, luz_sombra 80. 0 filas sin fid/
procedencia; 0 citas <40 caracteres. **Revisión manual**: 20 derecho + 10
revés, todas con contenido propio, orientación conservada y español estándar.

## Commits (hashes reales, `git log main..HEAD`)

- `da3371d` T134: ESTADO paráfrasis baraja 320/320 (nodo2) + TRACK COMPLETO
- `697c0c6` T134: anotar hash real del commit de ESTADO
- `038a333` T134: listar ambos hashes reales de la rama en ESTADO
- (este commit) T134 AJUSTE: fix `_REVES_RE` (grupo no capturador), verificador
  con reglas cita <40 / fórmula genérica, tests, y generación de
  `afirmaciones_baraja_validas.jsonl` (320 válidas) + re-paráfrasis 80 revés.

## Estado

`TRACK COMPLETO`
