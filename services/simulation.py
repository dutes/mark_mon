"""
simulation.py — "Our Book" price simulation modes.

Modes:
  1) no_sim    — our_odds = median (no outliers)
  2) bias      — shade favourites +1% (increase odds slightly for favourites)
  3) latency   — stale price (use previous cycle's median odds)
  4) manual    — single selection bump (+0.15 on one random selection per cycle)

All modes use a seeded RNG for repeatable demo output.
"""

from __future__ import annotations

import random
import statistics
from typing import Dict, List, Any, Optional

MODES = {
    "no_sim": "No Simulation (median)",
    "bias": "Bias Mode (shade favourites +1%)",
    "latency": "Latency Mode (stale prices)",
    "manual": "Manual Mistake (single +0.15 bump)",
}

# Seed based on poll cycle number for determinism
_RNG_SEED_BASE = 42


def _get_rng(cycle: int) -> random.Random:
    return random.Random(_RNG_SEED_BASE + cycle)


def apply_simulation(
    mode: str,
    events: List[Dict[str, Any]],
    current_medians: Dict[str, Dict[str, float]],   # event_id -> {sel -> median}
    previous_medians: Optional[Dict[str, Dict[str, float]]],  # previous cycle
    cycle: int = 0,
) -> Dict[str, Dict[str, float]]:
    """
    Return our_odds_by_event: Dict[event_id, Dict[selection_key, our_odds]]
    """
    rng = _get_rng(cycle)

    if mode == "no_sim":
        return {eid: dict(sel_map) for eid, sel_map in current_medians.items()}

    elif mode == "bias":
        result: Dict[str, Dict[str, float]] = {}
        for eid, sel_map in current_medians.items():
            result[eid] = {}
            for sel, odds in sel_map.items():
                # Favourites have lower odds (< ~2.0); shade them up slightly
                if odds < 2.0:
                    result[eid][sel] = round(odds * 1.01, 3)
                else:
                    result[eid][sel] = odds
        return result

    elif mode == "latency":
        if not previous_medians:
            # No previous data yet — fall back to current
            return {eid: dict(sel_map) for eid, sel_map in current_medians.items()}
        result = {}
        for eid, sel_map in current_medians.items():
            if eid in previous_medians:
                result[eid] = dict(previous_medians[eid])
            else:
                result[eid] = dict(sel_map)
        return result

    elif mode == "manual":
        # Copy current medians, then pick one random (event, selection) and bump +0.15
        result = {eid: dict(sel_map) for eid, sel_map in current_medians.items()}
        all_keys = [
            (eid, sel)
            for eid, sel_map in result.items()
            for sel in sel_map
        ]
        if all_keys:
            chosen_eid, chosen_sel = rng.choice(all_keys)
            result[chosen_eid][chosen_sel] = round(result[chosen_eid][chosen_sel] + 0.15, 3)
        return result

    else:
        # Unknown mode — fallback to no_sim
        return {eid: dict(sel_map) for eid, sel_map in current_medians.items()}


def compute_medians(
    events: List[Dict[str, Any]],
    quotes_by_event: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Dict[str, float]]:
    """Helper: compute median odds per event+selection from quotes."""
    result: Dict[str, Dict[str, float]] = {}
    for event in events:
        eid = event["id"]
        quotes = quotes_by_event.get(eid, [])
        by_sel: Dict[str, List[float]] = {}
        for q in quotes:
            sel = q["selection_key"]
            odds = float(q["decimal_odds"])
            if odds > 1.0:
                by_sel.setdefault(sel, []).append(odds)
        result[eid] = {
            sel: statistics.median(odds_list)
            for sel, odds_list in by_sel.items()
            if odds_list
        }
    return result
