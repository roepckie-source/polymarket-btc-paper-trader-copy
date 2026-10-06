"""
Risk Engine
Manages position sizing, risk limits, and portfolio constraints

IMPORTANT:
Polymarket BTC UP/DOWN positions are purchased tokens.

The strategy direction still means:
    long  = BTC/UP prediction
    short = BTC/DOWN prediction

But both positions are BUY positions in a Polymarket outcome token.
Therefore P&L is always:

    position_size * (exit_price - entry_price)

A "short" strategy signal is NOT a traditional short sale.
"""

import os
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from loguru import logger


def _env_decimal(name: str, default: Decimal) -> Decimal:
    raw = os.getenv(name)

    if raw is None or str(raw).strip() == "":
        return default

    try:
        return Decimal(str(raw).strip())

    except (InvalidOperation, ValueError):
        logger.warning(
            f"Invalid {name}={raw!r}; using default {default}"
        )
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)

    if raw is None or str(raw).strip() == "":
        return default

    try:
        return float(raw)

    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)

    if raw is None or str(raw).strip() == "":
        return default

    try:
        return int(float(raw))

    except (TypeError, ValueError):
        return default


class RiskLevel(Enum):
    """Risk level classification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskLimits:
    """Risk management limits."""

    max_position_size: Decimal
    max_total_exposure: Decimal
    max_positions: int
    max_drawdown_pct: float
    max_loss_per_day: Decimal
    max_leverage: float = 1.0


@dataclass
class PositionRisk:
    """Risk assessment for a Polymarket token position."""

    position_id: str
    current_size: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    risk_level: RiskLevel
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    time_held: float
    metadata: Dict[str, Any]


class RiskEngine:
    """
    Risk management engine for Polymarket BTC UP/DOWN tokens.

    IMPORTANT SEMANTIC RULE:

    The strategy's direction describes the BTC prediction:

        long  -> BTC expected UP -> buy YES/UP token
        short -> BTC expected DOWN -> buy NO/DOWN token

    Both are purchases of an outcome token.

    Therefore:

        token price rises -> profit
        token price falls -> loss

    The Risk Engine must NOT interpret strategy direction="short"
    as a traditional short sale.
    """

    def __init__(
        self,
        limits: Optional[RiskLimits] = None,
        account_balance: Optional[Decimal] = None,
    ):
        """
        Initialize risk engine.

        Args:
            limits:
                Risk limits configuration.

            account_balance:
                Account balance used for drawdown and daily-loss controls.
        """

        if account_balance is None:

            bal = _env_decimal(
                "ACCOUNT_BALANCE_USD",
                _env_decimal(
                    "STARTING_BALANCE_USD",
                    Decimal("100.0"),
                ),
            )

        else:
            bal = Decimal(str(account_balance))

        if bal <= 0:

            logger.warning(
                f"Account balance {bal} <= 0; "
                f"defaulting to $100"
            )

            bal = Decimal("100.0")

        self.limits = (
            limits
            or self._build_limits_from_env(bal)
        )

        # Track open positions.
        self._positions: Dict[str, PositionRisk] = {}

        # Daily statistics.
        self._daily_pnl = Decimal("0")
        self._daily_trades = 0

        self._starting_balance = bal
        self._peak_balance = bal
        self._current_balance = bal

        # Alerts.
        self._alerts: List[Dict[str, Any]] = []

        logger.info(
            f"Initialized Risk Engine: "
            f"balance=${self._current_balance:.2f}, "
            f"max_position=${self.limits.max_position_size}, "
            f"max_exposure=${self.limits.max_total_exposure}, "
            f"max_daily_loss=${self.limits.max_loss_per_day}, "
            f"max_drawdown={self.limits.max_drawdown_pct:.0%}"
        )

    @staticmethod
    def _build_limits_from_env(
        balance: Decimal,
    ) -> RiskLimits:
        """Build risk limits from environment variables."""

        max_position = _env_decimal(
            "MAX_POSITION_USD",
            _env_decimal(
                "MARKET_BUY_USD",
                Decimal("1.0"),
            ),
        )

        max_exposure = _env_decimal(
            "MAX_TOTAL_EXPOSURE_USD",
            max_position * Decimal("10"),
        )

        default_daily = (
            balance * Decimal("0.25")
        ).quantize(Decimal("0.01"))

        max_daily_loss = _env_decimal(
            "MAX_DAILY_LOSS_USD",
            default_daily,
        )

        return RiskLimits(
            max_position_size=max_position,
            max_total_exposure=max_exposure,
            max_positions=_env_int(
                "MAX_CONCURRENT_POSITIONS",
                5,
            ),
            max_drawdown_pct=_env_float(
                "MAX_DRAWDOWN_PCT",
                0.15,
            ),
            max_loss_per_day=max_daily_loss,
            max_leverage=1.0,
        )

    def set_account_balance(
        self,
        balance: Decimal,
        *,
        reset_peak: bool = True,
    ) -> None:
        """
        Update tracked account balance.

        ``reset_peak=True`` re-anchors the drawdown peak
        to the supplied balance.
        """

        try:
            bal = Decimal(str(balance))

        except (InvalidOperation, ValueError):

            logger.warning(
                f"set_account_balance: "
                f"invalid value {balance!r}"
            )

            return

        if bal <= 0:
            return

        self._current_balance = bal
        self._starting_balance = bal

        if reset_peak or bal > self._peak_balance:
            self._peak_balance = bal

        logger.info(
            f"Risk engine balance set to "
            f"${bal:.2f} "
            f"(peak=${self._peak_balance:.2f})"
        )

    def validate_new_position(
        self,
        size: Decimal,
        direction: str,
        current_price: Decimal,
    ) -> tuple[bool, Optional[str]]:
        """
        Validate whether a new Polymarket token position is allowed.

        ``direction`` remains the BTC signal direction:

            long  = BTC UP
            short = BTC DOWN

        It does NOT mean a traditional short sale.
        """

        if size > self.limits.max_position_size:

            return (
                False,
                f"Position size ${size} exceeds "
                f"max ${self.limits.max_position_size}",
            )

        if len(self._positions) >= self.limits.max_positions:

            return (
                False,
                f"Max positions reached "
                f"({self.limits.max_positions})",
            )

        current_exposure = self.get_total_exposure()
        new_exposure = current_exposure + size

        if new_exposure > self.limits.max_total_exposure:

            return (
                False,
                f"Total exposure ${new_exposure} "
                f"would exceed max "
                f"${self.limits.max_total_exposure}",
            )

        if self._daily_pnl < -self.limits.max_loss_per_day:

            return (
                False,
                f"Daily loss limit reached "
                f"(${abs(self._daily_pnl)})",
            )

        drawdown = self.get_current_drawdown()

        if drawdown > self.limits.max_drawdown_pct:

            return (
                False,
                f"Drawdown {drawdown:.1%} exceeds "
                f"max {self.limits.max_drawdown_pct:.1%}",
            )

        return True, None

    def calculate_position_size(
        self,
        signal_confidence: float,
        signal_score: float,
        current_price: Decimal,
        risk_percent: float = 0.02,
    ) -> Decimal:
        """
        Calculate position size.

        Position size is capped at $1.00 by default.
        """

        risk_amount = (
            self._current_balance
            * Decimal(str(risk_percent))
        )

        strength_multiplier = (
            Decimal(str(signal_confidence))
            * Decimal(str(signal_score / 100))
        )

        position_size = (
            risk_amount
            * strength_multiplier
        )

        if position_size > Decimal("1.0"):

            logger.info(
                f"Capping position size "
                f"from ${float(position_size):.2f} "
                f"to $1.00"
            )

            position_size = Decimal("1.0")

        # For the current paper-trading setup we enforce
        # a minimum position of $1.
        position_size = max(
            position_size,
            Decimal("1.0"),
        )

        logger.info(
            f"Calculated position size: "
            f"${position_size:.2f} "
            f"(confidence={signal_confidence:.2%}, "
            f"score={signal_score:.1f})"
        )

        return position_size

    def add_position(
        self,
        position_id: str,
        size: Decimal,
        entry_price: Decimal,
        direction: str,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None,
    ) -> None:
        """
        Add a Polymarket token position.

        ``direction`` is the BTC prediction direction.

        long:
            buy YES/UP token

        short:
            buy NO/DOWN token

        Both are bought tokens from the Risk Engine's
        P&L perspective.
        """

        position = PositionRisk(
            position_id=position_id,
            current_size=size,
            entry_price=entry_price,
            current_price=entry_price,
            unrealized_pnl=Decimal("0"),
            risk_level=RiskLevel.LOW,
            stop_loss=stop_loss,
            take_profit=take_profit,
            time_held=0.0,
            metadata={
                "direction": direction,
                "position_type": "polymarket_token_long",
                "entry_time": datetime.now(),
            },
        )

        self._positions[position_id] = position
        self._daily_trades += 1

        logger.info(
            f"Added position: "
            f"{position_id} "
            f"({direction.upper()} / "
            f"POLYMARKET TOKEN) "
            f"(${size:.2f} @ ${entry_price:.2f})"
        )

    def update_position(
        self,
        position_id: str,
        current_price: Decimal,
    ) -> Optional[PositionRisk]:
        """
        Update position with current token price.

        IMPORTANT:

        Both YES/UP and NO/DOWN are purchased tokens.

        Therefore P&L is always:

            (current_price - entry_price)
            / entry_price
        """

        if position_id not in self._positions:
            return None

        position = self._positions[position_id]

        position.current_price = current_price

        # --------------------------------------------------------------
        # POLYMARKET TOKEN P&L
        # --------------------------------------------------------------
        #
        # The strategy direction is NOT used to reverse P&L.
        #
        # long  = bought YES token
        # short = bought NO token
        #
        # In both cases:
        # token up   -> profit
        # token down -> loss
        #
        pnl_pct = (
            current_price - position.entry_price
        ) / position.entry_price

        position.unrealized_pnl = (
            position.current_size * pnl_pct
        )

        entry_time = position.metadata.get(
            "entry_time",
            datetime.now(),
        )

        position.time_held = (
            datetime.now() - entry_time
        ).total_seconds()

        position.risk_level = (
            self._assess_risk_level(position)
        )

        # Check stop loss.
        if (
            position.stop_loss
            and self._check_stop_loss(
                position,
                current_price,
            )
        ):

            self._create_alert(
                "STOP_LOSS",
                f"Stop loss hit for {position_id}",
                RiskLevel.HIGH,
            )

        # Check take profit.
        if (
            position.take_profit
            and self._check_take_profit(
                position,
                current_price,
            )
        ):

            self._create_alert(
                "TAKE_PROFIT",
                f"Take profit hit for {position_id}",
                RiskLevel.LOW,
            )

        return position

    def remove_position(
        self,
        position_id: str,
        exit_price: Decimal,
    ) -> Optional[Decimal]:
        """
        Remove position and record realized P&L.

        Both UP and DOWN Polymarket tokens are purchased.

        Therefore:

            realized_pnl =
                position_size
                * (exit_price - entry_price)

        The strategy direction is deliberately NOT used
        to invert the result.
        """

        if position_id not in self._positions:
            return None

        position = self._positions[position_id]

        # --------------------------------------------------------------
        # FINAL POLYMARKET TOKEN P&L
        # --------------------------------------------------------------

        pnl_pct = (
            exit_price - position.entry_price
        ) / position.entry_price

        realized_pnl = (
            position.current_size * pnl_pct
        )

        # Update balance and daily P&L.
        self._current_balance += realized_pnl
        self._daily_pnl += realized_pnl

        # Update peak balance.
        if self._current_balance > self._peak_balance:
            self._peak_balance = self._current_balance

        # Remove position.
        del self._positions[position_id]

        direction = position.metadata.get(
            "direction",
            "unknown",
        )

        logger.info(
            f"Closed position: "
            f"{position_id} "
            f"direction={str(direction).upper()} "
            f"P&L: ${realized_pnl:+.2f} "
            f"({pnl_pct:+.2%})"
        )

        return realized_pnl

    def _assess_risk_level(
        self,
        position: PositionRisk,
    ) -> RiskLevel:
        """Assess risk level of a position."""

        pnl_pct = (
            position.unrealized_pnl
            / position.current_size
            if position.current_size > 0
            else 0
        )

        if pnl_pct < -0.10:

            return RiskLevel.CRITICAL

        elif pnl_pct < -0.05:

            return RiskLevel.HIGH

        elif pnl_pct < -0.02:

            return RiskLevel.MEDIUM

        else:

            return RiskLevel.LOW

    def _check_stop_loss(
        self,
        position: PositionRisk,
        current_price: Decimal,
    ) -> bool:
        """
        Check whether token stop loss is hit.

        Both UP and DOWN tokens are purchased.

        Therefore a stop loss is always triggered
        when the token price falls to/below the stop.
        """

        if not position.stop_loss:
            return False

        return (
            current_price <= position.stop_loss
        )

    def _check_take_profit(
        self,
        position: PositionRisk,
        current_price: Decimal,
    ) -> bool:
        """
        Check whether token take profit is hit.

        Both UP and DOWN tokens are purchased.

        Therefore take profit is always triggered
        when the token price rises to/above the target.
        """

        if not position.take_profit:
            return False

        return (
            current_price >= position.take_profit
        )

    def _create_alert(
        self,
        alert_type: str,
        message: str,
        risk_level: RiskLevel,
    ) -> None:
        """Create a risk alert."""

        alert = {
            "timestamp": datetime.now(),
            "type": alert_type,
            "message": message,
            "risk_level": risk_level.value,
        }

        self._alerts.append(alert)

        logger.warning(
            f"[{risk_level.value.upper()}] "
            f"{alert_type}: {message}"
        )

    def get_total_exposure(self) -> Decimal:
        """Get total current exposure."""

        return sum(
            pos.current_size
            for pos in self._positions.values()
        )

    def get_total_unrealized_pnl(self) -> Decimal:
        """Get total unrealized P&L."""

        return sum(
            pos.unrealized_pnl
            for pos in self._positions.values()
        )

    def get_current_drawdown(self) -> float:
        """Get current drawdown from peak."""

        if self._peak_balance == 0:
            return 0.0

        drawdown = (
            self._peak_balance
            - self._current_balance
        ) / self._peak_balance

        return float(drawdown)

    def get_risk_summary(
        self,
    ) -> Dict[str, Any]:
        """Get comprehensive risk summary."""

        return {
            "timestamp": datetime.now(),

            "positions": {
                "count": len(self._positions),
                "max_allowed": self.limits.max_positions,
            },

            "exposure": {
                "current": float(
                    self.get_total_exposure()
                ),
                "max_allowed": float(
                    self.limits.max_total_exposure
                ),
                "utilization_pct": (
                    float(
                        self.get_total_exposure()
                        / self.limits.max_total_exposure
                        * 100
                    )
                    if self.limits.max_total_exposure > 0
                    else 0
                ),
            },

            "pnl": {
                "daily": float(
                    self._daily_pnl
                ),
                "unrealized": float(
                    self.get_total_unrealized_pnl()
                ),
                "daily_limit": float(
                    self.limits.max_loss_per_day
                ),
            },

            "balance": {
                "current": float(
                    self._current_balance
                ),
                "peak": float(
                    self._peak_balance
                ),
                "drawdown_pct": (
                    self.get_current_drawdown()
                    * 100
                ),
                "max_drawdown_pct": (
                    self.limits.max_drawdown_pct
                    * 100
                ),
            },

            "daily_stats": {
                "trades": self._daily_trades,
                "pnl": float(
                    self._daily_pnl
                ),
            },

            "alerts": len(
                [
                    a
                    for a in self._alerts
                    if (
                        datetime.now()
                        - a["timestamp"]
                    ).seconds < 3600
                ]
            ),
        }

    def reset_daily_stats(self) -> None:
        """Reset daily statistics."""

        self._daily_pnl = Decimal("0")
        self._daily_trades = 0

        logger.info(
            "Reset daily statistics"
        )


# Singleton instance.
_risk_engine_instance = None


def get_risk_engine() -> RiskEngine:
    """Get singleton risk engine."""

    global _risk_engine_instance

    if _risk_engine_instance is None:
        _risk_engine_instance = RiskEngine()

    return _risk_engine_instance
