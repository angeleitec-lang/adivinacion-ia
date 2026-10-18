# Inventario curado de fuentes (A1, primera pasada)

Fecha: 2026-10-18 · Alcance: tarot, baraja española, astrología occidental y numerología (ver `PLAN_ADQUISICION_CALIDAD.md`). Datos máquina en `finetune/knowledge/fuentes_libros.jsonl` y `fuentes_sitios.jsonl`. Metodología: libros consultados en archive.org por título y autor y **verificados** (existe texto OCR plano `_djvu.txt` de ≥ 100 KB); sitios descubiertos con Exa y evaluados con una descarga real de muestra (extracción con trafilatura, idioma, densidad de términos del dominio, ruido comercial).

## Resultado en cifras

| Medida | Dato |
|---|---|
| Libros candidatos consultados | 35 |
| **Libros con texto completo verificado** | **21** (≈ 12.5 MB de texto) |
| Libros valiosos solo en préstamo digital o sin texto libre | 14 |
| Sitios evaluados | 143 (prioridad alta: 23, media: 76, baja: 36, descartados: 8) |

## Hallazgos que condicionan el plan

1. **El español está muy poco cubierto con libros libres.** Solo hay texto completo de *La vía del tarot* (Jodorowsky) y de un libro de numerología. Los libros de baraja española (Salas, Rossi y otro) existen en archive.org pero **solo en préstamo digital**, sin texto descargable. El español tendrá que venir de **sitios web, traducción de los clásicos ingleses y libros que el usuario aporte**.
2. **Astrología occidental clásica está bien cubierta** (Alan Leo ×5, Raphael, Carter, Adams, Heindel, Ptolomeo, Lilly): unos 8 MB de texto limpio.
3. **Tarot:** hay base sólida (Waite, Papus, Wirth, Case) y en `docs_epub` ya descargados Pollack (*78 Degrees of Wisdom*), Nichols, Wang y Cicero, pendientes de verificar que traen texto y no solo imagen.
4. **Las obras modernas más valiosas** (Hand, Sasportas, Forrest, Greer, Jordan, Campbell, Cheiro) están **solo en préstamo digital**.
5. **Ejemplos de lecturas resueltas:** los sitios con valor son Biddy Tarot, Labyrinthos, The Tarot Lady (serie de la Cruz Celta con una lectura de ejemplo), Bene Bell Wen (tiradas) y los libros de Leo y Foli.
6. **astro.com bloquea el rastreo** (devuelve páginas vacías); `nymero.org` bloquea bots. Se descartan.

## Libros con texto completo verificado

| Familia | Obra | Autor | Año | Idioma | Texto | Identificador |
|---|---|---|---|---|---|---|
| astrologia | A Concise Encyclopaedia of Psychological Astrology | Charles E. O. Carter | 1924 | en | 334 KB | `in.ernet.dli.2015.128345` |
| astrologia | A Manual of Astrology | Raphael | 1828 | en | 578 KB | `manualofastrolog00raph` |
| astrologia | Astrology for All | Alan Leo | 1899 | en | 485 KB | `astrologyforall00leogoog` |
| astrologia | Astrology: Your Place in the Sun | Evangeline Adams | 1927 | en | 625 KB | `astrologyyourpl00adam` |
| astrologia | Christian Astrology | William Lilly | 1647 | en | 1 MB | `b30338724` |
| astrologia | How to Judge a Nativity | Alan Leo | 1928 | en | 826 KB | `howtojudgenativi00leoa` |
| astrologia | Tetrabiblos | Ptolomeo |  | en | 516 KB | `ptolemystetrabib00ptol` |
| astrologia | The Art of Synthesis | Alan Leo | 1926 | en | 757 KB | `artofsynthesis00leoa` |
| astrologia | The Key to Your Own Nativity | Alan Leo | 1920 | en | 682 KB | `dli.ernet.128062` |
| astrologia | The Message of the Stars | Max Heindel | 1918 | en | 1 MB | `messageofstarses00heiniala` |
| astrologia | The Progressed Horoscope | Alan Leo | 1936 | en | 637 KB | `in.ernet.dli.2015.128064` |
| baraja-espanola | Fortune-telling by cards | P. R. S. Foli | 1900 | en | 208 KB | `fortunetellingby00foli` |
| numerologia | Numerology Made Plain | Ariel Yvon Taylor | 1926 | en | 229 KB | `numerologymadepl00tayl_0` |
| numerologia | The Day of Wisdom According to Number Vibrations | L. Dow Balliett | 1917 | en | 220 KB | `dayofwisdomaccor00ball` |
| numerologia | The Kabala of Numbers | Sepharial |  | en | 258 KB | `TheKabalaOfNumbers` |
| numerologia | La numerología a la luz del árbol de la vida y las letras hebraicas | Martine Coquet |  | es | 693 KB | `la-numerologia-a-la-luz-del-arbol-de-la-vida-y-l` |
| tarot | Tarot Fundamentals | Paul Foster Case | 1936 | en | 625 KB | `PaulFosterCase-TarotFundamentals-1936` |
| tarot | The Pictorial Key to the Tarot | A. E. Waite | 1911 | en | 229 KB | `a.-e.-waite-the-pictorial-key-to-the-tarot` |
| tarot | The Tarot of the Bohemians | Papus | 1896 | en | 446 KB | `tarotofbohemians00papu` |
| tarot | The Tarot of the Magicians | Oswald Wirth | 1927 | en | 561 KB | `dlscrib.com-pdf-oswald-wirth-the-tarot-of-the-ma` |
| tarot | La vía del tarot | Alejandro Jodorowsky |  | es | 901 KB | `la-via-del-tarot-alejandro-jodorowsky` |

## Libros de interés sin texto libre (conseguir por otra vía)

| Familia | Obra | Autor | Año | Idioma | Texto | Identificador |
|---|---|---|---|---|---|---|
| astrologia | Planets in Composite | Robert Hand |  | en | 0 KB | `planetsincomposi00hand` |
| astrologia | Planets in Transit | Robert Hand |  | en | 0 KB | `planetsintransit00hand` |
| astrologia | The Inner Sky | Steven Forrest |  | en | 0 KB | `innerskydynamicn00forr` |
| astrologia | The Twelve Houses | Howard Sasportas |  | en | 0 KB | `twelvehousesintr0000sasp` |
| baraja-espanola | Curso de cartomancia | Rolando Rossi |  | es | 0 KB | `cursodecartomanc0000ross` |
| baraja-espanola | El arte de echar las cartas 2: cartomancia | Emilio Salas |  | es | 0 KB | `artedeecharlasca00emil` |
| baraja-espanola | El arte de echar las cartas con la baraja española | (varios) |  | es | 0 KB | `elartedeecharlas0000unse` |
| numerologia | Cheiro's Book of Numbers | Cheiro |  | en | 0 KB | `cheirosbookofnum00chei` |
| numerologia | Numerology: The Romance in Your Name | Juno Jordan |  | en | 0 KB | `numerologyromanc00juno` |
| numerologia | Your Days Are Numbered | Florence Campbell |  | en | 0 KB | `yourdaysarenumbe0000flor` |
| tarot | The Pictorial Key to the Tarot (ed. con láminas) | A. E. Waite |  | en | 0 KB | `pictorialkeytota00arth` |
| tarot | The Symbolism of the Tarot | P. D. Ouspensky |  | en | 0 KB | `symbolismoftarot0000pdou` |
| tarot | Mastering the Tarot | Eden Gray |  | en | 0 KB | `masteringtarotba00gray` |
| tarot | Tarot for Your Self | Mary K. Greer |  | en | 0 KB | `tarotforyourself00gree` |

## Sitios web de prioridad alta (páginas por carta/signo/número)

| Dominio | Idioma | Familias | Chars/pág. | Términos/KB |
|---|---|---|---|---|
| cafeastrology.com | en | astro-en | 36478 | 2.1 |
| tarotrossana.com | es | tarot-es | 29704 | 2.5 |
| tarotcardguide.com | es | tarot-en, tarot-es | 24440 | 3.0 |
| juliantarot.com | es | numerologia-es | 22486 | 2.0 |
| www.tarotamigo.com | es | baraja-es | 17280 | 3.4 |
| astralisis.com | es | astro-es | 12969 | 2.2 |
| aistrowise.com | es | astro-es | 11562 | 1.8 |
| www.numerology.com | en | numerologia-en | 11008 | 4.6 |
| cartastarotsagrado.com | es | tarot-es | 10955 | 3.0 |
| benebellwen.com | en | tarot-en | 10931 | 7.9 |
| labyrinthos.co | en | tarot-en | 10371 | 4.3 |
| tarotgratis.com.mx | es | tarot-es | 9503 | 5.8 |
| www.astrotheme.com | en | astro-es | 9399 | 3.4 |
| aspectados.com | es | astro-es | 9373 | 2.3 |
| www.tarotdemorgana.com | es | tarot-es | 7936 | 2.6 |
| www.avastrologia.com | es | astro-es | 7826 | 2.0 |
| federacionkamira.es | es | baraja-es | 7665 | 3.6 |
| bindi-online.com | es | astro-es | 5891 | 3.1 |
| www.thetarotlady.com | en | tarot-en | 3815 | 4.3 |
| www.tarot.com | en | tarot-en | 3125 | 2.9 |
| biddytarot.com | en | tarot-en, tarot-es | 3011 | 8.3 |
| www.learntarot.com | en | tarot-en | 2626 | 0.5 |
| www.aeclectic.net | en | tarot-en | 1873 | 2.8 |

Los 76 sitios de prioridad media están en el JSONL; muchos son blogs o aplicaciones con contenido útil pero desigual y se decidirán con el juez LLM (puerta 4 de la tubería), no a ojo.

## Todavía sin inventariar (siguiente paso de A1)

- **Nivel D (lecturas trabajadas):** foros (Aeclectic Tarot Forum, r/tarotreadings) y canales de YouTube de tarotistas en español (hace falta instalar `yt-dlp`).
- **Libros en español del propio usuario:** si tienes PDFs o EPUB de Jodorowsky, Pollack en español, manuales de baraja española o astrología psicológica, son la mejor fuente que falta.
- Verificar el texto real de los EPUB ya descargados en `docs_epub` que sí son útiles (unos 25).

## Hugging Face: ¿existe algo parecido? (revisión del 2026-10-18)

Búsquedas con el CLI `hf` de modelos y datasets de tarot, astrología, horóscopo, numerología, quiromancia, cartomancia y esoterismo. **No hay nada comparable a lo que queremos hacer**: lo más descargado tiene cientos de descargas, casi todo es pequeño, en inglés, de plantilla o de astrología védica.

**Modelos** (todos pequeños y sin evaluación publicada): `TinyLlama-1.1B-Tarot-Chat`, `tarot-qwen2.5-7b`, `vedic-astrology-14b`, `kp-astrology-llama-8b`, `astrology-qwen-finetuned`, `gpt-oss-20b-turkish-astrology`. Los «Esoteric*» son mezclas de rol, no modelos de lectura.

**Datasets útiles como contraste o base estructurada:**

| Dataset | Contenido | Licencia | Uso |
|---|---|---|---|
| `Tarotoo/tarotoo-tarot-card-meanings` | 78 cartas, 22 campos: derecha/invertida, amor, carrera, espiritual, elemento, planeta, signo, sí/no | MIT | Contraste de la KB (en inglés) |
| `StarTarotOnline/tarot-rws-historical-meanings` | 78 cartas con los significados de Waite (*Pictorial Key*) y sección de origen | CC BY 4.0 | Contraste y trazabilidad |
| `Pepere45/spanish-esotericism-corpus` | Corpus **en español**, entre 1.000 y 10.000 filas, ficheros «HQ» | otra | **Acceso restringido (solicitud manual)**; solicitar acceso con la cuenta HF `Serono22` |

**Datasets que sirven de contraejemplo** (confirman el hueco): `Dendory/tarot` (5.770 lecturas de un párrafo generadas con ChatGPT a partir de 3 cartas al azar), `11-47/The_Prophet_Tarot_Zodiac_50K` (respuestas de plantilla, con textos como «placeholder for brevity»), `AmareshHebbar/numerology_pythagorean-sft` (más de 100.000 filas de numerología con hechos calculados y reglas recuperadas, pero respuestas cortas de regla y marcadas `rule_matched`). Lo valioso de este último es el **diseño** (hechos calculados + reglas recuperadas + citas), que coincide con nuestro enfoque.

No existen datasets de quiromancia ni de Lenormand/cartomancia española utilizables.
