"""
Polymarket BTC 5-Minute Paper Trader
Nautilus runner

PAPER-ONLY SAFETY:
- Simulation/test mode does NOT create an execution client.
- No private key is required for paper trading.
- No real orders are submitted in simulation mode.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import redis
from dotenv import load_dotenv
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv()

from bot.models import generate_btc_market_slugs

from patches.gamma_markets import (
    apply_gamma_markets_patch,
    verify_patch,
)

from patches.market_orders import apply_market_order_patch


# ---------------------------------------------------------------------------
# PATCHES
# ---------------------------------------------------------------------------

if not apply_gamma_markets_patch():
    print("ERROR: Failed to apply gamma_markets patch")
    sys.exit(1)

verify_patch()
apply_market_order_patch()


# ---------------------------------------------------------------------------
# NAUTILUS IMPORTS
# ---------------------------------------------------------------------------

from nautilus_trader.adapters.polymarket import POLYMARKET

from nautilus_trader.adapters.polymarket import (
    PolymarketDataClientConfig,
    PolymarketExecClientConfig,
)

from nautilus_trader.adapters.polymarket.factories import (
    PolymarketLiveDataClientFactory,
    PolymarketLiveExecClientFactory,
)

from nautilus_trader.config import (
    InstrumentProviderConfig,
    LiveDataEngineConfig,
    LiveExecEngineConfig,
    LiveRiskEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)

from nautilus_trader.live.node import TradingNode


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

def _logging_config(quiet: bool = False) -> LoggingConfig:
    """Create Nautilus logging configuration."""

    if quiet:
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


# ---------------------------------------------------------------------------
# REDIS
# ---------------------------------------------------------------------------

def init_redis():
    """Try to connect to Redis.

    Redis is optional for paper tests.
    """

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
        logger.warning("Continuing without Redis")
        return None


def _set_simulation_mode(client, simulation: bool) -> None:
    """Set Redis simulation flag when Redis is available."""

    if client is None:
        return

    try:
        client.set(
            "btc_trading:simulation_mode",
            "1" if simulation else "0",
        )

        logger.info(
            "Redis simulation mode: "
            + ("SIMULATION" if simulation else "LIVE")
        )

    except Exception as exc:
        logger.warning(
            f"Could not set Redis simulation mode: {exc}"
        )


# ---------------------------------------------------------------------------
# MARKET CONFIGURATION
# ---------------------------------------------------------------------------

def _build_instrument_config():
    """Build BTC 5-minute market configuration."""

    slugs = generate_btc_market_slugs()

    if not slugs:
        raise RuntimeError(
            "No BTC 5-minute market slugs generated."
        )

    logger.info("=" * 70)
    logger.info("LOADING BTC 5-MIN MARKETS")
    logger.info(f"Count: {len(slugs)}")
    logger.info(f"First: {slugs[0]}")
    logger.info(f"Last: {slugs[-1]}")
    logger.info("=" * 70)

    filters = {
        "active": True,
        "closed": False,
        "archived": False,
        "slug": tuple(slugs),
        "limit": 100,
    }

    return InstrumentProviderConfig(
        load_all=True,
        filters=filters,
        use_gamma_markets=True,
    )


# ---------------------------------------------------------------------------
# POLYMARKET DATA CLIENT
# ---------------------------------------------------------------------------

def _build_data_config(instrument_config):
    """Build Polymarket data configuration."""

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
        instrument_provider=instrument_config,
    )


# ---------------------------------------------------------------------------
# POLYMARKET EXECUTION CLIENT
# ---------------------------------------------------------------------------

def _build_exec_config(instrument_config):
    """Build live execution configuration.

    This function is NEVER called in simulation mode.
    """

    private_key = (
        os.getenv("POLYMARKET_PK") or ""
    ).strip()

    if not private_key:
        raise RuntimeError(
            "POLYMARKET_PK is required for LIVE execution."
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
            "POLYMARKET_FUNDER is required for "
            "signature type 1 or 2."
        )

    return PolymarketExecClientConfig(
        private_key=private_key,
        api_key=os.getenv("POLYMARKET_API_KEY"),
        api_secret=os.getenv("POLYMARKET_API_SECRET"),
        passphrase=os.getenv("POLYMARKET_PASSPHRASE"),
        signature_type=sig_type,
        funder=funder,
        instrument_provider=instrument_config,
    )


# ---------------------------------------------------------------------------
# STRATEGY
# ---------------------------------------------------------------------------

def _create_strategy(
    redis_client,
    simulation: bool,
    test_mode: bool,
    enable_grafana: bool,
):
    """Create the integrated BTC strategy."""

    from bot.strategy import IntegratedBTCStrategy

    return IntegratedBTCStrategy(
        redis_client=redis_client,
        simulation=simulation,
        test_mode=test_mode,
        enable_grafana=enable_grafana,
    )


# ---------------------------------------------------------------------------
# NODE
# ---------------------------------------------------------------------------

def _build_node(
    simulation: bool,
    test_mode: bool,
    enable_grafana: bool,
    quiet_console: bool = False,
):
    """Build the Nautilus TradingNode."""

    redis_client = init_redis()

    _set_simulation_mode(
        redis_client,
        simulation,
    )

    instrument_config = _build_instrument_config()

    data_config = _build_data_config(
        instrument_config
    )

    # ---------------------------------------------------------------
    # PAPER MODE
    # ---------------------------------------------------------------

    if simulation:

        logger.info("=" * 80)
        logger.info("PAPER-ONLY MODE ACTIVE")
        logger.info("Execution client: DISABLED")
        logger.info("Private key: NOT REQUIRED")
        logger.info("Wallet: NOT REQUIRED")
        logger.info("Real orders: DISABLED")
        logger.info("=" * 80)

        node_config = TradingNodeConfig(
            environment="live",
            trader_id="BTC-5MIN-INTEGRATED-001",
            logging=_logging_config(
                quiet=quiet_console
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
                POLYMARKET: data_config
            },
            exec_clients={},
        )

    # ---------------------------------------------------------------
    # LIVE MODE
    # ---------------------------------------------------------------

    else:

        logger.warning("=" * 80)
        logger.warning("LIVE EXECUTION MODE")
        logger.warning("REAL MONEY MAY BE AT RISK")
        logger.warning("=" * 80)

        exec_config = _build_exec_config(
            instrument_config
        )

        node_config = TradingNodeConfig(
            environment="live",
            trader_id="BTC-5MIN-INTEGRATED-001",
            logging=_logging_config(
                quiet=quiet_console
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
                POLYMARKET: data_config
            },
            exec_clients={
                POLYMARKET: exec_config
            },
        )

    # ---------------------------------------------------------------
    # CREATE NODE
    # ---------------------------------------------------------------

    strategy = _create_strategy(
        redis_client=redis_client,
        simulation=simulation,
        test_mode=test_mode,
        enable_grafana=enable_grafana,
    )

    node = TradingNode(
        config=node_config
    )

    # Data client is always registered.
    node.add_data_client_factory(
        POLYMARKET,
        PolymarketLiveDataClientFactory,
    )

    # Execution client is ONLY registered in live mode.
    if not simulation:

        node.add_exec_client_factory(
            POLYMARKET,
            PolymarketLiveExecClientFactory,
        )

        logger.warning(
            "LIVE execution factory registered."
        )

    else:

        logger.info(
            "Paper mode: execution factory NOT registered."
        )

    node.trader.add_strategy(
        strategy
    )

    node.build()

    logger.info(
        "Nautilus node built successfully."
    )

    return node


# ---------------------------------------------------------------------------
# TUI BOOTSTRAP
# ---------------------------------------------------------------------------

def _boot_bot_node(
    simulation: bool,
    enable_grafana: bool,
    test_mode: bool,
):
    """Build node for terminal UI."""

    return _build_node(
        simulation=simulation,
        test_mode=test_mode,
        enable_grafana=enable_grafana,
        quiet_console=True,
    )


# ---------------------------------------------------------------------------
# MAIN BOT ENTRY POINT
# ---------------------------------------------------------------------------

def run_integrated_bot(
    simulation: bool = True,
    enable_grafana: bool = False,
    test_mode: bool = False,
    enable_tui: bool = True,
) -> None:
    """Run integrated BTC 5-minute bot."""

    if enable_tui:

        from monitoring.terminal_ui import run_bot_session

        try:

            run_bot_session(
                lambda: _boot_bot_node(
                    simulation=simulation,
                    enable_grafana=enable_grafana,
                    test_mode=test_mode,
                ),
                simulation=simulation,
                test_mode=test_mode,
            )

        except KeyboardInterrupt:

            logger.info("Bot interrupted.")

        finally:

            logger.info("Bot stopped.")

        return

    print("=" * 80)
    print("POLYMARKET BTC 5-MIN PAPER TRADER")
    print("=" * 80)

    print(
        "Mode:",
        "TEST SIMULATION" if test_mode else (
            "SIMULATION" if simulation else "LIVE"
        ),
    )

    print(
        "Execution:",
        "PAPER ONLY" if simulation else "LIVE",
    )

    print(
        "Private Key:",
        "NOT REQUIRED" if simulation else "REQUIRED",
    )

    print(
        "Real Orders:",
        "DISABLED" if simulation else "ENABLED",
    )

    print("=" * 80)

    node = None

    try:

        node = _build_node(
            simulation=simulation,
            test_mode=test_mode,
            enable_grafana=enable_grafana,
            quiet_console=False,
        )

        print()
        print("BOT STARTING")
        print()

        node.run()

    except KeyboardInterrupt:

        print("Bot interrupted.")

    finally:

        if node is not None:

            try:
                node.dispose()

            except Exception as exc:

                logger.warning(
                    f"Node dispose warning: {exc}"
                )

        logger.info("Bot stopped.")


# ---------------------------------------------------------------------------
# COMMAND LINE
# ---------------------------------------------------------------------------

def main() -> None:
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description="Polymarket BTC 5-Minute Trading Bot"
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable live trading.",
    )

    parser.add_argument(
        "--no-grafana",
        action="store_true",
        help="Disable Grafana.",
    )

    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run accelerated paper simulation.",
    )

    parser.add_argument(
        "--no-tui",
        action="store_true",
        help="Disable terminal UI.",
    )

    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip startup checks.",
    )

    args = parser.parse_args()

    # ---------------------------------------------------------------
    # TEST MODE ALWAYS OVERRIDES LIVE MODE
    # ---------------------------------------------------------------

    if args.test_mode:

        simulation = True

    else:

        simulation = not args.live

    enable_grafana = not args.no_grafana
    enable_tui = not args.no_tui

    if simulation:

        logger.info("=" * 80)
        logger.info("SIMULATION MODE")
        logger.info("PAPER TRADING ONLY")
        logger.info("REAL ORDERS DISABLED")
        logger.info("PRIVATE KEY NOT REQUIRED")
        logger.info("=" * 80)

    else:

        logger.warning("=" * 80)
        logger.warning("LIVE TRADING MODE")
        logger.warning("REAL MONEY MAY BE AT RISK")
        logger.warning("=" * 80)

    run_integrated_bot(
        simulation=simulation,
        enable_grafana=enable_grafana,
        test_mode=args.test_mode,
        enable_tui=enable_tui,
    )


if __name__ == "__main__":
    main()