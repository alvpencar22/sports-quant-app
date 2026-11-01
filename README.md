# ⚽ Sports Quant App — Plataforma Cuantitativa de Apuestas Deportivas

Aplicación modular en Python para la **ingestión automatizada, evaluación matemática imparcial y optimización combinatoria de apuestas deportivas** basada en el historial empírico del sistema (`historial_prompt.txt`).

---

## 🚀 Características Principales

1. **Ingestión y Reconciliación Automatizada:**
   - Lee y parsea directamente el archivo maestro `data/historial_prompt.txt` (+1,320 pronósticos, 49 partidos).
   - Detecta ligas (La Liga, Serie A, Bundesliga, Champions League, Premier League).
   - Reconcilia automáticamente Cuotas Justas pre-partido si el post-partido tiene campos en blanco.
2. **Cero Sesgo de Mercado (Zero Bias Policy):**
   - Evalúa **todos los mercados por igual** sin vetos subjetivos previos (Tiros de Equipo, Tiros Totales, Córners, Tarjetas, Player Props, Goles, BTTS).
   - Los datos empíricos ($N$, $W$, $L$, Hit Rate, Break-Even, Margen) dictan el valor real de forma 100% matemática.
3. **Cálculo Dinámico de Desplazamientos Arbitrarios ($X+k$ de $X-6$ a $X+6$ y Unders):**
   - Calcula la probabilidad empírica de acierto para cualquier línea alternativa:
     $$\text{Over } X+k \implies P(\text{Margen} \ge k) = \frac{\sum \mathbf{1}_{\text{Margen} \ge k}}{N}$$
     $$\text{Under } X+k \implies P(\text{Margen} < k) = \frac{\sum \mathbf{1}_{\text{Margen} < k}}{N}$$
   - Genera el espectro completo de líneas con su respectivo Break-Even ($BE = \frac{1}{\text{HR}}$) y Valor Esperado ($\mathbb{E}[V] = CR \times HR - 1$).
4. **Ciclo Operativo Completo en 3 Tiempos:**
   - **Tiempo 1 (Ex-Ante):** Ingesta hojas pre-partido, clasifica en la matriz 2D (Categoría $\times$ Franja CJ $\times$ Liga), calcula Hit Rate, BE y EV.
   - **Tiempo 2 (Descalados y Optimización de Balas):** Ingesta cuotas de descalados y resuelve el trío óptimo de **3 Balas Definitivas** con **0 solapamiento**, máx 2 legs por bala y cuota objetivo [@ 1.80 – @ 2.35].
   - **Post-Partido (Auditoría y PnL):** Ingesta veredictos y márgenes, liquida las 3 balas, calcula beneficio neto y ROI / Yield %, e incorpora el nuevo partido al historial.
5. **Múltiples Interfaces de Usuario:**
   - **CLI (`cli.py`):** Comandos rápidos para terminal y pipelines automatizados.
   - **Menú Interactivo (`main.py`):** Interfaz guiada por consola paso a paso.
   - **Dashboard Web (`dashboard.py`):** Interfaz gráfica interactiva moderna en Streamlit.

---

## 📁 Estructura del Proyecto

```text
sports_quant_app/
│
├── data/
│   ├── historial_prompt.txt          <- Archivo fuente con el histórico completo de partidos
│   ├── categorized_dataset.json      <- Base de datos estructurada en JSON
│   ├── matrix_2d.json                <- Matriz empírica multidimensional
│   └── matches/                      <- Hojas pre-partido y evaluaciones temporales
│
├── quant_engine/
│   ├── __init__.py
│   ├── parser.py                     <- Parser universal de líneas, cuotas, veredictos y márgenes
│   ├── categories.py                 <- Clasificador canónico e imparcial de mercados
│   ├── math_engine.py                <- Motor cuantitativo de Hit Rates, EVs y espectro de líneas X+k
│   ├── optimizer.py                  <- Optimizador combinatorio de 3 Balas con 0 solapamiento
│   └── auditor.py                    <- Liquidador post-partido y sincronizador del historial
│
├── tests/
│   └── test_math.py                  <- Pruebas de verificación de cálculos y distribuciones
│
├── cli.py                            <- Interfaz de línea de comandos
├── main.py                           <- Menú interactivo guiado por consola
├── dashboard.py                      <- Dashboard web interactivo con Streamlit
├── requirements.txt                  <- Dependencias del proyecto
└── README.md                         <- Manual de usuario y referencia matemática
```

---

## 🧮 Fundamentos Matemáticos

### 1. Cuota Break-Even y Valor Esperado
Para cualquier selección con Hit Rate empírico $HR \in (0, 1]$ y Cuota Real de la casa $CR$:
$$\text{Break-Even} = \frac{1}{HR}$$
$$\mathbb{E}[V] = (CR \times HR) - 1 = \frac{CR}{\text{Break-Even}} - 1$$
- $\mathbb{E}[V] > 0$: **Ventaja Matemática (Edge positivo / Valor).**
- $\mathbb{E}[V] < 0$: **Margen desfavorable para el apostador.**

### 2. Desplazamientos Arbitrarios de Línea ($X+k$)
A partir de la distribución empírica de márgenes de una categoría y franja CJ:
- **Línea Over $X + k$ ($k \in [-6, +6]$):**
  Acierta si el resultado real supera la línea desplazada. En términos de margen respecto a la línea base $X$:
  $$\text{Hit Rate}(X+k) = \frac{\sum_{i=1}^N \mathbf{1}_{\text{Margen}_i \ge k}}{N}$$
- **Línea Under $X + k$ ($k \in [-6, +6]$):**
  Acierta si el resultado real queda por debajo de la línea desplazada:
  $$\text{Hit Rate}_{\text{under}}(X+k) = \frac{\sum_{i=1}^N \mathbf{1}_{\text{Margen}_i < k}}{N}$$

### 3. Distribución Estadística de Márgenes
Para cada mercado se calcula:
$$\mu_M = \frac{1}{N} \sum_{i=1}^N M_i, \quad s_M = \sqrt{\frac{1}{N-1} \sum_{i=1}^N (M_i - \mu_M)^2}$$
Junto con percentiles ($p_{25}, p_{50}, p_{75}$) e histograma completo de frecuencias.

### 4. Restricciones del Optimizador de 3 Balas
El algoritmo resuelve:
$$\max \sum_{i=1}^3 \mathbb{E}[V]_i \quad \text{y} \quad \max P(\ge 2 \text{ aciertos})$$
Sujeto a:
1. $CR_i \in [1.80, 2.35] \quad \forall i \in \{1, 2, 3\}$.
2. $\text{NumLegs}(Bala_i) \le 2 \quad \forall i \in \{1, 2, 3\}$.
3. $\text{Legs}(Bala_1) \cap \text{Legs}(Bala_2) = \emptyset$.
4. $\text{Legs}(Bala_1) \cap \text{Legs}(Bala_3) = \emptyset$.
5. $\text{Legs}(Bala_2) \cap \text{Legs}(Bala_3) = \emptyset$.
6. Independencia de jugadores: ningún jugador se repite en más de una bala.

---

## 💻 Guía de Uso

### Opción 1: Menú Interactivo (Recomendada para el día a día)
Ejecuta:
```bash
python main.py
```
Aparecerá el menú interactivo:
```text
======================================================================
 ⚽ SPORTS QUANT APP — SISTEMA CUANTITATIVO DE APUESTAS
======================================================================
 [1] 📊 Ver Estado del Sistema y Estadísticas de Ligas / Mercados
 [2] 🔍 Explorar Líneas Arbitrarias X+k (de X-6 a X+6 y Unders)
 [3] ⏱️ Analizar Hoja Pre-Partido (Tiempo 1: Ex-Ante)
 [4] 🎯 Optimizar 3 Balas Definitivas con Descalados (Tiempo 2)
 [5] 🏁 Auditar Resultados Post-Partido y Actualizar Historial
 [6] 🔄 Re-indexar y Re-parsear historial_prompt.txt
 [0] 🚪 Salir
======================================================================
```

---

### Opción 2: Dashboard Web (Streamlit)
Para abrir la interfaz visual en tu navegador:
```bash
streamlit run dashboard.py
```
Permite explorar gráficos interactivos de márgenes, pegar pronósticos en un área de texto y optimizar balas en tiempo real.

---

### Opción 3: Comandos de Consola (CLI)

#### 1. Ver Estado General del Sistema
```bash
python cli.py status
```

#### 2. Explorar Espectro Completo de Líneas (X-6 a X+6 y Unders)
Explora sin sesgos cualquier mercado (por ejemplo, Tiros de Jugador, Tiros Totales, Córners o Goles):
```bash
python cli.py explore "Player - Tiros Totales" --cj 1.45 --k_min -6 --k_max 6
```
```bash
python cli.py explore "Partido - Tiros Totales (Overs)" --k_min -6 --k_max 6
```

#### 3. Tiempo 1: Evaluar Hoja Pre-Partido
```bash
python cli.py t1 data/matches/sheet_atletico_prematch.txt --league "La Liga"
```

#### 4. Tiempo 2: Optimizar las 3 Balas Definitivas
```bash
python cli.py t2 --descalados "julian 2 tiros 1.18, manu sanchez 2 entradas 1.28, over 1.5 goles 1.16, over 3.5 tarjetas 1.66" --min_odds 1.80 --max_odds 2.35
```

#### 5. Post-Partido: Auditar Resultados y Liquidar PnL
```bash
python cli.py audit
```
O con archivo de resultados oficiales:
```bash
python cli.py audit --results ruta_a_resultados.txt
```

---

## 🔄 Actualización Continua del Historial

Cuando se dispute un nuevo partido, basta con pegar el bloque de resultados con `Veredicto: [SI/NO]` y `Margen: [+/- X]` en `data/historial_prompt.txt` (o usar la opción 5/6 del menú) para que todo el motor cuantitativo, las probabilidades empíricas y las matrices se re-calibren automáticamente.
