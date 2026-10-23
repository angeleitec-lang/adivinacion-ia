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

## Ajustes

No fue necesario tocar `parafrasear_baraja.py` ni sus tests: el modelo
`halogen-qwen3.8-flash-next` en nodo2 devolvió paráfrasis válidas (sin
razonamiento pegado ni texto fuera de la frase) desde el primer lote. No hay
commits de código en esta rama; el script ya venía de T131.

## Commits (hashes reales, `git log main..HEAD`)

- `da3371d` T134: ESTADO paráfrasis baraja 320/320 (nodo2) + TRACK COMPLETO

## Estado

`TRACK COMPLETO`
