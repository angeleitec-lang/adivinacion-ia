# Diseño de la app web monetizada de adivinación por IA

> Documento de diseño (spec) — pendiente de aprobación del usuario.
> Fecha: 2026-10-18. Idioma del producto: español.

## 1. Intención y por qué

Crear una app web que haga predicciones y lecturas combinando varias disciplinas
adivinatorias (tarot, carta astral, numerología y, más adelante, quiromancia por
cámara), usando un modelo de lenguaje de pesos abiertos entrenado para ese fin.

El porqué: el usuario quiere empezar como hobby con vocación de negocio/producto
monetizado desde el primer día. Busca que la lectura sea real (cálculo astronómico
de verdad, cartas reales, líneas de la mano detectadas por cámara), no un generador
de frases genéricas.

## 2. Objetivos, no-objetivos y anti-objetivos

### Objetivos (V1)
- Tirada de tarot: barajar, cortar, sacar cartas y que el modelo las interprete en
  función de la pregunta del usuario, su posición y su relación entre sí.
- Corte del mazo por el usuario (requisito V1, ver §2.1): antes de la tirada, el
  usuario formula su pregunta y corta el mazo digital arrastrándolo.
- Carta astral: calcular con astronomía real (Swiss Ephemeris) a partir de fecha,
  hora y lugar de nacimiento, y que el modelo la interprete (signos, casas, aspectos).
- Numerología: cálculo de números clave (camino de vida, destino, etc.) e interpretación.
- Combinar las tres fuentes en una sola respuesta coherente a la pregunta "¿qué
  necesitas saber?".
- Monetización: pago por lectura + freemium con lecturas limitadas.
- Todo el producto en español.

### 2.1 Requisito: pregunta y corte del mazo (V1)

Decisión del usuario (2026-10-18): para la V1, la tirada de tarot incluye **pregunta
previa + corte del mazo por arrastre**. Hace la lectura más personal sin cambiar quién
calcula la tirada.

- **Orden del flujo:** pregunta (obligatoria) → corte por arrastre → reparto y volteo de
  cartas → interpretación.
- **Gesto:** el mazo aparece boca abajo; el usuario arrastra la parte superior hacia un
  lado y la suelta. La distancia del arrastre, en proporción al ancho del mazo, fija la
  posición de corte `k` (entero de 1 a 77 sobre 78 cartas). Sirve con ratón y con
  pantalla táctil (eventos de puntero).
- **Alternativas obligatorias:** control por teclado (flechas para elegir `k` y Enter para
  cortar), botón «Cortar por mí» (el cliente elige un `k` al azar) y respeto de
  `prefers-reduced-motion` (sin animación de arrastre, solo selección).
- **Reparto de responsabilidades:** el cliente envía únicamente `corte` (la posición `k`).
  El servidor baraja con su propia semilla secreta y aplica el corte como rotación del
  mazo en `k`; el orden barajado nunca llega al navegador antes de la lectura. El frontend
  no decide qué cartas salen.
- **Reproducibilidad:** se guardan junto a la lectura la semilla, `k` y la orientación de
  cada carta. Con los mismos valores, la tirada es idéntica.
- **Nota de honestidad:** como el mazo ya viene barajado por el servidor, el corte es un
  gesto ritual que personaliza la experiencia; no se presenta como algo que cambie el
  resultado más allá de eso.
- **Dónde se refleja:** `Mazo.cortar(en)` con rango 1–77 y orientación reproducible
  en `2026-10-18-nucleo-calculo.md` (Task 2); campo `corte` y guardado de semilla en
  `2026-10-18-backend-api.md` (Task 2); gesto y componente en
  `2026-10-18-frontend.md` (Task 3A).

### No-objetivos (fuera de V1)
- Contacto sostenido de 3 s («concentración») antes del corte: se reserva para el modo
  móvil, posterior a la V1.
- Elección de cartas desde un abanico y corte en tres montones: variantes futuras.
- Quiromancia por cámara (se deja para la Fase 2; es la pieza más arriesgada y
  requiere visión por computador).
- Otras técnicas (I Ching, runas, Lenormand, etc.) aunque el mapa de técnicas está
  documentado en `~/tecnicasCartomancia.md` para incorporarlas después.
- Internacionalización: solo español por ahora.
- App móvil nativa (se empieza web).

### Anti-objetivos (fracaso aunque técnicamente funcione)
- Respuestas genéricas de horóscopo prefabricado que no dependan de los datos reales
  de la tirada, la carta astral o los números calculados.
- Un "fine-tune" que solo memorice frases y no razone sobre la entrada concreta.
- Producto que dependa de datos cuya licencia prohíba uso comercial.

## 3. Restricciones

- Modelo de pesos abiertos con licencia apta para uso comercial (Apache-2.0
  preferente; descartar licencias no comerciales tipo CC-BY-NC).
- Herramientas impuestas por el usuario:
  - Fine-tune: repo `MakazhanAlpamys/Soup` (https://github.com/MakazhanAlpamys/Soup).
  - Extracción de datos: `firecrawl/firecrawl` (https://github.com/firecrawl/firecrawl).
- El cálculo de la carta astral NO lo hace el LLM: lo hace una librería de
  astronomía (Swiss Ephemeris / pyswisseph). El modelo solo interpreta.
- Hardware disponible: nodo1 (10.0.0.3) y nodo2 (10.0.0.4) como servidores GPU
  compute (ver "Pendiente de confirmar"). Mac mini M2 Pro como servidor de Postgres
  y Ollama (nomic-embed-text).
- Dos vías de desarrollo a la vez (aprobado por el usuario):
  - Track A: fine-tune del modelo.
  - Track B: RAG con corpus curado.

## 4. Decisiones del usuario (cómo lo decidió él)

1. Monetización combinada: (a) pago por lectura y (b) freemium que "excluye lo
   interesante para que el cliente decida pagar por la información".
2. Audiencia: solo español al inicio.
3. El stack lo propongo yo (ver sección 7). Herramientas de datos y fine-tune ya
   fijadas (Soup + Firecrawl).
4. Empezar las dos vías (fine-tune y RAG) a la vez.
5. V1 = Tarot + Carta astral + Numerología (texto, sin visión). Fase 2 = quiromancia.

## 5. Distinción técnica de las dos vías

- **Track B (RAG)**: modelo base + corpus curado de tarot/astrología/numerología
  indexado con embeddings; ante cada consulta se recuperan los fragmentos relevantes
  y se inyectan en el prompt. Rápido de montar, fácil de actualizar el conocimiento.
- **Track A (fine-tune)**: se entrena el modelo sobre pares pregunta/respuesta para
  que adopte el tono, el formato y la forma de razonar de un vidente experto.
  Recomendación: hacerlo ENCIMA del resultado de B si el tono no convence.
- Ambos alimentan la misma app; B es el camino rápido y A el de refinamiento.

## 6. Modelo elegido (recomendación)

- **V1 (texto, español, monetizable)**: `Qwen/Qwen3-8B-Instruct` (alternativa
  consolidada: `Qwen/Qwen2.5-7B-Instruct`). Apache-2.0, sin gate, mejor rendimiento
  en español de los pesos abiertos, 8B se fine-tunea con Soup en 8–16 GB de VRAM.
- **Fase 2 (visión/quiromancia)**: `Qwen/Qwen3-VL-8B-Instruct` (Apache-2.0, 8B,
  multimodal). Posibilidad de unificar usando este como base única (texto+visión).
- Descartados: Aya-Expanse (CC-BY-NC, no comercial); Llama (licencia con límite de
  usuarios y gate manual); Gemma (gate). Mistral también es válido (Apache-2.0).

## 7. Stack (CONFIRMADO por el usuario el 2026-10-18)

- **Frontend**: Next.js (React) — web app interactiva para las tiradas y el pago.
- **Backend**: FastAPI (Python) — motor de cálculo (Swiss Ephemeris), orquestación
  de RAG y fine-tune, y API para el frontend.
- **Base de datos**: Postgres (en Mac mini 10.0.0.1) para usuarios, lecturas, pagos,
  y `pgvector` para el índice de embeddings del RAG.
- **Astronomía**: `pyswisseph` (Swiss Ephemeris) para la carta astral.
- **RAG**: embeddings con Ollama (`nomic-embed-text`) y vector store en pgvector.
- **Inferencia del LLM**: servido con `soup serve` (API OpenAI-compatible) en
  nodo1/nodo2, o vía Ollama tras exportar a GGUF.
- **Fine-tune**: `soup train` con QLoRA sobre el modelo base, en nodo1/nodo2.
- **Extracción de corpus**: Firecrawl (crawl/scrape a markdown) sobre sitios de
  referencia de tarot, astrología y numerología.
- **Pagos**: Stripe (decisión por defecto mía) — se pospone a un diseño posterior
  de la pieza de monetización.

### Infraestructura real del homelab (relevante para el stack)

- **Inferencia LLM**: nodo1 (10.0.0.3) y nodo2 (10.0.0.4) exponen API
  OpenAI-compatible en `:8000` vía `halogen` (motor `flash_serve`, checkpoint
  4-bit `qwen38-flash-next-w4b.hgn`, Qwen3.8-27B, ctx 262144). No es
  vLLM/llama.cpp: motor propio en contenedor podman.
- **Embeddings**: Ollama en el mini (10.0.0.1) con `nomic-embed-text`. La NPU de
  halogen para embeddings/rerank está desactivada (decisión del usuario).
- **Vector store**: pgvector en Postgres del mini.
- **Transferencia de modelos**: rsync daemon en nodo1 (`rsync://10.0.0.3/models/`)
  y nodo2, sin cifrado (~Gbps), pensado para GGUF grandes.
- **Fine-tune**: el motor halogen NO usa PyTorch/transformers, así que Soup
  necesita un entorno ROCm PyTorch propio (venv/conda) en nodo1, separado del
  motor de inferencia. Hardware: Strix Halo (ROCm) con 128 GB unificados por
  nodo — suficiente para LoRA bf16 de 8B o QLoRA de 14B/24B.

## 8. Estructura de datos y corpus

- Corpus por disciplina (tarot: significado de los 78 arcanos por posición y
  combinación; astrología: significado de signos/casas/aspectos/tránsitos;
  numerología: números y su lectura), extraído con Firecrawl y validado en licencia.
- Para el fine-tune: datasets en formato ShareGPT/ChatML con pares
  (contexto de tirada + carta astral calculada + pregunta → lectura experta).

## 9. Riesgos y mitigación

- Riesgo: fine-tune degrada el razonamiento general. Mitigación: QLoRA con lr baja,
  dataset pequeño y de alta calidad, y evaluación con `soup eval`.
- Riesgo: lecturas genéricas. Mitigación: la carta astral se calcula de verdad y la
  tirada usa cartas reales; el prompt siempre lleva datos concretos.
- Riesgo: licencias del corpus. Mitigación: auditar licencias antes de incluir.

## 10. Decisiones cerradas y asunciones

- **Nombre del proyecto**: `adivinacion-ia` (ruta `~/adivinacion-ia/`). CONFIRMADO.
- **Stack** (sección 7): CONFIRMADO.
- **GPU**: nodo1 y nodo2 son dos **Strix Halo** (AMD Ryzen AI Max) con
  **128 GB de memoria unificada** compartida CPU/GPU (iGPU RDNA 3.5, ROCm).
  Con eso el fine-tune de 8B es holgado y 14B/24B QLoRA son viables.
  **Base: 8B** (Qwen3-8B-Instruct), con 14B como opción de calidad.
- **Pasarela de pago**: Stripe (asunción mía), se diseña en una fase posterior.
