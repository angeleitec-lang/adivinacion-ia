# Fuentes clasicas de dominio publico (T55)

Fecha de comprobacion: **2026-10-20**. Todas las URLs de `fuentes_clasicas_pd.jsonl`
se abrieron realmente con `curl` (HEAD y, cuando HEAD no bastaba, GET con `Range`)
y devolvieron **HTTP 200** (Fabre d'Olivet, 206 en GET Range). Cada peticion respeto
pausas de >= 1 s por dominio y no se salto ninguna proteccion.

## Criterio

- Autor fallecido antes de 1956 (regla espanola de 70 anos) **o** publicacion anterior
  a 1929 (regla estadounidense). Todas las fichas cumplen al menos una.
- Solo se admiten Project Gutenberg, Internet Archive (items de dominio publico),
  Wikisource, Biblioteca Digital Hispanica y Biblioteca Virtual Miguel de Cervantes.
- `licencia_hint` es siempre `dominio_publico`; la revision legal definitiva queda
  para la fase de licencias (`finetune/corpus/license_filter.py`).
- No se repiten obras ya presentes en `fase0/libros/informe.md` (Lilly, Ptolomeo,
  Raphael, Alan Leo, Carter, Robson, Heindel, Adams; Cheiro, Sepharial *Kabala of
  Numbers*, Balliett *Day of Wisdom*, Householder, Curtiss, Goodwin, Taylor; Foli,
  Minetta, Grand Orient, Platt, Pahlavi, Le Normand, Boiteau, Trismegiste).

## Cobertura (28 fichas)

| Familia | Fichas | Prioridad alta |
|---|---|---|
| Astrologia | 19 | 7 |
| Numerologia | 5 | 4 |
| Baraja / cartomancia | 4 | 2 |

### Astrologia

Aporta la tradicion clasica que faltaba en espanol y en latin:

- **Helenistica y romana**: Manilio (*Astronomicon*, ed. Housman 1903; Wageningen
  1915; Garrod 1911) y Firmico Materno (*Mathescos libri VIII* 1897; ed. 1553).
- **Tradicion inglesa**: Zadkiel (*Grammar of Astrology* 1833), Sepharial
  (*How to Make and Read Your Own Horoscope*, *A Manual of Occultism*,
  *Directional Astrology*, *Primary Directions Made Easy*, *The Science of
  Foreknowledge*), Partridge (*Defectio Geniturarum* 1697), Gadbury (*Ephemeris*
  1682), Mercier (*Astrology in Medicine*).
- **Agrippa** (*Three Books of Occult Philosophy*, ed. 1898): libro II es la base
  historica de la numerologia; cubre tambien simbolismo.
- **En espanol**: *El libro negro o la Magia* (1886), *El gran libro de los
  oraculos* (1841), *Almanaque profetico de Espana* (1844), Feijoo (*Teatro
  critico universal*, Wikisource) y *La rueda de adivinar* (1890). Son fuente
  popular y critica, no manuales tecnicos, salvo el primero.

### Numerologia

- Westcott, *Numbers: Their Occult Power and Mystic Virtues* (1890 y 1911): la
  exposicion clasica mas sistematica.
- L. Dow Balliett, *The Philosophy of Numbers* (1908): origen de la numerologia
  de vibraciones y colores; no duplica *The Day of Wisdom*.
- Jamblico, *The Life of Pythagoras* (trad. Taylor, 1918) y Fabre d'Olivet,
  *The Golden Verses of Pythagoras* (1917): fundamento filosofico pitagorico.

### Baraja y cartomancia

- **`libro_negro_1886` es el hallazgo de la pista**: unico manual PD localizado
  en espanol que trata explicitamente la cartomancia con **palos espanoles**
  (espadas, bastos, oros, copas) y su equivalencia con los palos franceses.
  Incluye capitulos de cartomancia y de adivinar por los naipes, ademas de
  astrologia y virtudes de los numeros. Prioridad maxima.
- Richmond, *The Mystic Test Book* (1893 y 1919) y Prime-Stevenson, *The Square
  of Sevens* (1899): metodos de cartomancia con baraja francesa, utiles para
  tecnicas de tirada y correspondencias, **no** para palos espanoles.

## Huecos y bloqueos

- **Baraja espanola en espanol**: el hueco sigue siendo grande. Solo hay un manual
  PD real (`libro_negro_1886`) mas textos populares tangenciales. Los manuales
  modernos de archive.org (`artedeecharlasca00emil` 1986,
  `cursodecartomanc0000ross` 1993, `elartedeecharlas0000unse` 1995,
  `los4antigousmeto0000fran` 2002) estan en prestamo restringido y no son PD.
- **BNE / Hemeroteca Digital / Biblioteca Virtual Miguel de Cervantes**: los
  dominios `datos.bne.es`, `bdh.bne.es`, `hemerotecadigital.bne.es`, `www.bne.es`
  y el buscador de `cervantesvirtual.com` responden **HTTP 403** con `curl` y UA
  de navegador (WAF). No es que no existan: no son verificables por automatizacion
  desde esta red. Los escaneos de la BNE que si son accesibles llegan a traves de
  archive.org (`AGuichot0879`, `b28748803`, `A11401406`). Queda pendiente una
  revision manual desde navegador o una pista especifica con otro metodo de acceso.
- **Dorotheus, *Carmen Astrologicum***: solo hay una Teubner de 2016 y una
  reelaboracion de 2024; **no PD**.
- **Abu Ma'shar**: no se localizo ninguna traduccion de dominio publico.
- **Agrippa 1651**: el item de 1651 no tiene `.txt`; se usa la edicion de 1898.
- **Juno Jordan** (1977): fuera de dominio publico, como ya advertia el encargo.
- **`HCa042008` "Buena ventura"**: pieza teatral sin ano, no es un manual.

## Siguiente paso

`finetune/corpus/descarga_clasicos_pd.py` descarga las fichas verificadas de
prioridad alta a `/Users/angelgonzalez/fase0/libros/crudo/` con el mismo esquema
`<id>.txt` que `libros_pipeline.py`, sin sobrescribir, con hash SHA-256 y
procedencia en `manifiesto_clasicos_pd.jsonl`. No ejecuta juez, extraccion ni
ninguna llamada a LLM.
