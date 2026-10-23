"""Point-in-time Order Flow Imbalance (OFI) and order-book feature engineering.

References:
    Cont, R., Kukanov, A., & Stoikov, S. (2014).
    The Price Impact of Order Book Events.
    Journal of Financial Econometrics, 12(1), 47-88.
    https://arxiv.org/abs/1011.6402
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from orderbook_ofi.models import BookSnapshot


def compute_l1_ofi(previous: BookSnapshot, current: BookSnapshot) -> float:
    """Compute Cont, Kukanov & Stoikov (2014) Level-1 Order Flow Imbalance.

    OFI measures net order flow entering or leaving the best bid and ask quotes:
    - Bid component:
        * If P_b(t) > P_b(t-1): price ticked up -> entire new bid size added (+q_b(t))
        * If P_b(t) < P_b(t-1): price ticked down -> old best bid consumed/cancelled (-q_b(t-1))
        * If P_b(t) == P_b(t-1): quantity change -> Delta q_b(t) = q_b(t) - q_b(t-1)
    - Ask component:
        * If P_a(t) < P_a(t-1): ask ticked down -> aggressive selling pushed ask down (-q_a(t))
        * If P_a(t) > P_a(t-1): ask ticked up -> old ask lifted/cancelled (+q_a(t-1))
        * If P_a(t) == P_a(t-1): quantity change -> Delta q_a(t) = q_a(t-1) - q_a(t)

    Returns:
        float: net signed order flow imbalance (positive = net buying pressure).
    """
    if not previous.bids or not previous.asks or not current.bids or not current.asks:
        raise ValueError("Both previous and current snapshots require at least best bid and ask")
    previous_bid, previous_ask = previous.bids[0], previous.asks[0]
    current_bid, current_ask = current.bids[0], current.asks[0]

    # Bid side component
    if current_bid.price > previous_bid.price:
        bid_component = current_bid.quantity
    elif current_bid.price < previous_bid.price:
        bid_component = -previous_bid.quantity
    else:
        bid_component = current_bid.quantity - previous_bid.quantity

    # Ask side component (positive when ask increases or ask size depletes)
    if current_ask.price < previous_ask.price:
        ask_component = -current_ask.quantity
    elif current_ask.price > previous_ask.price:
        ask_component = previous_ask.quantity
    else:
        ask_component = previous_ask.quantity - current_ask.quantity

    return bid_component + ask_component


def compute_multilevel_ofi(
    previous: BookSnapshot,
    current: BookSnapshot,
    levels: int = 5,
    weights: Optional[Sequence[float]] = None,
) -> dict[str, float]:
    """Compute Multi-Level Order Flow Imbalance across the top K levels.

    Extends Cont's formulation across depth levels k in 1..K.

    Args:
        previous: Earlier book snapshot.
        current: Later book snapshot.
        levels: Number of depth levels to evaluate (default: 5).
        weights: Optional weighting vector for integrated OFI. Defaults to harmonic 1/k.

    Returns:
        dict: Mapping of level names (e.g., 'l1_ofi', 'l2_ofi') and 'integrated_ofi'.
    """
    max_k = min(levels, len(previous.bids), len(current.bids), len(previous.asks), len(current.asks))
    if max_k == 0:
        raise ValueError("Snapshots must have at least one bid and ask level")

    if weights is None:
        raw_weights = [1.0 / (k + 1) for k in range(max_k)]
        norm = sum(raw_weights)
        weights = [w / norm for w in raw_weights]
    elif len(weights) < max_k:
        raise ValueError(f"Expected at least {max_k} weights, got {len(weights)}")

    result: dict[str, float] = {}
    integrated = 0.0

    for k in range(max_k):
        prev_b, curr_b = previous.bids[k], current.bids[k]
        prev_a, curr_a = previous.asks[k], current.asks[k]

        if curr_b.price > prev_b.price:
            b_comp = curr_b.quantity
        elif curr_b.price < prev_b.price:
            b_comp = -prev_b.quantity
        else:
            b_comp = curr_b.quantity - prev_b.quantity

        if curr_a.price < prev_a.price:
            a_comp = -curr_a.quantity
        elif curr_a.price > prev_a.price:
            a_comp = prev_a.quantity
        else:
            a_comp = prev_a.quantity - curr_a.quantity

        level_ofi = b_comp + a_comp
        result[f"l{k+1}_ofi"] = float(level_ofi)
        integrated += weights[k] * level_ofi

    result["integrated_ofi"] = float(integrated)
    return result


def book_snapshot_features(snapshot: BookSnapshot, levels: int = 10) -> dict[str, float]:
    """Extract canonical microstructure features from an order book snapshot."""
    if not snapshot.bids or not snapshot.asks:
        raise ValueError("Both bid and ask levels are required")
    bids = snapshot.bids[:levels]
    asks = snapshot.asks[:levels]
    best_bid = bids[0]
    best_ask = asks[0]
    mid = (best_bid.price + best_ask.price) / 2.0
    spread = best_ask.price - best_bid.price
    top_total = best_bid.quantity + best_ask.quantity
    microprice = (
        best_ask.price * best_bid.quantity + best_bid.price * best_ask.quantity
    ) / top_total if top_total > 0 else mid
    bid_depth = sum(level.quantity for level in bids)
    ask_depth = sum(level.quantity for level in asks)
    total_depth = bid_depth + ask_depth
    return {
        "best_bid": best_bid.price,
        "best_ask": best_ask.price,
        "mid": mid,
        "spread": spread,
        "spread_bps": (spread / mid * 10_000) if mid > 0 else np.nan,
        "top_imbalance": (
            (best_bid.quantity - best_ask.quantity) / top_total if top_total > 0 else 0.0
        ),
        "depth_imbalance": (bid_depth - ask_depth) / total_depth if total_depth > 0 else 0.0,
        "bid_depth": bid_depth,
        "ask_depth": ask_depth,
        "microprice": microprice,
        "microprice_offset_bps": ((microprice - mid) / mid * 10_000) if mid > 0 else 0.0,
    }
