from datetime import datetime, timezone
from decimal import Decimal

from monitoring.performance_tracker import PerformanceTracker
from execution.risk_engine import RiskEngine, RiskLimits


def test_polymarket_yes_token_profit():
    """
    YES / UP token:
    Entry $0.40 -> Exit $0.60
    Expected P&L: +$0.50 / +50%
    """

    tracker = PerformanceTracker(initial_capital=Decimal("1000"))

    trade = tracker.record_trade(
        trade_id="INTEGRATION-YES-WIN",
        direction="long",
        entry_price=Decimal("0.40"),
        exit_price=Decimal("0.60"),
        size=Decimal("1.00"),
        entry_time=datetime.now(timezone.utc),
        exit_time=datetime.now(timezone.utc),
    )

    assert trade.pnl == Decimal("0.50")
    assert trade.pnl_pct == 0.50


def test_polymarket_no_token_profit():
    """
    NO / DOWN token:
    Entry $0.31 -> Exit $0.59
    Expected P&L: +$0.9032258 / +90.32%
    """

    tracker = PerformanceTracker(initial_capital=Decimal("1000"))

    trade = tracker.record_trade(
        trade_id="INTEGRATION-NO-WIN",
        direction="short",
        entry_price=Decimal("0.31"),
        exit_price=Decimal("0.59"),
        size=Decimal("1.00"),
        entry_time=datetime.now(timezone.utc),
        exit_time=datetime.now(timezone.utc),
    )

    expected_pnl = (
        Decimal("0.59") - Decimal("0.31")
    ) / Decimal("0.31")

    assert abs(trade.pnl - expected_pnl) < Decimal("0.00000001")
    assert abs(
        trade.pnl_pct - 0.9032258064516129
    ) < 0.00000001


def test_polymarket_no_token_loss():
    """
    NO / DOWN token:
    Entry $0.08 -> Exit $0.04
    Expected P&L: -$0.50 / -50%
    """

    tracker = PerformanceTracker(initial_capital=Decimal("1000"))

    trade = tracker.record_trade(
        trade_id="INTEGRATION-NO-LOSS",
        direction="short",
        entry_price=Decimal("0.08"),
        exit_price=Decimal("0.04"),
        size=Decimal("1.00"),
        entry_time=datetime.now(timezone.utc),
        exit_time=datetime.now(timezone.utc),
    )

    assert trade.pnl == Decimal("-0.50")
    assert trade.pnl_pct == -0.50


def test_risk_engine_polymarket_token_pnl():
    """
    Verify that RiskEngine uses Polymarket token-price P&L.

    Both YES and NO are purchased outcome tokens.

    Therefore:

        P&L = (exit_price - entry_price)
               / entry_price * position_size
    """

    limits = RiskLimits(
        max_position_size=Decimal("10"),
        max_total_exposure=Decimal("100"),
        max_positions=10,
        max_drawdown_pct=0.15,
        max_loss_per_day=Decimal("25"),
        max_leverage=1.0,
    )

    risk = RiskEngine(
        limits=limits,
        account_balance=Decimal("100"),
    )

    risk.add_position(
        position_id="RISK-NO-WIN",
        size=Decimal("1"),
        entry_price=Decimal("0.31"),
        direction="short",
    )

    result = risk.remove_position(
        position_id="RISK-NO-WIN",
        exit_price=Decimal("0.59"),
    )

    assert result is not None

    if isinstance(result, dict):
        pnl = result.get("pnl")
    else:
        pnl = getattr(result, "pnl", None)

    assert pnl is not None

    expected_pnl = (
        Decimal("0.59") - Decimal("0.31")
    ) / Decimal("0.31")

    assert abs(
        Decimal(str(pnl)) - expected_pnl
    ) < Decimal("0.00000001")