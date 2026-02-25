"""
MockOddsProvider — always-available adapter using embedded sample data.
Covers 8 soccer events across different leagues.
Start times are computed dynamically relative to now so events always fall
within the default 24-hour filter window.
"""

from __future__ import annotations

import copy  # noqa: F401 kept for potential direct use
from datetime import datetime, timezone, timedelta, timedelta
from typing import List, Dict, Any


def _make_events() -> List[Dict[str, Any]]:
    """Build event list with start times spread across the next 3–22 hours."""
    now = datetime.now(timezone.utc)

    templates = [
        ("mock_001", "soccer", "English Premier League", "Arsenal",          "Chelsea"),
        ("mock_002", "soccer", "English Premier League", "Manchester City",   "Liverpool"),
        ("mock_003", "soccer", "La Liga",                "Real Madrid",       "Barcelona"),
        ("mock_004", "soccer", "La Liga",                "Atletico Madrid",   "Sevilla"),
        ("mock_005", "soccer", "Bundesliga",             "Bayern Munich",     "Borussia Dortmund"),
        ("mock_006", "soccer", "Bundesliga",             "RB Leipzig",        "Bayer Leverkusen"),
        ("mock_007", "soccer", "Serie A",                "AC Milan",          "Juventus"),
        ("mock_008", "soccer", "Serie A",                "Inter Milan",       "Napoli"),
        ("mock_009", "rugby",  "Rugby Union Premiership","Sale Sharks",       "Harlequins"),
        ("mock_010", "rugby",  "Rugby Union Premiership","Bath Rugby",        "Exeter Chiefs"),
        ("mock_011", "rugby",  "NRL Rugby League",       "Sydney Roosters",   "Melbourne Storm"),
        ("mock_012", "rugby",  "NRL Rugby League",       "Brisbane Broncos",  "Penrith Panthers"),
    ]

    offsets_h = [2, 4, 6, 8, 10, 14, 18, 22, 3, 7, 11, 16]

    events = []
    for (eid, sport, league, home, away), offset_h in zip(templates, offsets_h):
        start = now + timedelta(hours=offset_h)
        # Round to nearest quarter-hour for cleaner display
        start = start.replace(minute=(start.minute // 15) * 15, second=0, microsecond=0)
        events.append(
            {
                "id": eid,
                "sport": sport,
                "league": league,
                "start_time_utc": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "home_team": home,
                "away_team": away,
            }
        )
    return events

# Bookmaker odds: list of (bookmaker_name, home_odds, draw_odds, away_odds)
_SAMPLE_ODDS: Dict[str, List[tuple]] = {
    "mock_001": [
        ("bet365",    2.10, 3.40, 3.60),
        ("betfair",   2.08, 3.45, 3.65),
        ("pinnacle",  2.12, 3.38, 3.58),
        ("unibet",    2.09, 3.42, 3.62),
        ("williamhill", 2.07, 3.44, 3.70),
        ("bwin",      2.11, 3.40, 3.60),
    ],
    "mock_002": [
        ("bet365",    1.72, 3.80, 4.75),
        ("betfair",   1.74, 3.85, 4.70),
        ("pinnacle",  1.73, 3.82, 4.80),
        ("unibet",    1.71, 3.80, 4.75),
        ("williamhill", 1.70, 3.90, 4.85),
        ("bwin",      1.72, 3.78, 4.72),
    ],
    "mock_003": [
        ("bet365",    2.25, 3.30, 3.20),
        ("betfair",   2.28, 3.28, 3.18),
        ("pinnacle",  2.26, 3.32, 3.22),
        ("unibet",    2.24, 3.30, 3.20),
        ("williamhill", 2.30, 3.25, 3.15),
        ("bwin",      2.27, 3.30, 3.20),
    ],
    "mock_004": [
        ("bet365",    1.85, 3.60, 4.20),
        ("betfair",   1.87, 3.58, 4.25),
        ("pinnacle",  1.86, 3.62, 4.18),
        ("unibet",    1.84, 3.60, 4.22),
        ("williamhill", 1.83, 3.65, 4.30),
        ("bwin",      1.85, 3.60, 4.20),
    ],
    "mock_005": [
        ("bet365",    1.55, 4.20, 6.00),
        ("betfair",   1.57, 4.18, 6.10),
        ("pinnacle",  1.56, 4.22, 5.95),
        ("unibet",    1.54, 4.20, 6.05),
        ("williamhill", 1.53, 4.25, 6.20),
        ("bwin",      1.56, 4.18, 6.00),
    ],
    "mock_006": [
        ("bet365",    2.40, 3.20, 2.95),
        ("betfair",   2.42, 3.22, 2.93),
        ("pinnacle",  2.41, 3.18, 2.97),
        ("unibet",    2.39, 3.20, 2.95),
        ("williamhill", 2.38, 3.25, 3.00),
        ("bwin",      2.41, 3.20, 2.95),
    ],
    "mock_007": [
        ("bet365",    2.15, 3.35, 3.50),
        ("betfair",   2.17, 3.33, 3.48),
        ("pinnacle",  2.16, 3.37, 3.52),
        ("unibet",    2.14, 3.35, 3.50),
        ("williamhill", 2.13, 3.40, 3.55),
        ("bwin",      2.16, 3.35, 3.50),
    ],
    "mock_008": [
        ("bet365",    1.95, 3.50, 3.95),
        ("betfair",   1.97, 3.48, 3.92),
        ("pinnacle",  1.96, 3.52, 3.98),
        ("unibet",    1.94, 3.50, 3.95),
        ("williamhill", 1.93, 3.55, 4.00),
        ("bwin",      1.95, 3.50, 3.95),
    ],
    # Rugby Union Premiership
    "mock_009": [
        ("bet365",    1.80, 0.0, 2.10),
        ("betfair",   1.82, 0.0, 2.08),
        ("pinnacle",  1.81, 0.0, 2.11),
        ("unibet",    1.79, 0.0, 2.12),
        ("williamhill", 1.78, 0.0, 2.15),
        ("bwin",      1.80, 0.0, 2.10),
    ],
    "mock_010": [
        ("bet365",    2.30, 0.0, 1.65),
        ("betfair",   2.32, 0.0, 1.63),
        ("pinnacle",  2.29, 0.0, 1.66),
        ("unibet",    2.28, 0.0, 1.67),
        ("williamhill", 2.35, 0.0, 1.62),
        ("bwin",      2.30, 0.0, 1.65),
    ],
    # NRL Rugby League
    "mock_011": [
        ("bet365",    1.65, 0.0, 2.30),
        ("betfair",   1.67, 0.0, 2.28),
        ("pinnacle",  1.66, 0.0, 2.32),
        ("unibet",    1.64, 0.0, 2.35),
        ("williamhill", 1.63, 0.0, 2.38),
        ("bwin",      1.65, 0.0, 2.30),
    ],
    "mock_012": [
        ("bet365",    1.90, 0.0, 1.95),
        ("betfair",   1.92, 0.0, 1.93),
        ("pinnacle",  1.91, 0.0, 1.96),
        ("unibet",    1.89, 0.0, 1.97),
        ("williamhill", 1.88, 0.0, 2.00),
        ("bwin",      1.90, 0.0, 1.95),
    ],
}


class MockOddsProvider:
    """Embedded mock odds provider — no API key required."""

    name = "MockOddsProvider"

    def get_events(self) -> List[Dict[str, Any]]:
        return _make_events()

    def get_odds(self, event_id: str) -> List[Dict[str, Any]]:
        """Return list of OddsQuote-like dicts for the given event."""
        raw = _SAMPLE_ODDS.get(event_id, [])
        now = datetime.now(timezone.utc).isoformat()
        quotes = []
        for bookmaker, home_odds, draw_odds, away_odds in raw:
            for selection_key, odds in [("home", home_odds), ("draw", draw_odds), ("away", away_odds)]:
                if odds <= 1.0:
                    continue
                quotes.append(
                    {
                        "event_id": event_id,
                        "selection_key": selection_key,
                        "bookmaker": bookmaker,
                        "decimal_odds": odds,
                        "timestamp_utc": now,
                    }
                )
        return quotes
