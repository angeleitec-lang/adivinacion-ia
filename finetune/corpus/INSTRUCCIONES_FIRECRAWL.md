# Instrucciones de extracción de corpus (para Firecrawl)

## Objetivo

Recopilar manuales, técnicas, significados y tutoriales sobre adivinación
(cartomancia, astrología, numerología, quiromancia y afines) en español, en
formato markdown limpio, para construir el corpus de reentrenamiento de un
LLM de lecturas.

## PROMPT (pegar tal cual en Firecrawl `agent`)

```
Eres un recopilador de material de referencia sobre adivinación. Tu misión es
encontrar y devolver, en markdown limpio y en español, el contenido más
completo y riguroso sobre cada una de estas familias y sus subtemas:

1. Tarot: significados de los 22 Arcanos Mayores y de los 56 Arcanos Menores
   (palos de copas, espadas, bastos y oros; carta por carta, al derecho y a
   la inversa). Sistemas: Rider-Waite-Smith, Tarot de Marsella y Thoth.
   Tiradas: carta única, tres cartas (pasado/presente/futuro), Cruz Celta
   (10 cartas) y herradura.
2. Lenormand: las 36 cartas y sus combinaciones de pares. Baraja española
   (oros, copas, espadas, bastos, 40/48 naipes). Kipper, Sibilla y naipes
   franceses.
3. Astrología: carta natal (Sol, Luna, Mercurio, Venus, Marte, Júpiter,
   Saturno, Urano, Neptuno, Plutón, ascendente y nodos lunares); signo
   solar, lunar y ascendente; las 12 casas y su significado; los 5 aspectos
   (conjunción, sextil, cuadratura, trígono, oposición); tránsitos,
   revolución solar, progresiones, sinastría, astrología horaria, védica
   (Jyotish) y china.
4. Numerología: camino de vida, número de destino/expresión, número del alma,
   número de la personalidad, año y mes personales, compatibilidad. Números
   del 1 al 9 y números maestros 11, 22 y 33.
5. Quiromancia: líneas mayores (corazón, cabeza, vida, destino), líneas
   menores (Sol, Mercurio, cinturón de Venus, matrimonio), montes (Venus,
   Júpiter, Saturno, Apolo, Mercurio, Marte, Luna), forma de la mano según
   los 4 elementos, dedos y falanges, dermatoglifos y onicomancia.
6. Otras: I Ching (64 hexagramas), runas (Futhark, 24), cafeomancia,
   tasseografía, cristalomancia, péndulo y biorritmos.

Para cada tema devuelve: explicación clara, significados concretos, ejemplos
de lectura e interpretación, y fórmulas o pasos cuando existan. Prioriza el
español. Indica la URL de origen de cada bloque. Evita anuncios, formularios
de contacto, pasarelas de pago y contenido de registro.
```

## Manifiesto de fuentes (URLs semilla)

### Dominio público / CC (columna vertebral, prioridad alta)

- `es.wikipedia.org` — Tarot, Arcanos mayores, Arcanos menores, Tarot de
  Marsella, Rider-Waite-Smith, Astrología, Carta astral, Casa (astrología),
  Signo zodiacal, Aspecto (astrología), Numerología, Quiromancia, I Ching,
  Alfabeto rúnico, Astrología china, Astrología védica, Marie Anne Lenormand.
- `es.wikisource.org` — Papus "El Tarot de los Bohemios", Etteilla y textos
  clásicos de dominio público.
- `gutenberg.org` — Papus, Éliphas Lévi y manuales clásicos (dominio público).
- `archive.org` — manuales escaneados de dominio público.

### Tarot (consultar licencia)

- cartastarotsagrado.com
- esotericouniverso.es/tarot/
- consultasespirituales.net/tarot/
- moritarot.com/es/tarot_knowledge/
- tarot-amor-destino.com

### Lenormand y baraja española (consultar licencia)

- lenormand.life/es/learn-lenormand
- tarotbrisatalis.com
- meutarot.com/es/cartas-del-tarot/lenormand
- bindi-online.com
- labyrinthos.co/blogs/lenormand-cards (EN)

### Astrología (consultar licencia)

- tucartastral.com/blog/casas-astrologicas-significado
- mi.astrocentro.com/astrologia/articulo/E1712-casas-astrologicas
- astrocarto.org/es/astrology-houses/
- ladamadelzodiaco.com/casas-astrologicas
- ladoastral.com/astrologia/las-12-casas
- gaia.com/es/article/las-12-casas-astrologicas
- astral-mood.com/es/casas
- magicalchart.com/es/casas-astrologicas

### Numerología (consultar licencia)

- gaia.com/es/article/numeros-de-vida
- mi.astrocentro.com/numerologia/mag/camino-de-vida-significado
- numerovya.com/es/camino-de-vida-una-direccion-fundamental
- astrolium.com/es/guides/numerology
- esotericouniverso.es/numerologia/numeros-de-camino-de-vida/
- tucartastral.com/blog/numerologia-camino-de-vida
- numastra.com
- nymero.org/es/numero-camino-vida/
- mybornday.com/es/numerologia/

### Quiromancia (consultar licencia)

- es.wikihow.com/leer-la-mano
- karmaweather.com/es/misticismo/esoterismo/quiromancia-lineas-mano
- gaia.com/es/article/quiromancia-que-es
- elrincondeunachiari.com/esoterismo/adivinacion/guia-basica-en-quiromancia-significado-de-lineas-y-montes/
- aliciagalvan.com/articulos/quiromancia/
- mundoquiromancia.com

## Reglas de extracción

1. **Idioma**: priorizar español; aceptar inglés solo para fuentes sin
   equivalente (p. ej. labyrinthos).
2. **Formato**: markdown limpio, sin banners de cookies, anuncios, menús ni
   pies repetidos.
3. **Atribución**: guardar URL de origen y licencia estimada por cada bloque
   en `manifest.json`.
4. **Desduplicación**: no repetir bloques idénticos entre fuentes.
5. **Robots.txt**: si un sitio bloquea el rastreo, marcarlo como bloqueado;
   no forzar.
6. **Profundidad**: en cada dominio, seguir enlaces internos que desarrollen
   los temas listados, hasta agotar el contenido relevante.

## Exclusiones

- Contenido de pago, áreas de registro, anuncios y enlaces de afiliados.
- Sitios que exijan login o CAPTCHA de forma agresiva.
- Foros/comentarios de usuarios (ruido) salvo que sean guías técnicas.
- Contenido con licencia claramente incompatible (p. ej. "prohibida su
  reproducción" sin permiso): marcarlo en el manifest, no incluirlo.

## Salida esperada

- `corpus/raw/<dominio>/<slug>.md` — una página por fichero markdown.
- `corpus/manifest.json` — `[{url, dominio, licencia, estado, fecha}]`.
- `corpus/raw/agent_output.json` — si se usa el modo agent.
