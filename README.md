# Elexon BMRS Wind Forecast vs. Actual Outturn Backtest

Live app: https://zphyr7.vercel.app | Repo: https://github.com/AkshathK05/zphyr7

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
├── .gitignore                         # Git exclusion rules (whitelists data/bmrs_cache.db)
├── Dockerfile.backend                 # Python 3.11 container build
├── Dockerfile.frontend                # Vite build + Nginx container
├── Procfile                           # Heroku process definition
├── README.md                          # Project documentation
├── requirements.txt                   # Lean production dependencies (FastAPI, NumPy, Pandas)
├── requirements-dev.txt               # Testing dependencies (pytest, httpx)
├── vercel.json                        # Vercel services mode routing and service configuration
├── docker-compose.yml                 # Local multi-container orchestration
├── api/
│   └── index.py                       # Vercel entrypoint importing FastAPI app from backend.main
├── backend/
│   ├── __init__.py
│   ├── config.py                      # Pydantic BaseSettings (date ranges, cutoff, db path, API URL)
│   ├── database.py                    # SQLite schema initialization and indexed upserts
│   ├── fetcher.py                     # Elexon BMRS API client with exponential backoff retries
│   ├── main.py                        # FastAPI REST API application
│   ├── metrics.py                     # MAE, bias, RMSE, percentiles, hourly, daily, horizon analysis
│   ├── processing.py                  # Decision cutoff logic, no-lookahead filter, Option A join
│   ├── scripts/
│   │   ├── __init__.py
│   │   ├── export_csv.py              # CLI script exporting all 1,488 evaluated slots to CSV
│   │   └── rebuild_cache.py           # CLI script to rebuild local SQLite cache from Elexon API
│   └── tests/
│       ├── __init__.py
│       ├── test_api.py                # Integration tests for FastAPI endpoints
│       ├── test_metrics.py            # Unit tests for statistical metric computations & bias correction
│       └── test_processing.py         # Unit tests for cutoff boundaries & resolution mapping
├── data/
│   ├── bmrs_cache.db                  # Local SQLite cache (1,488 actuals, 20,440 forecasts)
│   └── evaluated_slots_january_2026.csv # Full CSV export of 1,488 evaluated backtest slots
└── frontend/
    ├── .env                           # Frontend environment configuration (VITE_API_BASE_URL=/api)
    ├── .env.example
    ├── index.html
    ├── nginx.conf                     # Nginx reverse-proxy configuration for Docker
    ├── package.json
    ├── package-lock.json
    ├── tsconfig.json
    ├── tsconfig.node.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx                    # Main interactive analytics dashboard (Recharts)
        ├── api.ts                     # Typed API client
        ├── index.css                  # Responsive styling
        ├── main.tsx                   # React entry point
        ├── types.ts                   # TypeScript interfaces
        └── vite-env.d.ts              # Vite client type definitions
```

---

## 6. How to Run Locally

### Run with Docker (Recommended)
Prerequisites: Docker & Docker Compose.

```bash
# Clone the repository
git clone https://github.com/AkshathK05/zphyr7.git
cd zphyr7

# Build and start both services
docker compose up --build
```
* **Frontend Dashboard:** [http://localhost:3000](http://localhost:3000)
* **FastAPI Backend & Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Run without Docker

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

## 10. Deployment Architecture: Vercel Services Mode

The application is deployed on **Vercel** using **Vercel services mode** (`vercel.json`), orchestrating both services under a single domain:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "services": {
    "api": {
      "root": ".",
      "framework": "fastapi",
      "entrypoint": "api/index.py"
    },
    "frontend": {
      "root": "frontend",
      "framework": "vite",
      "devCommand": "npx vite"
    }
  },
  "rewrites": [
    { "source": "/api/(.*)", "destination": { "service": "api" } },
    { "source": "/(.*)", "destination": { "service": "frontend" } }
  ]
}
```

* **Frontend Service:** React + Vite served from `frontend` at `/`.
* **API Service:** FastAPI exposed via `api/index.py` at `/api`.
* **Path Preservation & Routing:** In Vercel services mode, rewrites route incoming `/api/...` requests to the `api` service with the `/api` prefix preserved. FastAPI mounts its routes directly with `prefix="/api"` (`app.include_router(router, prefix="/api")`), eliminating any duplicate root routing.
* **Pre-Built SQLite Cache:** The 5.7 MB SQLite cache (`data/bmrs_cache.db`) is bundled directly in the deployed repository and opened read-only. The serverless function never makes external HTTP calls to Elexon at request time.
* **Anonymous Access:** The application requires zero authentication or cookies; reviewers can open the deployed link in an incognito window and immediately interact with all charts and data.

### Alternative Setup: Heroku
Heroku is a possible alternative but would need frontend serving added; the app is deployed on Vercel.

* **Deployed Link:** https://zphyr7.vercel.app

---

## 11. Limitations & Next Steps

### Current Limitations:
1. **Single-Month In-Sample Evaluation:** The backtest covers 31 days (January 2026). While 1,488 half-hour slots provide high statistical power for that month, winter wind patterns and grid constraint conditions differ significantly from summer regimes.
2. **09:00 UTC Cutoff Assumption:** The morning decision cutoff is assumed to be 09:00 UTC (configurable via query parameter or `.env`), reflecting typical day-ahead bidding prep; desks with earlier or later cutoffs will see slightly different lead times and forecast availability.
3. **Curtailment Hypothesis Unverified:** The persistent positive bias (+1,747.9 MW) is hypothesized to stem from operational curtailment (NESO bid-offer acceptances turning down wind generators behind transmission constraints). Validating or disproving this requires granular Balancing Mechanism (BOA) data, which was out of scope for this backtest.

### Next Steps for Production:
1. **Multi-Year / Seasonal Backtesting:** Expand the cache to ingest a full 12–24 months of BMRS data to test buffer sizing across seasonal wind variability.
2. **Live / Rolling Operational Mode:** Deploy a lightweight scheduled worker that polls BMRS at 08:30 UTC daily, selects the morning forecasts, and provides live trade sizing recommendations for Day D.
3. **Out-of-Sample Dynamic Bias Correction:** Replace the in-sample mean bias subtraction with an out-of-sample rolling filter (e.g. 7-day or 14-day exponential moving average bias) to produce actionable, predictive residual buffers for live trading.

---

## AI Tools Disclosure

AI tools were used during development:

- **Gemini (Antigravity)**: code generation for the backend, frontend,
  tests, Docker/Vercel configuration and documentation drafts.
- **Claude**: design review and domain guidance, including the decision
  cutoff approach, half-hour alignment choice, metric selection, and
  reviewing generated output for errors (e.g. correcting an unsupported
  claim about embedded wind in an earlier draft).

Human verification:

- Forecast, actual and error values for sample slots (e.g. 27 Jan 2026)
  were checked manually against the raw Elexon API responses.
- Forecast selection was confirmed to use the latest publish time before
  the 09:00 UTC cutoff (no later runs existed in the window).
- Summary statistics were cross-checked for internal consistency
  (e.g. bias-corrected MAE against RMSE and bias).
- All design decisions documented above were reviewed and chosen by me.
