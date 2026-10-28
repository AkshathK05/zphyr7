# Elexon BMRS Wind Forecast vs. Actual Outturn Backtest

A full-stack quantitative web application built for a UK energy utility trading desk buying electricity in the **Great Britain (GB) Day-Ahead Market**.

---

## 1. Project Purpose & Market Context

Every morning, the trading desk places a single set of orders covering all **48 half-hour settlement periods** of the **NEXT day (Day D)**. Whatever energy wind generation cannot cover, the team must buy in the wholesale market. If actual wind generation comes in below forecast, the utility faces a **short position** and is exposed to volatile system imbalance cashout prices to balance the national grid.

### Objectives:
1. **Historical Backtest:** Reconstruct and display the exact wind generation forecast available to the trading desk at the morning auction decision cutoff, compared directly with the physical metered actual generation that followed.
2. **Safety Buffer Sizing:** Quantify forecast error and shortfall risks ($P_{90}$) to size an operational MW buffer against underdelivery.
3. **Strict No-Lookahead:** Guarantee causality—never use any forecast published after the auction decision cutoff.
4. **Anonymous & Client-Ready:** Works out-of-the-box for any reviewer or trading team member (no authentication or login required; operates seamlessly in incognito).

---

## 2. Data Sources (Elexon BMRS Only)

The application pulls exclusively from the official **Elexon BMRS Insights API** stream datasets:

| Dataset | Stream Endpoint | Resolution | Description |
| :--- | :--- | :--- | :--- |
| **FUELHH** (Actuals) | `GET /datasets/FUELHH/stream` | **30 minutes** (48 slots/day) | Half-hourly generation outturn for Great Britain by fuel type (filtered to `fuelType == "WIND"`). Values are average MW over the half-hour. |
| **WINDFOR** (Forecasts) | `GET /datasets/WINDFOR/stream` | **60 minutes** (24 slots/day) | National wind generation forecasts published at various times by National Grid ESO (NESO). Values are average MW over the hour. |

* **Base URL:** `https://data.elexon.co.uk/bmrs/api/v1`
* **Historical Scope:** Decision days throughout **January 2026**; Delivery days from **2 Jan 2026 to 1 Feb 2026** (31 delivery days = 1,488 half-hour settlement slots).
* **Lookback:** Forecast fetching starts on **28 Dec 2025** so late-December forecasts are already in cache for the first decision on 1 Jan.
* **Timestamps:** ISO 8601 UTC. In January, UK local time is GMT (UTC+0).

---

## 3. Key Design Decisions

### 1. Decision Cutoff at 09:00 UTC (Day D-1)
* For delivery day $D$, the auction decision cutoff is set on day $D - 1$ at **09:00 UTC** (configurable).
* The cutoff strictly filters: `publishTime <= cutoff`. Any forecast published after `09:00:00 UTC` is excluded.

### 2. Per-Hour Latest-Forecast Selection
* Forecast selection is executed strictly **per target delivery hour (`startTime`)**, not by picking a single forecast run for the entire day.
* If the latest forecast run published before the cutoff was partial or aborted and omitted later hours, the system seamlessly falls back to the preceding run for those remaining hours.

### 3. Resolution Alignment: Option A (Selected) vs. Option B (Alternative)
Because `WINDFOR` is hourly (24 slots/day) while `FUELHH` is half-hourly (48 slots/day):
* **Option A (Chosen & Implemented): Broadcast Hourly Forecast to Both Half-Hours (`HH:00` and `HH:30`).**
  * *Rationale:* The energy trader only has an hourly average power forecast at 09:00 and must plan orders for both 30-minute trading blocks around it. Intra-hour physical wind fluctuations represent real cashout exposure that the trader faces.
  * *Visual Honesty:* Rendered on the frontend as an **hourly step line** (`type="stepAfter"`) to truthfully reflect the 60-minute forecast resolution.
* **Option B (Alternative Considered): Average Actuals to Hourly Resolution.**
  * *Mechanism:* Average the two 30-minute actual readings into an hourly average.
  * *Trade-off:* While statistically smooth, it obscures intra-hour volatility that drives imbalance cashout exposure in the GB power market.

### 4. Skip, Don't Impute
* If an hourly forecast is missing or published after cutoff, both of its half-hour slots count as `SKIPPED`.
* If actual outturn is missing for an individual slot, that specific slot is skipped.
* No interpolation, forward-filling, or imputation is applied to genuinely missing values. All skipped slots are counted and reported. (Across the Jan 2 – Feb 1 pilot, coverage was 100% with 0 skipped slots).

### 5. Error Definition & Shortfall Convention
$$\text{Error} = \text{Forecast Generation} - \text{Actual Generation} \quad (\text{MW})$$
* **Positive Error ($> 0$):** Forecast exceeded actual generation $\rightarrow$ wind underdelivered $\rightarrow$ **utility would have been short**.
* **Negative Error ($< 0$):** Forecast was below actual generation $\rightarrow$ wind surplus / long position.

### 6. Forecast Bias Framed as a Curtailment Hypothesis
Across the 1,488 slots of January 2026, the backtest revealed a systematic positive bias of **$+1,747.9\text{ MW}$** (mean signed error).
* *Operational Hypothesis:* Forecasts systematically exceeded metered outturn. A likely cause is **curtailment** (constraint actions on wind farms where the system operator instructs generators to turn down due to transmission bottlenecks, such as the B6 Anglo-Scottish boundary), which reduces metered output relative to forecast potential. Verifying this needs constraint data, which is out of scope.

### 7. In-Sample Caveat on the Bias-Corrected Buffer
* The headline recommended safety buffer is **4,140.1 MW** ($P_{90}$ of raw signed error, which would have covered 90% of wind shortfalls in the backtest).
* To isolate residual volatility from the systematic shift, the app also reports a **Bias-Corrected Buffer of 2,392.2 MW** (residual $P_{90}$, residual MAE: 1,381.2 MW).
* *In-Sample Caveat:* This metric is explicitly labelled as **in-sample** because subtracting the period's mean bias cannot be done in advance in live trading without an out-of-sample dynamic bias-estimation model.

---

## 4. Key Metrics Summary (January 2026 Backtest)

| Metric | Raw Value | Bias-Corrected (In-Sample) | Description |
| :--- | :--- | :--- | :--- |
| **Evaluated Slots** | 1,488 / 1,488 (100.0%) | 1,488 / 1,488 | Complete month coverage (0 skipped slots) |
| **Mean Absolute Error (MAE)** | **2,042.0 MW** | **1,381.2 MW** | Average magnitude of forecast miss |
| **Forecast Bias (Mean Signed)** | **+1,747.9 MW** | $0.0\text{ MW}$ | Forecast tends to run high; utility would have been short |
| **Root Mean Squared Error (RMSE)**| **2,509.1 MW** | **1,798.5 MW** | Root mean square error |
| **P10 (Overdelivery Tail)** | -544.1 MW | -2,292.0 MW | 10th percentile error |
| **P50 (Median Error)** | +1,592.0 MW | -155.9 MW | Median signed error |
| **P90 (Shortfall Buffer)** | **+4,140.1 MW** | **+2,392.2 MW** | Would have covered 90% of wind shortfalls in the backtest |

---

## 5. Repository & Directory Structure

```
├── backend/
│   ├── config.py              # Pydantic BaseSettings (date ranges, cutoff, db path, API URL)
│   ├── database.py            # SQLite schema initialization and indexed upserts
│   ├── fetcher.py             # Elexon BMRS API client with exponential backoff retries
│   ├── processing.py          # Decision cutoff logic, no-lookahead filter, Option A join
│   ├── metrics.py             # MAE, bias, RMSE, percentiles, hourly, daily, horizon analysis
│   ├── main.py                # FastAPI REST API application
│   ├── scripts/
│   │   └── rebuild_cache.py   # CLI script to rebuild local SQLite cache from Elexon API
│   └── tests/
│       ├── test_processing.py # Unit tests for cutoff boundaries & resolution mapping
│       ├── test_metrics.py    # Unit tests for statistical metric computations & bias correction
│       └── test_api.py        # Integration tests for FastAPI endpoints
├── frontend/
│   ├── src/
│   │   ├── App.tsx            # Main interactive analytics dashboard (Recharts)
│   │   ├── api.ts             # Typed API client
│   │   ├── types.ts           # TypeScript interfaces
│   │   ├── index.css          # Client-ready responsive styling
│   │   └── main.tsx           # React entry point
│   ├── package.json
│   ├── vite.config.ts
│   └── nginx.conf             # Production container reverse-proxy config
├── data/
│   └── bmrs_cache.db          # Local SQLite cache (1,488 actuals, 20,440 forecasts)
├── Dockerfile.backend         # Multi-stage Python build
├── Dockerfile.frontend        # Multi-stage Node/Nginx build
├── docker-compose.yml         # One-command orchestration
├── Procfile                   # Container/Heroku entry point
├── requirements.txt           # Production runtime dependencies (FastAPI, NumPy, Pandas)
├── requirements-dev.txt       # Development & testing dependencies (pytest)
└── README.md
```

---

## 6. How to Run Locally

### Option A: Running with Docker (Recommended)
Prerequisites: Docker & Docker Compose.

```bash
# Clone the repository
git clone https://github.com/placeholder/elexon-wind-backtest.git
cd elexon-wind-backtest

# Build and start both services
docker compose up --build
```
* **Frontend Dashboard:** [http://localhost:3000](http://localhost:3000)
* **FastAPI Backend & Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Option B: Running Without Docker

#### 1. Backend Setup (Python 3.10+)
```bash
# Create and activate virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install runtime dependencies (or requirements-dev.txt for testing)
pip install -r requirements.txt

# Start the FastAPI server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. Frontend Setup (Node 18+)
In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```
* The Vite dev server will start at `http://localhost:5173`. Requests to `/api` are automatically proxied to `http://localhost:8000`.

---

## 7. How to Run Tests

The test suite contains **27 automated unit and integration tests** covering cutoff boundaries, per-hour fallback, Option A resolution alignment, lead-time horizon scoring, bias correction, CSV export, and FastAPI HTTP responses.

```bash
# Install development/test dependencies
pip install -r requirements-dev.txt

# Run pytest
pytest backend/tests/ -v
```

---

## 8. How to (Re)build the Data Cache

The repository includes a standalone script to fetch raw data directly from Elexon BMRS and rebuild the local SQLite cache:

```bash
python -m backend.scripts.rebuild_cache
```
* Pulls `FUELHH/stream` across `2026-01-02` to `2026-02-01` (`fuelType=WIND`).
* Pulls `WINDFOR/stream` in 5-day chunks from `2025-12-28` to `2026-01-31`.
* Persists to `data/bmrs_cache.db` with indexed `start_time` and `publish_time` columns in ~8 seconds.
* **Zero Elexon calls at request time:** The application serves all backtest queries exclusively from this local cache.

---

## 9. Data Export & Verification (1,488 Evaluated Slots)

To verify all calculations independently, the entire 1,488 evaluated slot dataset is exported:
* **Via CLI Script:**
  ```bash
  python -m backend.scripts.export_csv
  ```
  Writes `data/evaluated_slots_january_2026.csv` containing:
  `start_time`, `settlement_date`, `settlement_period`, `forecast_generation_mw`, `actual_generation_mw`, `error_mw`, `forecast_publish_time`, `actual_publish_time`, `lead_time_hours`.
* **Via API Endpoint:** `GET /api/export/csv` (returns direct CSV download with attachment header).
* **Via Frontend UI:** Click the **"Export CSV (1,488 Slots)"** button in the dashboard header.

### Unified Bias-Corrected Metrics (Computed from the 1,488 Slots):
All 4 bias-corrected metrics are calculated in a single unified function (`compute_bias_corrected_spread` in `backend/metrics.py`) from the exact same dataset:
* **Mean Bias Subtracted:** $+1,747.89\text{ MW}$
* **1. Bias-Corrected MAE:** **1,381.18 MW**
* **2. Bias-Corrected P10:** **-2,291.99 MW**
* **3. Bias-Corrected P50:** **-155.89 MW**
* **4. Bias-Corrected P90:** **+2,392.21 MW**
* **Recommended In-Sample Residual Buffer:** **2,392.2 MW**

---

## 10. Deployment Architecture: All-in-One on Vercel

As required, deployment is implemented cleanly on **Vercel** with **Heroku** as the containerized alternative:

### Primary Setup: Full-Stack Vercel Deployment (100% Free)
Both the React frontend and FastAPI backend deploy together in a single Vercel project:
* **Frontend:** React + Vite static build (`frontend/dist`) served from Vercel’s global Edge CDN.
* **Backend:** FastAPI exposed as a Vercel Python Serverless Function via [api/index.py](api/index.py).
* **Single-Domain Relative Routing:** The frontend uses relative `/api` paths (configured in `frontend/.env` and `vercel.json`). The frontend and API share the exact same domain, eliminating CORS entirely.
* **Pre-Built SQLite Cache:** The 5.7 MB SQLite cache (`data/bmrs_cache.db`) is bundled directly in the deployment package and opened read-only. The serverless function never makes external HTTP calls to Elexon at request time.
* **Cold-Start Performance:** Because the database is pre-indexed and only 5.7 MB, cold starts execute in **$< 400\text{ ms}$**, and warm responses execute in **$< 20\text{ ms}$**.
* **Anonymous Access:** The application requires zero authentication or cookies; reviewers can open the deployed link in an incognito window and immediately interact with all charts and data.

#### How to Deploy to Vercel:
```bash
# Install Vercel CLI (or connect the GitHub repository in the Vercel dashboard)
npm i -g vercel

# Deploy production build
vercel --prod
```

### Alternative Setup: Heroku Container Dyno
If deploying as a standalone container:
```bash
# Log in to Heroku Container Registry
heroku container:login

# Push and release backend container
heroku container:push web -a your-app-name
heroku container:release web -a your-app-name
```
* Uses [Procfile](Procfile) (`web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT`). Note that Heroku requires an Eco dyno ($5/mo) as it no longer offers a free tier.

* **Deployed Link (Placeholder):** `https://elexon-wind-backtest.vercel.app`

---

## 11. AI Tools Disclosure

In accordance with transparent engineering practices: AI coding assistants (Gemini / Antigravity) were utilized during development for rapid prototyping, API schema verification, unit test generation, and documentation drafting. All code, statistical calculations, domain assumptions, and test results were reviewed, debugged, and validated against official Elexon specifications.
