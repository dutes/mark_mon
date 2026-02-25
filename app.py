"""
app.py — Betfair Market Intelligence
FastAPI + Jinja2 server-rendered dashboard.
Betfair's own prices are used as the primary reference; all other bookmakers
form the competitor market used for consensus / divergence computation.
"""

from __future__ import annotations

import csv
import io
import logging
import os
from collections import deque
from datetime import datetime, timezone, timedelta
from typing import Any, Deque, Dict, List, Optional

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from adapters.mock_provider import MockOddsProvider
from adapters.odds_api_provider import OddsApiProvider
from services.detector import compute_outliers, compute_event_detail
from services.simulation import apply_simulation, compute_medians, MODES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
ODDS_PROVIDER_ENV = os.getenv("ODDS_PROVIDER", "mock").lower()
ODDSAPI_KEY = os.getenv("ODDSAPI_KEY", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY_SNAPSHOTS", "30"))

# The bookmaker name that represents Betfair in the quotes data
BETFAIR_BOOKMAKER = "betfair"

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------
store: Dict[str, Any] = {
    "events": [],
    "quotes_by_event": {},           # event_id -> list of OddsQuote dicts (all bookmakers)
    "market_quotes_by_event": {},    # event_id -> list of OddsQuote dicts (competitors only, no Betfair)
    "current_medians": {},           # event_id -> {sel -> median_odds} (competitor market)
    "previous_medians": None,        # previous cycle medians (for latency mode)
    "our_odds": {},                  # event_id -> {sel -> our_odds}  (Betfair prices)
    "outliers": [],                  # latest computed outlier rows
    "history": {},                   # (event_id, sel) -> deque of {cycle, median_odds, our_odds, ts}
    "last_poll_utc": None,
    "events_scanned": 0,
    "cycle": 0,
    "sim_mode": "manual",        # default simulation mode (fallback when Betfair data absent)
    "provider_name": "",
    "betfair_available": False,  # True when live Betfair quotes were found
    "use_simulated": False,      # True = ignore live Betfair data, use simulation only
    # Exposure params (defaults)
    "max_stake": 500.0,
    "expected_sharp_bets": 10,
    "assumed_hit_rate": 0.55,
}


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------
def _build_provider():
    if ODDS_PROVIDER_ENV == "oddsapi" and ODDSAPI_KEY:
        provider = OddsApiProvider()
        if provider.available:
            logger.info("Using OddsApiProvider")
            return provider
        logger.warning("OddsApiProvider not available — falling back to MockOddsProvider")
    logger.info("Using MockOddsProvider")
    return MockOddsProvider()


provider = _build_provider()
store["provider_name"] = provider.name


# ---------------------------------------------------------------------------
# Betfair odds extraction
# ---------------------------------------------------------------------------
def _extract_betfair_odds(
    events: List[Dict[str, Any]],
    quotes_by_event: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, float]]:
    """
    Pull Betfair's quoted prices out of the raw quotes and return them as
    our_odds_by_event {event_id -> {selection_key -> decimal_odds}}.
    """
    result: Dict[str, Dict[str, float]] = {}
    for event in events:
        eid = event["id"]
        betfair_qs = [
            q for q in quotes_by_event.get(eid, [])
            if q.get("bookmaker", "").lower() == BETFAIR_BOOKMAKER
        ]
        if betfair_qs:
            result[eid] = {q["selection_key"]: float(q["decimal_odds"]) for q in betfair_qs}
    return result


# ---------------------------------------------------------------------------
# Poll logic
# ---------------------------------------------------------------------------
def run_poll() -> None:
    """Fetch odds, update store, recompute outliers."""
    try:
        events = provider.get_events()
        quotes_by_event: Dict[str, List[Dict]] = {}
        for event in events:
            quotes_by_event[event["id"]] = provider.get_odds(event["id"])

        # Separate Betfair quotes from the competitor market
        market_quotes_by_event: Dict[str, List[Dict]] = {
            eid: [q for q in qs if q.get("bookmaker", "").lower() != BETFAIR_BOOKMAKER]
            for eid, qs in quotes_by_event.items()
        }

        # Market consensus is computed from competitor bookmakers only
        current_medians = compute_medians(events, market_quotes_by_event)

        cycle = store["cycle"]
        sim_mode = store["sim_mode"]

        # Use Betfair's own prices as the primary reference ("our odds").
        # Fall back to simulation for any events/selections without Betfair data.
        betfair_odds = _extract_betfair_odds(events, quotes_by_event)
        betfair_available = bool(betfair_odds)

        sim_odds = apply_simulation(
            mode=sim_mode,
            events=events,
            current_medians=current_medians,
            previous_medians=store["previous_medians"],
            cycle=cycle,
        )
        our_odds: Dict[str, Dict[str, float]] = {}
        for event in events:
            eid = event["id"]
            if store.get("use_simulated"):
                # Simulated mode: ignore live Betfair data entirely
                our_odds[eid] = dict(sim_odds.get(eid, {}))
            else:
                # Live mode: Betfair prices take priority; simulation fills any gaps
                our_odds[eid] = {**sim_odds.get(eid, {}), **betfair_odds.get(eid, {})}

        outliers = compute_outliers(
            events=events,
            quotes_by_event=market_quotes_by_event,  # compare against competitor market only
            our_odds_by_event=our_odds,
            max_stake=store["max_stake"],
            expected_sharp_bets=store["expected_sharp_bets"],
            assumed_hit_rate=store["assumed_hit_rate"],
        )

        # Update history
        ts = datetime.now(timezone.utc).isoformat()
        for row in outliers:
            key = (row["event_id"], row["selection_key"])
            if key not in store["history"]:
                store["history"][key] = deque(maxlen=MAX_HISTORY)
            store["history"][key].append(
                {
                    "cycle": cycle,
                    "timestamp_utc": ts,
                    "market_median_odds": row["market_median_odds"],
                    "our_odds": row["our_odds"],
                    "edge_pct": row["edge_pct"],
                    "severity": row["severity"],
                }
            )

        # Also ensure history exists for all event+selection combos
        for eid, sel_map in our_odds.items():
            for sel, o_odds in sel_map.items():
                med = current_medians.get(eid, {}).get(sel, o_odds)
                key = (eid, sel)
                if key not in store["history"]:
                    store["history"][key] = deque(maxlen=MAX_HISTORY)

        # Persist
        store["previous_medians"] = current_medians
        store["current_medians"] = current_medians
        store["events"] = events
        store["quotes_by_event"] = quotes_by_event
        store["market_quotes_by_event"] = market_quotes_by_event  # competitor-only quotes
        store["our_odds"] = our_odds
        store["outliers"] = outliers
        store["betfair_available"] = betfair_available
        store["last_poll_utc"] = datetime.now(timezone.utc).isoformat()
        store["events_scanned"] = len(events)
        store["cycle"] += 1

        logger.info("Poll #%d complete — %d events, %d outliers", cycle, len(events), len(outliers))
    except Exception as exc:
        logger.error("Poll error: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------
async def background_poller():
    while True:
        run_poll()
        await asyncio.sleep(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run initial poll synchronously so data is ready on first request
    run_poll()
    task = asyncio.create_task(background_poller())
    yield
    task.cancel()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Betfair Market Intelligence", lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Jinja2 helpers
def _severity_class(severity: str) -> str:
    return {"red": "sev-red", "amber": "sev-amber", "green": "sev-green"}.get(severity, "")

templates.env.globals["severity_class"] = _severity_class


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/outliers")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "last_poll_utc": store["last_poll_utc"],
        "events_scanned": store["events_scanned"],
        "provider": store["provider_name"],
        "betfair_available": store["betfair_available"],
        "sim_mode": store["sim_mode"],
        "cycle": store["cycle"],
    }


@app.get("/api/outliers")
async def api_outliers(
    severity: str = Query("amber", description="all|green|amber|red"),
    sport: str = Query("", description="Filter by sport"),
    league: str = Query("", description="Filter by league name"),
    hours: int = Query(24, description="Next N hours"),
):
    rows = _filter_outliers(severity, sport, league, hours)
    return rows


@app.get("/outliers", response_class=HTMLResponse)
async def outliers_page(
    request: Request,
    severity: str = Query("amber", description="all|green|amber|red"),
    sport: str = Query("", description="Filter by sport"),
    league: str = Query("", description="Filter by league"),
    hours: int = Query(24, description="Next N hours"),
    sim_mode: str = Query("", description="Simulation mode"),
    use_simulated: int = Query(-1, description="0=live Betfair, 1=simulated"),
    max_stake: float = Query(0.0),
    expected_sharp_bets: int = Query(0),
    assumed_hit_rate: float = Query(0.0),
):
    # Apply param overrides
    if use_simulated != -1 and bool(use_simulated) != store["use_simulated"]:
        store["use_simulated"] = bool(use_simulated)
        run_poll()
    if sim_mode and sim_mode in MODES:
        store["sim_mode"] = sim_mode
        run_poll()
    if max_stake > 0:
        store["max_stake"] = max_stake
        run_poll()
    if expected_sharp_bets > 0:
        store["expected_sharp_bets"] = expected_sharp_bets
        run_poll()
    if 0 < assumed_hit_rate <= 1.0:
        store["assumed_hit_rate"] = assumed_hit_rate
        run_poll()

    rows = _filter_outliers(severity, sport, league, hours)
    sports = sorted({e.get("sport", "") for e in store["events"] if e.get("sport")})
    # Leagues filtered by selected sport (or all if no sport selected)
    leagues = sorted({
        e.get("league", "") for e in store["events"]
        if not sport or e.get("sport", "") == sport
    })

    return templates.TemplateResponse(
        "outliers.html",
        {
            "request": request,
            "rows": rows,
            "severity_filter": severity,
            "sport_filter": sport,
            "league_filter": league,
            "hours_filter": hours,
            "sports": sports,
            "leagues": leagues,
            "sim_mode": store["sim_mode"],
            "sim_modes": MODES,
            "max_stake": store["max_stake"],
            "expected_sharp_bets": store["expected_sharp_bets"],
            "assumed_hit_rate": store["assumed_hit_rate"],
            "last_poll_utc": store["last_poll_utc"],
            "provider_name": store["provider_name"],
            "events_scanned": store["events_scanned"],
            "betfair_available": store["betfair_available"],
            "use_simulated": store["use_simulated"],
        },
    )


@app.get("/event/{event_id}", response_class=HTMLResponse)
async def event_detail(
    request: Request,
    event_id: str,
):
    event = next((e for e in store["events"] if e["id"] == event_id), None)
    if not event:
        return HTMLResponse(content="<h1>Event not found</h1>", status_code=404)

    # Use competitor-only quotes for market stats; Betfair is shown separately
    market_quotes = store["market_quotes_by_event"].get(event_id, [])
    our_odds_map = store["our_odds"].get(event_id, {})

    # Collect history for this event — use all known selection keys
    all_quotes = store["quotes_by_event"].get(event_id, [])
    sel_keys = list({q["selection_key"] for q in all_quotes}) or list(our_odds_map.keys())
    history_by_sel: Dict[str, List] = {}
    for sel in sel_keys:
        key = (event_id, sel)
        history_by_sel[sel] = list(store["history"].get(key, []))

    detail = compute_event_detail(
        event=event,
        quotes=market_quotes,
        our_odds_map=our_odds_map,
        history=history_by_sel,
        max_stake=store["max_stake"],
        expected_sharp_bets=store["expected_sharp_bets"],
        assumed_hit_rate=store["assumed_hit_rate"],
    )

    return templates.TemplateResponse(
        "event.html",
        {
            "request": request,
            **detail,
            "last_poll_utc": store["last_poll_utc"],
            "provider_name": store["provider_name"],
            "betfair_available": store["betfair_available"],
        },
    )


@app.get("/export.csv")
async def export_csv(
    severity: str = Query("amber"),
    sport: str = Query(""),
    league: str = Query(""),
    hours: int = Query(24),
):
    rows = _filter_outliers(severity, sport, league, hours)
    output = io.StringIO()
    fieldnames = [
        "start_time_utc", "league", "event_name", "selection_key",
        "market_median_odds", "our_odds", "edge_pct", "severity", "exposure",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=outliers.csv"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _filter_outliers(severity: str, sport: str, league: str, hours: int) -> List[Dict[str, Any]]:
    rows = store["outliers"]
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours)

    filtered = []
    for row in rows:
        # Severity filter
        if severity != "all":
            if severity == "amber":
                if row["severity"] not in ("amber", "red"):
                    continue
            elif row["severity"] != severity:
                continue

        # Sport filter
        if sport and row.get("sport", "").lower() != sport.lower():
            continue

        # League filter
        if league and row.get("league", "").lower() != league.lower():
            continue

        # Time window filter
        try:
            start = datetime.fromisoformat(row["start_time_utc"].replace("Z", "+00:00"))
            if start > cutoff:
                continue
        except Exception:
            pass

        filtered.append(row)

    return filtered
