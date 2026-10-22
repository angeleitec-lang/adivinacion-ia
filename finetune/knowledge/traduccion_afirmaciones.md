# Traducción de afirmaciones EN→ES (T116)

Herramienta para pasar al español las afirmaciones en inglés procedentes de
libros (Pollack, Greer) antes de que entren al dataset de fine-tune.
Código: `finetune/corpus/traducir_afirmaciones.py` (tests en
`corpus/tests/test_traducir_afirmaciones.py`). No modifica
`translate_dataset.py`: reutiliza su detección de idioma y limpieza.

## Piezas

- **Glosario fijo** `finetune/corpus/glosario_tarot_en_es.json`: palos
  (wands→Bastos, cups→Copas, swords→Espadas, pentacles/coins/disks→Oros),
  22 arcana mayores con los nombres de la KB (strength→La Fuerza,
  judgement→El Juicio…), rangos de corte (page→Sota, knight→Caballero…),
  términos (reversed→invertida, upright→derecha, spread→tirada,
  querent→consultante…) y básico de astrología/numerología. Todos los
  nombres españoles están verificados contra `kb/tarot.json`,
  `kb/astrologia.json` y `cartas.py` (un test lo comprueba: ningún nombre
  inventado).
- **Traductor**: lee JSONL de afirmaciones y escribe JSONL conservando
  `entidad_id`, `faceta` y procedencia, con campos nuevos `fid` (hash
  estable para reanudar), `idioma_origen` y `traductor`. Inyecta el glosario
  completo en el prompt. Backends: `--backend local` (OpenAI-compatible,
  por defecto nodo2 `http://10.0.0.4:8000/v1`; **nodo1 queda reservado**) y
  `--backend mercury` (Inception, clave SOLO por variable de entorno
  `INCEPTION_API_KEY`, nunca se lee ni se imprime su valor). Admite
  `--endpoints` múltiples, `--workers`, `--limite`, `--dry-run` y `--resume`.
  Las filas ya en español pasan sin tocarlas.
- **Verificador determinista** (sin modelo): rechaza nombres de carta en
  inglés residuales o no traducidos según el glosario, cifras y números en
  palabras perdidos (con «2 of Cups» exenta porque la cifra es del nombre de
  carta, y «one's» tratado como pronombre, no como número), inversión/derecha
  conservadas, restos de inglés (stopwords y tecnicismos), longitud fuera de
  0,6–1,6× y marcadores de gallego/portugués. Fallo → reintento con el
  motivo en el prompt (hasta 3); si persiste, va a
  `<salida>.rechazadas.jsonl` con `motivo` e `intentos`.

## Prueba de humo (2026-10-22)

Salida en `/tmp/t116_smoke/` (no version: datos pesados fuera del repo).

- Entrada: 20 afirmaciones EN reales de
  `~/fase0/afirmaciones_libros/afirmaciones_libros.jsonl` (30 283 filas; el
  detector marcó 21 como EN — el resto del fichero ya está en español; las
  20 seleccionadas son de El Colgado, La Luna, El Mundo y El Ermitaño,
  bloque Pollack).
- Backend: `local`, nodo2 `halogen-qwen3.8-flash-next`, 1 worker.
- Resultado primera pasada: **18/20 aprobadas (90 %)** en 1 min 49 s
  (≈0,2 filas/s con reintentos incluidos). Los 2 rechazos fueron un falso
  positivo del verificador («one's own storehouse» exigía traducir *one* por
  *uno*); corregido en `e2d7a44`, la segunda pasada con `--resume` aceptó
  las 2 restantes → **20/20 finales**. El `--resume` funcionó como se espera
  (18 omitidas, 2 procesadas).
- Ejemplos aprobados:
  - EN «Consciously and joyously surrender to Fate, confident that every
    temporary hardship c…」 → ES «Ríndete conscientemente y con alegría al
    destino, confiando en que la dificultad temp…」
  - EN «The natives of Mars are usually capable of making their own way in
    the world」 → ES «Los nativos de Marte suelen ser capaces de abrirse
    camino en el mundo por sí mismos.»
  - EN 「…not from someone else, but from out ou…r own storehouse」 → ES
    「El dinero debe visualizarse como algo que proviene de la propia
    reserva, no de la de otr…」

## Cómo lanzar la pasada masiva (cuando exista el dataset)

Con T115 terminado, sobre sus afirmaciones EN (y revisando antes la lista
de fuentes con partes en inglés, p. ej. `afirmaciones_full`):

```
finetune/.venv/bin/python finetune/corpus/traducir_afirmaciones.py \
  --entrada <afirmaciones_en.jsonl> --salida <afirmaciones_es.jsonl> \
  --backend local --workers 1        # nodo2; aumentar workers con cuidado
```

Reanudable: relanzar con `--resume` continúa por donde quedó. Revisar
siempre `<salida>.rechazadas.jsonl` antes de fusionar.

## Límites conocidos

- Muestra pequeña (20 filas, 4 entidades): la tasa real sobre miles de
  filas puede bajar; los reintentos con feedback deberían absorber la
  mayoría de desviaciones del glosario.
- El ratio de longitud 0,6–1,6 puede rechazar traduccías muy parafraseadas;
  es a propósito (se quiere fidelidad, no resumen).
- «one must…» sí exige forma de *uno/un/una* en la traducción: correcto
  pero estricto.
