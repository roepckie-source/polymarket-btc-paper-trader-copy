"""
bot.runner — Node construction and top-level ``run_integrated_bot`` entry point.

PAPER-ONLY SAFETY:
In simulation/test mode, the Polymarket execution client is NOT created.
This prevents any private-key requirement and guarantees that the paper
trader cannot initialize a real order execution path.
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

# Apply patches BEFORE importing Nautilus
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
    """Initialise Redis connection for optional simulation control."""

    try:
        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            db=int(os.getenv("REDIS_DB", 2)),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True,
        )

        client.ping()

        logger.info("Redis connection established")

        return client

    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        logger.warning("Simulation mode will be static (from .env)")

        return None


def _set_redis_simulation_mode(redis_client, simulation: bool):
    """Set Redis simulation flag when Redis is available."""

    if not redis_client:
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

    except Exception as e:
        logger.warning(
            f"Could not set Redis simulation mode: {e}"
        )


def _build_instrument_config():
    """Build BTC 5-minute market instrument configuration."""

    btc_slugs = generate_btc_market_slugs()

    filters = {
        "active": True,
        "closed": False,
        "archived": False,
        "slug": tuple(btc_slugs),
        "limit": 100,
    }

    logger.info(
        "Loading BTC 5-min markets by slug"
    )

    logger.info(
        f"  First: {btc_slugs[0]} | "
        f"Count: {len(btc_slugs)}"
    )

    logger.info(
        f"  Last: {btc_slugs[-1]}"
    )

    instrument_cfg = InstrumentProviderConfig(
        load_all=True,
        filters=filters,
        use_gamma_markets=True,
    )

    return instrument_cfg


def _build_polymarket_data_config(instrument_cfg):
    """
    Build the Polymarket DATA client.

    Public market data does not require a private key.
    """

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
    Build the Polymarket EXECUTION client.

    This function is intentionally isolated so it is only called
    when live execution is explicitly requested.
    """

    sig_type = int(
        os.getenv(
            "POLYMARKET_SIG_TYPE",
            "2",
        )
    )

    funder = (
        os.getenv("POLYMARKET_FUNDER") or ""
    ).strip() or None

    if not os.getenv("POLYMARKET_PK"):
        raise RuntimeError(
            "Live execution requires POLYMARKET_PK. "
            "Paper mode must never call this function."
        )

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

    logger.info(
        f"Polymarket LIVE wallet config: "
        f"signature_type={sig_type} ({sig_label})"
    )

    logger.info(
        f"  Funder: {funder}"
    )

    return PolymarketExecClientConfig(
        private_key=os.getenv("POLYMARKET_PK"),
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

    strategy = IntegratedBTCStrategy(
        redis_client=redis_client,
        enable_grafana=enable_grafana,
        test_mode=test_mode,
        simulation=simulation,
    )

    return strategy


def _build_node(
    *,
    simulation: bool,
    enable_grafana: bool,
    test_mode: bool,
    quiet_console: bool,
):
    """
    Build the Nautilus node.

    CRITICAL SAFETY RULE:

    simulation=True
        -> DATA CLIENT only
        -> NO execution client
        -> NO private key
        -> NO wallet
        -> NO real orders

    simulation=False
        -> execution client may be created
        -> explicit credentials required
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

    # ------------------------------------------------------------
    # PAPER MODE
    # ------------------------------------------------------------

    if simulation:

        logger.info("=" * 80)
        logger.info(
            "PAPER-ONLY MODE: "
            "Polymarket execution client DISABLED"
        )
        logger.info(
            "PAPER-ONLY MODE: "
            "Private key NOT required"
        )
        logger.info(
            "PAPER-ONLY MODE: "
            "Real orders DISABLED"
        )
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

    # ------------------------------------------------------------
    # LIVE MODE
    # ------------------------------------------------------------

    else:

        logger.warning("=" * 80)
        logger.warning(
            "LIVE EXECUTION MODE REQUESTED"
        )
        logger.warning(
            "REAL MONEY MAY BE AT RISK"
        )
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
            data_engine=LiveDataEngineConfig(
                qsize=6000
            ),
            exec_engine=LiveExecEngineConfig(
                qsize=6000
            ),
            risk_engine=LiveRiskEngineConfig(
                bypass=False
            ),
            data_clients={
                POLYMARKET: poly_data_cfg
            },
            exec_clients={
                POLYMARKET: poly_exec_cfg
            },
        )

    strategy = _create_strategy(
        redis_client=redis_client,
        enable_grafana=enable_grafana,
        test_mode=test_mode,
        simulation=simulation,
    )

    node = TradingNode(
        config=config
    )

    # ------------------------------------------------------------
    # DATA CLIENT
    # ------------------------------------------------------------

    node.add_data_client_factory(
        POLYMARKET,
        PolymarketLiveDataClientFactory,
    )

    # ------------------------------------------------------------
    # EXECUTION CLIENT
    #
    # IMPORTANT:
    # Never register the Polymarket execution factory in
    # simulation mode.
    # ------------------------------------------------------------

    if not simulation:

        node.add_exec_client_factory(
            POLYMARKET,
            PolymarketLiveExecClientFactory,
        )

        logger.info(
            "Polymarket execution factory registered"
        )

    else:

        logger.info(
            "Paper mode: "
            "Polymarket execution factory NOT registered"
        )

    node.trader.add_strategy(
        strategy
    )

    node.build()

    logger.info(
        "Nautilus node built successfully"
    )

    return (
        node,
        strategy,
        redis_client is not None,
    )


def _boot_bot_node(
    simulation: bool,
    enable_grafana: bool,
    test_mode