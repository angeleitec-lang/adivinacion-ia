# ESTADO — T140 (cierre 2: fusión de fuentes nuevas del 23/10)

Rama: `track/t140-cierre-2` (verificada con `git branch --show-current`).
Worktree: `/Users/angelgonzalez/adivinacion-ia/.worktrees/t140-cierre-2`.
Python: `/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python`.
Git solo local, sin push. Sin Mercury, sin nodo1.

## Progreso de los pasos

1. **Copia de seguridad fechada** — HECHO.
   `fase0/_backup_t140_20261023_1727` (consenso_kb, kb_v2, libros/evidencias,
   afirmaciones_libros, cobertura_v3). Conteos verificados: consenso 4021,
   evidencias 16545, afirmaciones 38857.

2. **Dry-run + fusión de evidencias y afirmaciones** — HECHO.
   - Evidencias: `libros/evidencias/evidencias.jsonl` 16 545 → 17 278 (+733).
   - Afirmaciones deduplicadas → `afirmaciones_libros/afirmaciones_libros.jsonl`
     38 857 → 40 546 (+1 689). Dedup por `(entidad_id, norm(afirmacion))`
     conservando la primera: T132 −48, T134 −24, T133 sin cambios.
   - Staging dedup en `fase0/_t140_staging/`.

3. **Consenso solo celdas afectadas (nodo2, ≤2 workers)** — HECHO.
   - Wrapper `run_consenso_t140.py`: `LLMClient(endpoints=['http://10.0.0.4:8000/v1'],
     max_concurrencia=2)` + `consenso_kb.main(--extra-afirmaciones <3 dedup>
     --rehacer-celdas-con-extra --workers 2)`. **Solo nodo2** (el default del
     cliente haría round-robin con nodo1; se evitó pasando el cliente a mano).
   - Antes de lanzar: verificado que no había escritores en nodo2.
   - STATS: 138 celdas procesadas (80 rehacer + 58 nuevas), 0 fallback, 4 alertas
     menores (3 elemento, 1 tautología), 51 no útiles, 4524 duplicadas por fuente.
   - Consenso final: 4 078 líneas. Copia pre-extra:
     `consenso.jsonl.pre-extra-20261023_173056`.

4. **Reconstruir kb_v2 y cobertura_v3** — HECHO.
   - kb_v2 (`cierre_recopilacion.py --paso 5`): tarot 78, astrología 424,
     numerología 71 (+2), baraja 40.
   - cobertura_v3: el `--paso 6` del cierre tiene un bug (pasa el directorio en
     vez del fichero `evidencias_limpias.jsonl` y no incluye las evidencias
     nuevas). Generada invocando `cobertura_v3.py` directamente:
     ```
     finetune/.venv/bin/python finetune/corpus/cobertura_v3.py \
       --libros limpio \
       --libros-limpio /Users/angelgonzalez/fase0/libros_limpio/evidencias_limpias.jsonl \
       --extra \
         /Users/angelgonzalez/fase0/txt_naipes_tarot/evidencias/evidencias.jsonl \
         /Users/angelgonzalez/fase0/txt_ocultismo_numerologia/evidencias/evidencias.jsonl \
         /Users/angelgonzalez/fase0/libros_comprados_baraja/evidencias/evidencias_baraja.jsonl
     ```
   - Resultado: 314 celdas completas (ver tabla en `docs/CIERRE_2.md`).

5. **Revisión manual de 20 celdas** — HECHO (ver abajo).

## Revisión manual de 20 celdas (nuevas y rehacer)

NUEVAS — Numerología (8):
1. `11|mes_personal|luz_sombra` — coherente (galves). OK
2. `22|mes_personal|luz_sombra` — coherente. OK
3. `22|mes_personal|significado_general` — imaginería del Loco (arcano 22)
   aplicada a numerología; aceptable, con sabor a tarot.
4. `2|destino|simbolismo` — fuente clásica (TarotDeLosBohemios), coherente. OK
5. `2|mes_personal|luz_sombra` — coherente. OK
6. `5|mes_personal|luz_sombra` — coherente. OK
7. `9|mes_personal|luz_sombra` — 1 discrepancia registrada correctamente. OK
8. `9|personalidad|luz_sombra` — coherente. OK

NUEVAS — Astrología (6):
9. `jupiter|oposicion|saturno|aspecto|dinero` — coherente. OK
10. `jupiter|oposicion|saturno|aspecto|luz_sombra` — coherente. OK
11. `jupiter|virgo|planeta_en_signo|correspondencias` — Golden Dawn, esotérico
    coherente. OK
12. `leo|signo|consejo_practico` — **AVISO**: la celda de Leo arrastra consejos
    de Géminis («Para conquistar a una persona Géminis…»). Malaatribución en la
    extracción de la fuente (astrologiaparadummies), no de T140.
13. `leo|signo|dinero` — coherente (Leo). OK
14. `luna|aries|planeta_en_signo|correspondencias` — coherente (los-planetas-huber). OK

REHACER — modificadas (6):
15. `tarot-bastos-03|correspondencias` — decanato, clásica. OK
16. `3|personalidad|significado_general` — **AVISO**: mezcla contenido de otros
    números (cuatro, siete, diez, 22, 19, 8) del libro de Hitchcock.
    Contaminación cruzada de extracción preexistente, no introducida por T140.
17. `tarot-bastos-10|significado_general` — multi-fuente coherente (Jodorowsky,
    brujas modernas, pollack, greer). OK
18. `tarot-copas-07|simbolismo` — coherente. OK
19. `tarot-espadas-12|derecha_invertida` — n=9, disc=12 (esperable en invertida). OK
20. `tarot-mayor-06|simbolismo` — n=259; tautología de `altaya_naipes`
    correctamente alertada. OK

**Veredicto**: 17/20 limpias; 2 avisos de calidad de extracción (preexistentes,
no introducidos por esta fusión); 1 tautología bien detectada. Ninguno bloqueante.

## Procesos

El proceso de consenso (PID 34780) **terminó** correctamente. No queda ningún
proceso vivo de esta pista. Los generadores suspendidos (66101, 66396) **no** se
reanudaron.

## Comando de continuación (si hiciera falta reejecutar)

Reejecutar el consenso de las mismas celdas (idempotente, deja copia pre-extra):
```
/Users/angelgonzalez/adivinacion-ia/finetune/.venv/bin/python \
  /var/folders/wf/n_gzv4090z77rh0jlq19y78r0000gn/T/opencode/run_consenso_t140.py
```
Reconstruir kb_v2 y cobertura_v3: ver paso 4 arriba.

## Commits y hashes

`git log --oneline main..HEAD` (verificado tras el commit de docs):

- `01af8f7` — T140: cierre 2 — fusion de fuentes nuevas (T132/T133/T134) en cobertura v3

(El presente commit de `ESTADO.md` es de registro y sigue a `01af8f7`.)

TRACK COMPLETO
