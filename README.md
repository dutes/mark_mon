# Market Divergence & Exposure Monitor

A clean, understated weekend PoC web app that pulls public odds, computes market consensus (median), simulates "our book" prices, detects price isolation (divergence) using implied probability edge, and estimates directional exposure.

## Quick Start (local)

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000).

## Docker

### Run with Docker directly

```bash
docker build -t market-divergence-exposure-monitor .
docker run -p 8000:8000 market-divergence-exposure-monitor
```

### Run with Docker Compose

```bash
docker-compose up --build
```

### Using the live odds API (optional)

Copy `.env.example` to `.env` and edit the values:

```bash
cp .env.example .env
```

Then open `.env` and set:

```
ODDS_PROVIDER=oddsapi
ODDSAPI_KEY=your_key_here
```

Finally run:

```bash
docker-compose up --build
```

**Linux / macOS** — you can also pass variables inline:

```bash
ODDS_PROVIDER=oddsapi ODDSAPI_KEY=your_key_here docker-compose up --build
```

**Windows PowerShell** — use the `.env` file approach above, or set variables before the command:

```powershell
$env:ODDS_PROVIDER="oddsapi"; $env:ODDSAPI_KEY="your_key_here"; docker-compose up --build
```

**Windows CMD**:

```cmd
set ODDS_PROVIDER=oddsapi && set ODDSAPI_KEY=your_key_here && docker-compose up --build
```

Without `ODDSAPI_KEY`, the app automatically uses the built-in mock provider.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ODDS_PROVIDER` | `mock` | `mock` or `oddsapi` |
| `ODDSAPI_KEY` | *(empty)* | API key for [the-odds-api.com](https://the-odds-api.com/) |
| `POLL_INTERVAL_SECONDS` | `60` | Background refresh interval |

## Project Structure

```
app.py                      FastAPI application + routes + background poller
adapters/
  mock_provider.py          Embedded sample data (8 soccer events, always works)
  odds_api_provider.py      Live adapter for the-odds-api.com
services/
  detector.py               Consensus, divergence, severity, exposure computation
  simulation.py             4 simulation modes for "our book" prices
templates/
  outliers.html             Main dashboard
  event.html                Event detail page
static/
  styles.css                Clean, minimal styles
requirements.txt
Dockerfile
docker-compose.yml
```

## Simulation Modes

| Mode | Description |
|---|---|
| **No Simulation** | `our_odds = median` — no artificial outliers |
| **Bias Mode** | Shade favourites +1% (odds < 2.0 get a slight increase) |
| **Latency Mode** | Stale prices — use previous polling cycle's median |
| **Manual Mistake** | One random selection gets +0.15 odds per cycle |

## Dashboard

- Filters: severity (amber+red / red only / all), league, time window
- Controls: simulation mode, max stake, expected sharp bets, hit rate
- Export: CSV download of current outliers
- Severity bands: 🟢 green `< 1%`, 🟡 amber `1–2%`, 🔴 red `≥ 2%` implied probability edge

## Routes

| Route | Description |
|---|---|
| `GET /` | Redirect to `/outliers` |
| `GET /outliers` | Main dashboard |
| `GET /event/{id}` | Event detail page |
| `GET /api/outliers` | JSON outlier data |
| `GET /export.csv` | CSV export |
| `GET /health` | Health / status JSON |