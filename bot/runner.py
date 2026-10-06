"""
bot.runner — Node construction and top-level run_integrated_bot entry point.

PAPER-ONLY SAFETY:
In simulation/test mode the Polymarket execution client is NOT created.
No private key, wallet or real order execution is required.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from loguru import logger
import redis

from bot.models import generate_btc_market_slugs

# Apply patches before importing Nautilus.
from patches.gamma_markets import apply_gamma_markets_patch, verify_patch

_patch_applied = apply_gamma_markets_patch()

if _patch_applied:
    verify_patch()
else:
    print("ERROR: Failed to apply gamma_markets patch")
    sys.exit(1)

from nautilus_trader.config import (
    InstrumentProviderConfig,
    LiveDataEngineConfig,
    LiveExecEngineConfig,
    LiveRiskEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)

from nautilus_trader.live.node import TradingNode

from nautilus_trader.adapters.polymarket import POLYMARKET

from nautilus_trader.adapters.polymarket import (
    PolymarketDataClientConfig,
    PolymarketExecClientConfig,
)

from nautilus_trader.adapters.polymarket.factories import (
    PolymarketLiveDataClientFactory,
    PolymarketLiveExecClientFactory,
)

from patches.market_orders import apply_market_order_patch

apply_market_order_patch()


def _nautilus_logging_config(*, quiet_console: bool) -> LoggingConfig:
    """Configure Nautilus logging."""

    if quiet_console:
        return LoggingConfig(
            log_level="INFO",
            log_level_file="INFO",
            log_directory="./logs/nautilus",
            log_components_only=True,
            print_config=False,
            log_colors=False,
        )

    return LoggingConfig(
        log_level="INFO",
        log_directory="./logs/nautilus",
    )


def init_redis():
    """Initialize optional Redis connection."""

    try:
        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "2")),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
        )

        client.ping()

        logger.info("Redis connection established")

        return client

    except Exception as exc:
        logger.warning(f"Redis connection failed: {exc}")
        logger.warning("Simulation mode will be static")
        return None


def _set_redis_simulation_mode(redis_client, simulation: bool) -> None:
    """Set the optional Redis simulation flag."""

    if redis_client is None:
        return

    try:
        mode_value = "1" if simulation else "0"
        mode_label = "SIMULATION" if simulation else "LIVE"

        redis_client.set(
            "btc_trading:simulation_mode",
            mode_value,
        )

        logger.info(
            f"Redis simulation_mode forced to: "
            f"{mode_label} ({mode_value})"
        )

    except Exception as exc:
        logger.warning(
            f"Could not set Redis simulation mode: {exc}"
        )


def _build_instrument_config():
    """Build the BTC 5-minute instrument configuration."""

    btc_slugs = generate_btc_market_slugs()

    if not btc_slugs:
        raise RuntimeError(
            "No BTC 5-minute market slugs were generated."
        )

    filters = {
        "active": True,
        "closed": False,
        "archived": False,
        "slug": tuple(btc_slugs),
        "limit": 100,
    }

    logger.info("=" * 60)
    logger.info("LOADING BTC 5-MIN MARKETS BY SLUG")
    logger.info(f"  Count: {len(btc_slugs)}")
    logger.info(f"  First: {btc_slugs[0]}")
    logger.info(f"  Last: {btc_slugs[-1]}")
    logger.info("=" * 60)

    return InstrumentProviderConfig(
        load_all=True,
        filters=filters,
        use_gamma_markets=True,
    )


def _build_polymarket_data_config(instrument_cfg):
    """Build the Polymarket market-data client."""

    sig_type = int(
        os.getenv(
            "POLYMARKET_SIG_TYPE",
            "2",
        )
    )

    funder = (
        os.getenv("POLYMARKET_FUNDER") or ""
    ).strip() or None

    return PolymarketDataClientConfig(
        private_key=os.getenv("POLYMARKET_PK"),
        api_key=os.getenv("POLYMARKET_API_KEY"),
        api_secret=os.getenv("POLYMARKET_API_SECRET"),
        passphrase=os.getenv("POLYMARKET_PASSPHRASE"),
        signature_type=sig_type,
        funder=funder,
        instrument_provider=instrument_cfg,
    )


def _build_polymarket_exec_config(instrument_cfg):
    """
    Build the Polymarket execution client.

    This function must NEVER be called in paper/simulation mode.
    """

    private_key = (
        os.getenv("POLYMARKET_PK") or ""
    ).strip()

    if not private_key:
        raise RuntimeError(
            "Live execution requires POLYMARKET_PK. "
            "Paper mode must not create an execution client."
        )

    sig_type = int(
        os.getenv(
            "POLYMARKET_SIG_TYPE",
            "2",
        )
    )

    funder = (
        os.getenv("POLYMARKET_FUNDER") or ""
    ).strip() or None

    if sig_type in (1, 2) and not funder:
        raise RuntimeError(
            "Live execution with signature type 1 or 2 "
            "requires POLYMARKET_FUNDER."
        )

    sig_label = {
        0: "EOA",
        1: "POLY_PROXY",
        2: "POLY_GNOSIS_SAFE",
    }.get(
        sig_type,
        "UNKNOWN",
    )

    logger.warning(
        f"LIVE execution configuration: "
        f"signature_type={sig_type} ({sig_label})"
    )

    return PolymarketExecClientConfig(
        private_key=private_key,
        api_key=os.getenv("POLYMARKET_API_KEY"),
        api_secret=os.getenv("POLYMARKET_API_SECRET"),
        passphrase=os.getenv("POLYMARKET_PASSPHRASE"),
        signature_type=sig_type,
        funder=funder,
        instrument_provider=instrument_cfg,
    )


def _create_strategy(
    redis_client,
    enable_grafana: bool,
    test_mode: bool,
    simulation: bool,
):
    """Create the integrated BTC strategy."""

    from bot.strategy import IntegratedBTCStrategy

    return IntegratedBTCStrategy(
        redis_client=redis_client,
        enable_grafana=enable_grafana,
        test_mode=test_mode,
        simulation=simulation,
    )


def _build_node(
    *,
    simulation: bool,
    enable_grafana: bool,
    test_mode: bool,
    quiet_console: bool,
):
    """
    Build the Nautilus node.

    PAPER MODE:
      - Data client: YES
      - Execution client: NO
      - Private key: NOT REQUIRED
      - Real orders: DISABLED

    LIVE MODE:
      - Data client: YES
      - Execution client: YES
      - Explicit credentials required
    """

    redis_client = init_redis()

    _set_redis_simulation_mode(
        redis_client,
        simulation,
    )

    instrument_cfg = _build_instrument_config()

    poly_data_cfg = _build_polymarket_data_config(
        instrument_cfg
    )

    if simulation:

        logger.info("=" * 80)
        logger.info("PAPER-ONLY MODE ACTIVE")
        logger.info("Polymarket execution client: DISABLED")
        logger.info("Private key: NOT REQUIRED")
        logger.info("Real orders: DISABLED")
        logger.info("=" * 80)

        config = TradingNodeConfig(
            environment="live",
            trader_id="BTC-5MIN-INTEGRATED-001",
            logging=_nautilus_logging_config(
                quiet_console=quiet_console
            ),
            data_engine=LiveDataEngineConfig(
                qsize=6000
            ),
            exec_engine=LiveExecEngineConfig(
                qsize=6000
            ),
            risk_engine=LiveRiskEngineConfig(
                bypass=True
            ),
            data_clients={
                POLYMARKET: poly_data_cfg
            },
            exec_clients={},
        )

    else:

        logger.warning("=" * 80)
        logger.warning("LIVE EXECUTION MODE REQUESTED")
        logger.warning("REAL MONEY MAY BE AT RISK")
        logger.warning("=" * 80)

        poly_exec_cfg = _build_polymarket_exec_config(
            instrument_cfg
        )

        config = TradingNodeConfig(
            environment="live",
            trader_id="BTC-5MIN-INTEGRATED-001",
            logging=_nautilus_logging_config(
                quiet_console=quiet_console
            ),
           