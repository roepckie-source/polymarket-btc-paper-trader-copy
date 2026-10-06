from datetime import datetime, timezone
from decimal import Decimal

from monitoring.performance_tracker import PerformanceTracker


def test_polymarket_no_token_losing_trade():
    """
    Polymarket SHORT = BUY NO (DOWN).

    Entry: $0.08
    Exit:  $0.04
    Size:  $1.00

    Expected:
        P&L = -$0.50
        P&L% = -50%
    """

    tracker = PerformanceTracker(initial_capital=Decimal("1000"))

    entry_time = datetime.now(timezone.utc)
    exit_time = datetime.now(timezone.utc)

    trade = tracker.record_trade(
        trade_id="TEST-NO-LOSS",
        direction="short",
        entry_price=Decimal("0.08"),
        exit_price=Decimal("0.04"),
        size=Decimal("1.00"),
        entry_time=entry_time,
        exit_time=exit_time,
    )

    assert trade.pnl == Decimal("-0.50")
    assert trade.pnl_pct == -0.50


def test_polymarket_no_token_winning_trade():
    """
    Polymarket SHORT = BUY NO (DOWN).

    Entry: $0.31
    Exit:  $0.59
    Size:  $1.00

    Expected:
        P&L ≈ +$0.9032
        P&L% ≈ +90.32%
    """

    tracker = PerformanceTracker(initial_capital=Decimal("1000"))

    entry_time = datetime.now(timezone.utc)
    exit_time = datetime.now(timezone.utc)

    trade = tracker.record_trade(
        trade_id="TEST-NO-WIN",
        direction="short",
        entry_price=Decimal("0.31"),
        exit_price=Decimal("0.59"),
        size=Decimal("1.00"),
        entry_time=entry_time,
        exit_time=exit_time,
    )

    expected_pnl = (
        Decimal("0.59") - Decimal("0.31")
    ) / Decimal("0.31")

    assert abs(trade.pnl - expected_pnl) < Decimal("0.00000001")

    assert abs(
        trade.pnl_pct - 0.9032258064516129
    ) < 0.00000001


def test_polymarket_yes_token_winning_trade():
    """
    Polymarket LONG = BUY YES (UP).

    Entry: $0.40
    Exit:  $0.60
    Size:  $1.00

    Expected:
        P&L = +$0.50
        P&L% = +50%
    """

    tracker = PerformanceTracker(initial_capital=Decimal("1000"))

    entry_time = datetime.now(timezone.utc)
    exit_time = datetime.now(timezone.utc)

    trade = tracker.record_trade(
        trade_id="TEST-YES-WIN",
        direction="long",
        entry_price=Decimal("0.40"),
        exit_price=Decimal("0.60"),
        size=Decimal("1.00"),
        entry_time=entry_time,
        exit_time=exit_time,
    )

    assert trade.pnl == Decimal("0.50")
    assert trade.pnl_pct == 0.50
