# Guía didáctica del proyecto — Índice

Esta guía es para alguien que no sabe programar ni entrenar modelos y quiere
entender qué se ha hecho en este proyecto y dónde está cada cosa.

## Qué hay en cada fichero

1. **`01_MAPA_DE_PROGRAMAS.md`** — El mapa completo. Empieza con un esquema
   en texto del flujo entero con las cifras de hoy, y luego una ficha por cada
   programa: qué problema resuelve, qué recibe, qué produce y si se usa aún.
   Los programas están agrupados por etapas, en el orden en que actúan:
   (A) conseguir textos → (B) limpiarlos → (C) sacar ideas con IA →
   (D) consenso y base de conocimiento → (E) fabricar ejemplos →
   (F) controles de calidad → (G) entrenar y evaluar.
   Al final hay una tabla que cruza cada pista «T##» con el programa que la
   ejecutó.

2. **`02_GLOSARIO.md`** — 60 términos, cada uno con una definición de una a
   tres frases y un ejemplo del propio proyecto. Si una palabra te frena en el
   mapa, búcala aquí.

## Orden recomendado de lectura

1. El esquema ASCII del principio de `01_MAPA_DE_PROGRAMAS.md` (5 minutos).
   Da la visión de conjunto: de los libros y webs al modelo entrenado.
2. Las etapas (A) a (D) del mapa: es la **fase 0**, donde se aprende de las
   fuentes. Es la parte más trabajada del proyecto.
3. Las etapas (E) a (G): la **fase 1** (fabricar 13.290 ejemplos de lectura)
   y la **fase 2** (entrenar y evaluar).
4. El glosario en paralelo: al primer término raro, consultar y seguir.

## Si solo tienes 5 minutos

El proyecto hace esto: se leen miles de páginas y libros de tarot, baraja
española, astrología y numerología; una IA saca de ahí ideas sueltas
(«afirmaciones»); se agrupan por consenso en una base de conocimiento; con
esa base se fabrican 13.290 lecturas de ejemplo verificadas; y con ellas se
entrena un modelo en español que hace lecturas honestas, sin inventar y sin
prometer lo que no puede prometer.

## Dónde está el resto de la documentación

- `docs/ESTADO_Y_PENDIENTES.md` — traspaso completo: decisiones, cifras,
  procesos en marcha y pendientes.
- `docs/PIPELINE.md` — el mismo mapa pero técnico (para quien ejecute los
  comandos).
- `docs/ARMAR_DATASET_V1D.md` y `docs/CIERRE_FINAL.md` — de dónde salen las
  cifras de esta guía.
- `finetune/GUIA_REENTRENAMIENTO.md` — cómo se entrena cuando toque.
