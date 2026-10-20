# Libros faltantes: disponibilidad LEGAL (T39)

Consulta realizada el 2026-10-20. **Regla dura: solo fuentes legales.** Ninguna entrada enlaza piratería. Los precios no se han podido verificar por vía automatizada (Google Books API sin cuota diaria; Fnac 403; Casa del Libro y Buscalibre con render JavaScript; Llewellyn 404; DuckDuckGo con challenge; HathiTrust 403), por lo que van a `null` con nota de consulta manual pendiente.

Fuentes de las que sí se obtuvo dato fiable: Open Library (`search.json`) e Internet Archive (`advancedsearch.php` / páginas de préstamo controlado).

## Cobertura actual (cruce con `~/fase0/cobertura_total.md`)

| Familia | Celdas | Completas | % |
|---|---|---|---|
| Baraja española | 480 | 2 | 0,4 % (CRÍTICO) |
| Numerología | 792 | 5 | 0,6 % (CRÍTICO) |
| Astrología | 5247 | 79 | 1,5 % |
| Tarot | 936 | 173 | 18,5 % |

Las celdas bajo mínimo exigen 5 fuentes independientes + 1 clásica + 2 modernas + 1 en español.

## Tabla de libros faltantes (15)

| Libro | Autor | Año | Estado legal | Vía legal | Coste |
|---|---|---|---|---|---|
| The Symbolism of the Tarot (Символы Таро) | P. D. Ouspensky | 1913 | Dominio público (m. 1947) | [Wikisource RU](https://ru.wikisource.org/wiki/%D0%A1%D0%B8%D0%BC%D0%B2%D0%BE%D0%BB%D1%8B_%D0%A2%D0%B0%D1%80%D0%BE_(%D0%A3%D1%81%D0%BF%D0%B5%D0%BD%D1%81%D0%BA%D0%B8%D0%B9)) | Gratis |
| El arte de echar las cartas con la baraja española | anónimo (atrib. A. Mercadal) | 1997 | Copyright vigente | [Préstamo IA](https://archive.org/details/elartedeecharlas0000unse) | Gratis (biblioteca) |
| El arte de echar las cartas 2: cartomancia | Emilio Salas | 1986 | Copyright vigente | [Préstamo IA](https://archive.org/details/artedeecharlasca00emil) / compra | Pendiente |
| Curso de cartomancia | Rolando Rossi | 1993 | Copyright vigente | [Préstamo IA](https://archive.org/details/cursodecartomanc0000ross) | Gratis (biblioteca) |
| Tarot con cartas españolas | Beltrame (sin identificar) | — | No localizado | Ninguna verificada | — |
| Numerology: The Romance in Your Name | Juno Jordan | 1977 | Copyright vigente | [Préstamo IA](https://archive.org/details/numerologyromanc00juno) | Gratis (biblioteca) |
| Your Days Are Numbered | Florence Campbell | 1931 | Copyright vigente (PD incierto, depende de renovación) | Solo Open Library (sin escaneo) | Pendiente |
| Planets in Transit | Robert Hand | 1976 | Copyright vigente | [Préstamo IA](https://archive.org/details/planetsintransit00hand) | Gratis (biblioteca) |
| Planets in Composite | Robert Hand | 1975 | Copyright vigente | [Préstamo IA](https://archive.org/details/planetsincomposi00hand) | Gratis (biblioteca) |
| The Twelve Houses | Howard Sasportas | 1985 | Copyright vigente | [Préstamo IA](https://archive.org/details/twelvehousesintr0000sasp) | Gratis (biblioteca) |
| The Inner Sky | Steven Forrest | 1984 | Copyright vigente | [Préstamo IA](https://archive.org/details/innerskydynamicn00forr) | Gratis (biblioteca) |
| Mastering the Tarot | Eden Gray | 1971 | Copyright vigente | [Préstamo IA](https://archive.org/details/masteringtarotba00gray) | Gratis (biblioteca) |
| Tarot for Your Self | Mary K. Greer | 1984 | Copyright vigente | [Préstamo IA](https://archive.org/details/tarotforyourself00gree) / compra | Pendiente |
| El gran libro del tarot | Hajo Banzhaf | 2003 | Copyright vigente | [Ítem IA (HTTP 500 intermitente)](https://archive.org/details/el-gran-libro-del-tarot-hajo-banzhaf) / compra | Pendiente |
| El arte de tirar el tarot | Vanessa Bell | 1999 | Copyright vigente | [Préstamo IA (HTTP 500 intermitente)](https://archive.org/details/elartedetirarelt00vane) | Gratis (biblioteca) |

## Recomendación priorizada (por celdas de la matriz que cubriría)

**Prioridad 1 — Baraja española (0,4 %, la peor cobertura).**
Cubrir con los tres títulos en español: Rossi *Curso de cartomancia*, Salas *El arte de echar las cartas 2* y el anónimo/Mercadal *El arte de echar las cartas con la baraja española*. Los tres están en préstamo controlado de Internet Archive: acceso legal sin coste. Salas es además lista corta de compra: si el préstamo resulta insuficiente para extraer texto de calidad, es el primer candidato a compra. *Beltrame* **no se compra hasta localizar edición verificada** (0 hits en Open Library; autor sin identificar).

**Prioridad 2 — Numerología (0,6 %).**
Juno Jordan (préstamo IA, gratis) aporta la fuente clásica moderna del sistema pitagórico de nombres; Campbell complementa días/personal. Campbell (1931) no tiene escaneo legal: valorar compra solo si Jordan no basta. Los números críticos (11, 1, 22, 2, 33, 3, 4 × alma/año personal/camino de vida/destino/mes personal/personalidad) necesitan además fuentes web en español ya inventariadas; estos dos libros dan profundidad, no amplitud.

**Prioridad 3 — Astrología (1,5 %).**
Hand (*Transits*, *Composite*), Sasportas (*Casas*) y Forrest (*Inner Sky*) son los estándares de sus subtemas; todos en préstamo IA sin coste. Compra solo si el préstamo no permite extracción.

**Prioridad 4 — Tarot (18,5 %, la mejor cubierta).**
Empezar por lo gratis: **Ouspensky es dominio público** (original ruso en Wikisource; la traducción inglesa de 1921 no está verificada en alojamiento legal, la traducción al español habría que hacerla nosotras). Greer y Banzhaf (lista corta de compra) son los únicos que justificarían gasto en tarot, y solo tras agotar el préstamo IA. Gray y Bell quedan en préstamo.

**Presupuesto:** con préstamo bibliotecario (Internet Archive/eBiblio) los 15 libros son accesibles legalmente sin gastar nada. La compra mínima justificada por cobertura sería: **Salas** (baraja española, crítico, en lista corta) y, si se quiere traducción de referencia en vez de hacerla, **Greer**. Nada más hasta ver qué rinde el préstamo.

## Avisos

- La nota del inventario que decía que *Simbolismo de los Tarot* ya estaba descargado en `docs_epub` es **falsa** (verificado ausente el 2026-10-20).
- Los ítems de Banzhaf y Bell devuelven HTTP 500 intermitente en Internet Archive; reintentar más tarde.
- Ningún precio es verificable por vía automatizada hoy; antes de comprar, consultar manualmente Fnac/Casa del Libro/Llewellyn y anotar fecha y precio.
