"""
OddsApiProvider — live adapter using the-odds-api.com.
Requires ODDSAPI_KEY environment variable.
Falls back gracefully when not configured.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


class OddsApiProvider:
    """
    Adapter for https://the-odds-api.com/
    Fetches prematch soccer 1x2 (h2h) odds.
    """

    name = "OddsApiProvider"
    BASE_URL = "https://api.the-odds-api.com/v4"
    SPORT = "soccer"
    REGIONS = "eu"
    MARKETS = "h2h"

    def __init__(self) -> None:
        self._api_key: Optional[str] = os.getenv("ODDSAPI_KEY")
        if not self._api_key:
            logger.warning("OddsApiProvider: ODDSAPI_KEY not set — provider unavailable.")
        if not _HTTPX_AVAILABLE:
            logger.warning("OddsApiProvider: httpx not installed — provider unavailable.")
        self._events_cache: List[Dict[str, Any]] = []
        self._odds_cache: Dict[str, List[Dict[str, Any]]] = {}

    @property
    def available(self) -> bool:
        return bool(self._api_key) and _HTTPX_AVAILABLE

    def _fetch_sport_odds(self) -> List[Dict[str, Any]]:
        """Fetch all soccer events + h2h odds in one call."""
        if not self.available:
            return []
        url = f"{self.BASE_URL}/sports/soccer_epl/odds/"
        params = {
            "apiKey": self._api_key,
            "regions": self.REGIONS,
            "markets": self.MARKETS,
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.error("OddsApiProvider fetch error: %s", exc)
            return []

    def _parse_raw(self, raw_events: List[Dict[str, Any]]) -> None:
        """Parse API response into internal format."""
        self._events_cache = []
        self._odds_cache = {}
        now = datetime.now(timezone.utc).isoformat()

        for item in raw_events:
            event_id = item.get("id", "")
            event = {
                "id": event_id,
                "sport": "soccer",
                "league": item.get("sport_title", "Unknown"),
                "start_time_utc": item.get("commence_time", now),
                "home_team": item.get("home_team", "Home"),
                "away_team": item.get("away_team", "Away"),
            }
            self._events_cache.append(event)

            quotes: List[Dict[str, Any]] = []
            for bookmaker_data in item.get("bookmakers", []):
                bookmaker_name = bookmaker_data.get("key", "unknown")
                for market in bookmaker_data.get("markets", []):
                    if market.get("key") != "h2h":
                        continue
                    outcomes = market.get("outcomes", [])
                    home_team = item.get("home_team", "")
                    for outcome in outcomes:
                        name = outcome.get("name", "")
                        price = float(outcome.get("price", 0))
                        if price <= 1.0:
                            continue
                        if name == home_team:
                            sel = "home"
                        elif name == item.get("away_team", ""):
                            sel = "away"
                        else:
                            sel = "draw"
                        quotes.append(
                            {
                                "event_id": event_id,
                                "selection_key": sel,
                                "bookmaker": bookmaker_name,
                                "decimal_odds": price,
                                "timestamp_utc": now,
                            }
                        )
            self._odds_cache[event_id] = quotes

    def refresh(self) -> None:
        """Pull fresh data from the API and update cache."""
        raw = self._fetch_sport_odds()
        if raw:
            self._parse_raw(raw)

    def get_events(self) -> List[Dict[str, Any]]:
        if not self._events_cache:
            self.refresh()
        return list(self._events_cache)

    def get_odds(self, event_id: str) -> List[Dict[str, Any]]:
        if not self._odds_cache:
            self.refresh()
        return list(self._odds_cache.get(event_id, []))
