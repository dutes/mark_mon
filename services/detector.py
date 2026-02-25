"""
detector.py — consensus computation, divergence detection, and exposure estimation.
"""

from __future__ import annotations

import statistics
from typing import List, Dict, Any, Optional


SEVERITY_GREEN = "green"
SEVERITY_AMBER = "amber"
SEVERITY_RED = "red"

EDGE_AMBER_THRESHOLD = 0.01
EDGE_RED_THRESHOLD = 0.02


def _implied_prob(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability."""
    if decimal_odds <= 1.0:
        return 1.0
    return 1.0 / decimal_odds


def _severity(edge: float) -> str:
    abs_edge = abs(edge)
    if abs_edge >= EDGE_RED_THRESHOLD:
        return SEVERITY_RED
    if abs_edge >= EDGE_AMBER_THRESHOLD:
        return SEVERITY_AMBER
    return SEVERITY_GREEN


def _compute_exposure(
    our_odds: float,
    market_median_odds: float,
    max_stake: float,
    expected_sharp_bets: int,
    assumed_hit_rate: float,
) -> float:
    """
    cost_per_bet ≈ max_stake * max(0, (our_odds - market_median_odds)) / our_odds
    estimated_exposure = cost_per_bet * expected_sharp_bets * assumed_hit_rate
    """
    if our_odds <= 1.0:
        return 0.0
    cost_per_bet = max_stake * max(0.0, (our_odds - market_median_odds)) / our_odds
    return cost_per_bet * expected_sharp_bets * assumed_hit_rate


def compute_outliers(
    events: List[Dict[str, Any]],
    quotes_by_event: Dict[str, List[Dict[str, Any]]],
    our_odds_by_event: Dict[str, Dict[str, float]],
    max_stake: float = 500.0,
    expected_sharp_bets: int = 10,
    assumed_hit_rate: float = 0.55,
) -> List[Dict[str, Any]]:
    """
    For every event × selection compute consensus, divergence, severity, exposure.
    Returns a flat list of outlier dicts sorted by severity desc then edge desc.
    """
    results = []
    severity_order = {SEVERITY_RED: 0, SEVERITY_AMBER: 1, SEVERITY_GREEN: 2}

    for event in events:
        event_id = event["id"]
        quotes = quotes_by_event.get(event_id, [])
        if not quotes:
            continue

        our_odds_map = our_odds_by_event.get(event_id, {})

        # Group odds by selection
        by_selection: Dict[str, List[float]] = {}
        by_selection_bookmakers: Dict[str, List[Dict[str, Any]]] = {}
        for q in quotes:
            sel = q["selection_key"]
            odds = float(q["decimal_odds"])
            if odds > 1.0:
                by_selection.setdefault(sel, []).append(odds)
                by_selection_bookmakers.setdefault(sel, []).append(q)

        for sel, odds_list in by_selection.items():
            if len(odds_list) < 2:
                continue
            median_odds = statistics.median(odds_list)
            our_odds = our_odds_map.get(sel, median_odds)

            p_market = _implied_prob(median_odds)
            p_ours = _implied_prob(our_odds)
            edge = p_market - p_ours  # positive = we're offering too much value

            severity = _severity(edge)
            exposure = _compute_exposure(
                our_odds, median_odds, max_stake, expected_sharp_bets, assumed_hit_rate
            )

            results.append(
                {
                    "event_id": event_id,
                    "sport": event.get("sport", ""),
                    "league": event.get("league", ""),
                    "start_time_utc": event.get("start_time_utc", ""),
                    "home_team": event.get("home_team", ""),
                    "away_team": event.get("away_team", ""),
                    "event_name": f"{event.get('home_team','')} vs {event.get('away_team','')}" if event.get('away_team') else event.get('home_team', ''),
                    "selection_key": sel,
                    "market_median_odds": round(median_odds, 3),
                    "our_odds": round(our_odds, 3),
                    "edge": round(edge, 5),
                    "edge_pct": round(edge * 100, 2),
                    "severity": severity,
                    "exposure": round(exposure, 2),
                    "bookmaker_count": len(odds_list),
                }
            )

    results.sort(key=lambda r: (severity_order[r["severity"]], -abs(r["edge"])))
    return results


def compute_event_detail(
    event: Dict[str, Any],
    quotes: List[Dict[str, Any]],
    our_odds_map: Dict[str, float],
    history: List[Dict[str, Any]],
    max_stake: float = 500.0,
    expected_sharp_bets: int = 10,
    assumed_hit_rate: float = 0.55,
) -> Dict[str, Any]:
    """
    Return rich detail for a single event page.
    """
    by_selection: Dict[str, List[Dict[str, Any]]] = {}
    for q in quotes:
        sel = q["selection_key"]
        if float(q["decimal_odds"]) > 1.0:
            by_selection.setdefault(sel, []).append(q)

    selections_detail = []
    for sel in by_selection:
        sel_quotes = by_selection.get(sel, [])
        if not sel_quotes:
            continue
        odds_list = [float(q["decimal_odds"]) for q in sel_quotes]
        median_odds = statistics.median(odds_list)
        our_odds = our_odds_map.get(sel, median_odds)
        p_market = _implied_prob(median_odds)
        p_ours = _implied_prob(our_odds)
        edge = p_market - p_ours
        severity = _severity(edge)
        exposure = _compute_exposure(
            our_odds, median_odds, max_stake, expected_sharp_bets, assumed_hit_rate
        )

        bookmakers = sorted(sel_quotes, key=lambda q: float(q["decimal_odds"]))
        selections_detail.append(
            {
                "selection_key": sel,
                "market_median_odds": round(median_odds, 3),
                "our_odds": round(our_odds, 3),
                "edge_pct": round(edge * 100, 2),
                "severity": severity,
                "exposure": round(exposure, 2),
                "bookmakers": bookmakers,
            }
        )

    return {
        "event": event,
        "event_name": f"{event.get('home_team','')} vs {event.get('away_team','')}" if event.get('away_team') else event.get('home_team', ''),
        "selections": selections_detail,
        "history": history,
    }
