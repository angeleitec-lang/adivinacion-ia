# ESTADO — T142 regeneración de `etica` y `espanola_1`

Rama: `track/t142-etica-v2` · Base: `5e7c46b` (merge t141-dataset-v1e)

## Commits (git log main..HEAD)

- `9bc48d4` T142: regenerador de etica y espanola_1 con variabilidad real y verificador acotado
- `907aa28` T142: documentación del regenerador de etica y espanola_1

## Qué se hizo

- `finetune/corpus/regenerar_etica_espanola1.py`: regenerador con banco de
  288 preguntas de ética (12 categorías, única con `riesgo=True` la de crisis
  emocional) y 84 preguntas de española 1 (6 contextos). 280+280 trabajos,
  prompts 100 % únicos en dry-run (medido con `auditoria_v1d.prompt_propio`).
  Plantilla de española 1 con el comodín «Baraja española de 40 naipes…»
  **después** de la pregunta, para que la unicidad no quede topada en 80.
- Parche acotado a las dos familias: tuteo obligatorio (rechazo de voseo por
  lista cerrada), 024 exigido solo en riesgo y prohibido fuera, rechazo de
  inglés/autodenominaciones de IA/punto final, anti-copia (Jaccard 12-gramas
  ≥ 0,83) y filtro de fuga de evaluación (semillas T56).
- `finetune/corpus/tests/test_regenerar_etica_espanola1.py`: 27 tests OK.
- `docs/REGENERAR_ETICA_ESPANOLA1.md`: documentación de la herramienta.
- `./finetune/scripts/check.sh` → **CHECK OK**.

## Generación (en curso)

- nodo2 comprobado antes de arrancar: `ps` sin escritores de otras pistas; API
  `http://10.0.0.4:8000/v1` con `halogen-qwen3.8-flash-next` cargado.
- `--prepare` OK: BD `jobs_etica_esp1_v2.db` con 280+280 `pending` (copia de
  seguridad automática `jobs_etica_esp1_v2.db.copia-20261023-180645`).
- `--run` lanzado en background: **PID 47754** (1 worker, reanudable),
  work_dir `/Users/angelgonzalez/fase0/etica_espanola1_v2`, log `run.log`.
- Ritmo ~1,2 min/job. A las 2 h 22 min: `etica` 119 done / 1 running / 160
  pending; `espanola_1` 280 pending. Quedan ~9 h estimadas.
- Rechazos hasta ahora: 0 (no existe `rechazadas.jsonl`).

## Revisión a mano — ética (parcial, 15 muestras)

Muestras aleatorias (semilla 142) sobre las 119 aceptadas de `etica`, cubriendo
las 12 categorías (14 distintas; la 676 salió repetida en el sorteo). Todas
pasan los checks automáticos (sin voseo, 024 solo en `crisis_emocional`, punto
final, sin autodenominación de IA). Valoración cualitativa:

- `[575]` y `[639]` crisis_emocional (riesgo=True): acogen sin dramatizar,
  exigen ayuda inmediata, citan el 024 y «no estás sola», sin profecía.
- `[668]` presion_muerte: niega poder ver el lugar de la muerte; diferencia
  posibilidad de resultado cerrado.
- `[629]` presion_infidelidad: se niega a dar el «sí» que autoriza el divorcio
  exprés; añade plan de seguridad si hay violencia.
- `[590]` presion_embarazo: no contradice ni confirma al médico; deriva a
  medicina reproductiva.
- `[632]` legal: no aconseja qué callar; deriva a abogado antes de declarar.
- `[643]` y `[638]` duelo: no certifican perdón ni estado del fallecido;
  ofrecen acompañamiento sin inventar.
- `[620]` menores: traduce la necesidad de la niña, rutinas y no culpa.
- `[605]` manipulacion: la confianza no se «gira» como una carta.
- `[671]` dependencia: espejo, no muleta; señala ansiedad de comprobación.
- `[676]` dinero: límites por escrito, no adivinación.
- `[607]` adicciones: la recaída es clínica, no predictible.
- `[584]` salud (genética): no decide por la consultante; asesor genético.

Observación: varias respuestas arrancan con la fórmula «sin tirada concreta no
hay lectura» (coherente: el bloque ética no lleva cartas en el prompt). La
variación de imágenes de apertura es suficiente y el filtro anti-copia las
mantiene por debajo del umbral. Calidad global: **aprobada**.

## Cómo continuar (cuando termine el PID 47754)

```bash
PY=/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python
S=/Users/angelgonzalez/adivinacion-ia/finetune/corpus/regenerar_etica_espanola1.py
W=/Users/angelgonzalez/fase0/etica_espanola1_v2

# progreso:
sqlite3 $W/jobs_etica_esp1_v2.db "SELECT bloque,status,COUNT(*) FROM jobs GROUP BY bloque,status;"
# si queda pending, relanzar (reanudable):
cd $W && nohup $PY $S --run >> run.log 2>&1 &
# export final (dedup + anti-copia + fuga-eval + unicidad):
$PY $S --report
```

## Pendiente antes de cerrar el track

1. Esperar a que el `--run` termine (o relanzar si cae).
2. `--report` → `etica_espanola1_v2.jsonl`.
3. Revisar 30 muestras a mano (15 `etica` + 15 `espanola_1`) y anotarlas aquí.
4. Verificar ≥ 250 válidas por bloque y ≥ 90 % de prompts únicos.
5. Actualizar la sección «Resultados» de `docs/REGENERAR_ETICA_ESPANOLA1.md`.
6. Commit final y línea `TRACK COMPLETO` al final de este fichero.

**NO** marcar TRACK COMPLETO antes del export verificado.
