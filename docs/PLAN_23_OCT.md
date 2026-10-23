# Plan de acción 23/10 (07:50 → 16:00)

Estado de partida: T121 (cierre, cobertura v3 = 299) y T131 (script de paráfrasis) integradas en main; check OK.

| Pista | Pestaña | Qué | Depende |
|---|---|---|---|
| T132 | 2 | `_txt`: Naipes y sus secretos (Altaya), Compendium Tarot Mexicanus, Ricart 1838 → evidencias/afirmaciones | — |
| T133 | 7 | `_txt`: Diccionario de ciencias ocultas (filtrado) y Numerología fácil (PT) | — |
| T134 | 8 | Paráfrasis de las 320 afirmaciones de baraja con nodo2 (sin Mercury: no hay clave) | — |

Descartado de `_txt`: `banzhaf_djvu.txt` (es un 404 de nginx), `baraja_solar_djvu.txt` (baraja oracular moderna, no es sistema del proyecto), `tarot_oceano_daoista_djvu.txt` (texto de 2026 «escrito y traducido por ZJC», sin tradición contrastable).

Nodo2: ≤3 workers en total (T132 ≤2, T133 ≤2, T134 1; las etapas LLM se escalonan).

Tras cada pista: revisión con casos propios, merge, check.sh. A partir de ~13:00, pista de cierre 2 (T135): fusionar T132/T133/T134 en consenso → kb_v2 → cobertura_v3, y regenerar si procede el dataset v1d→v1e.
Pestañas 3, 4, 5, 6 libres a propósito (nodo2 no admite más). DeepSeek (5) solo 10:00–24:00.
