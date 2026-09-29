"""
main.py
Polymarket BTC 5-Minute Paper Trader

Research / Paper Trading only.

Available modes:
    python main.py --test-mode
    python main.py --simulation

IMPORTANT:
    Live trading is intentionally NOT implemented in this project version.
    No real orders can be submitted through this entry point.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import box


# ============================================================
# PROJECT ROOT
# ============================================================

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

console = Console()


# ============================================================
# SAFETY
# ============================================================

PAPER_TRADING = True
LIVE_TRADING = False


if not PAPER_TRADING:
    raise RuntimeError("PAPER_TRADING must remain enabled.")

if LIVE_TRADING:
    raise RuntimeError("LIVE_TRADING is disabled in this project.")


# ============================================================
# LOGGING
# ============================================================

def setup_logging(
    test_mode: bool,
    verbose: bool,
    enable_tui: bool = True,
) -> None:
    """
    Configure console and file logging.
    """

    logger.remove()

    level = "DEBUG" if verbose else "INFO"

    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_label = "test" if test_mode else "simulation"

    if enable_tui:
        try:
            from monitoring.terminal_ui import install_log_sink

            install_log_sink(
                level=level,
                console=console,
            )

        except (ImportError, TypeError):
            # Fallback if the optional TUI is not available.
            logger.add(
                sys.stderr,
                level=level,
                format=(
                    "<green>{time:HH:mm:ss}</green> | "
                    "<level>{level:<7}</level> | "
                    "<cyan>{name}</cyan> | "
                    "{message}"
                ),
            )

    else:
        logger.add(
            sys.stderr,
            level=level,
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level:<7}</level> | "
                "<cyan>{name}</cyan> | "
                "{message}"
            ),
        )

    logger.add(
        log_dir / f"bot_{mode_label}_{timestamp}.log",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level:<7} | "
            "{name} | "
            "{message}"
        ),
        level="DEBUG",
        rotation="50 MB",
        retention="14 days",
    )


# ============================================================
# BANNER
# ============================================================

def print_banner(
    simulation: bool,
    test_mode: bool,
) -> None:
    """
    Display a clear paper-trading banner.
    """

    if test_mode:
        mode_text = Text(
            "TEST SIMULATION",
            style="bold yellow",
        )
        mode_description = (
            "Accelerated test clock · paper trades only"
        )
        border_style = "yellow"

    elif simulation:
        mode_text = Text(
            "PAPER SIMULATION",
            style="bold cyan",
        )
        mode_description = (
            "5-minute clock · paper trades only · no real orders"
        )
        border_style = "cyan"

    else:
        # This should never be reachable because live trading
        # is not exposed by the CLI.
        raise RuntimeError(
            "Invalid mode: live trading is disabled."
        )

    title = Text()
    title.append(
        "POLYMARKET ",
        style="bold white",
    )
    title.append(
        "BTC",
        style="bold yellow",
    )
    title.append(
        " 5-MIN PAPER TRADER",
        style="bold white",
    )

    body = Text(justify="center")

    body.append(
        "Mode: ",
        style="dim",
    )

    body.append(mode_text)

    body.append(
        f"\n{mode_description}",
        style="dim",
    )

    body.append(
        "\n\nLIVE TRADING: ",
        style="dim",
    )

    body.append(
        "DISABLED",
        style="bold green",
    )

    body.append(
        "\nREAL ORDERS: ",
        style="dim",
    )

    body.append(
        "DISABLED",
        style="bold green",
    )

    body.append(
        "\nWALLET: ",
        style="dim",
    )

    body.append(
        "NOT REQUIRED",
        style="bold green",
    )

    console.print()

    console.print(
        Panel(
            body,
            title=title,
            border_style=border_style,
            padding=(1, 4),
        )
    )


# ============================================================
# PRE-FLIGHT CHECKS
# ============================================================

def preflight(
    simulation: bool,
    silent: bool = False,
) -> bool:
    """
    Perform safe paper-trading pre-flight checks.

    No live credentials are required.
    """

    if not silent:
        console.print()
        console.print(
            Rule(
                "[bold white]PRE-FLIGHT CHECKS[/bold white]",
                style="white",
            )
        )

    ok = True

    table = Table(
        box=box.SIMPLE,
        show_header=False,
        pad_edge=False,
        padding=(0, 1),
    )

    table.add_column(
        "icon",
        style="bold",
        width=4,
    )

    table.add_column(
        "check",
        style="cyan",
        min_width=32,
    )

    table.add_column("status")

    # --------------------------------------------------------
    # Safety
    # --------------------------------------------------------

    if PAPER_TRADING:
        table.add_row(
            "✓",
            "PAPER_TRADING",
            Text("ENABLED", style="bold green"),
        )
    else:
        table.add_row(
            "✗",
            "PAPER_TRADING",
            Text("DISABLED", style="bold red"),
        )
        ok = False

    if not LIVE_TRADING:
        table.add_row(
            "✓",
            "LIVE_TRADING",
            Text("DISABLED", style="bold green"),
        )
    else:
        table.add_row(
            "✗",
            "LIVE_TRADING",
            Text("MUST BE DISABLED", style="bold red"),
        )
        ok = False

    # --------------------------------------------------------
    # Python
    # --------------------------------------------------------

    py_version = sys.version_info

    python_version = (
        f"{py_version.major}."
        f"{py_version.minor}."
        f"{py_version.micro}"
    )

    if py_version >= (3, 14):
        table.add_row(
            "✓",
            "Python",
            Text(
                f"{python_version} OK",
                style="green",
            ),
        )
    else:
        table.add_row(
            "!",
            "Python",
            Text(
                f"{python_version} — requires 3.14+",
                style="yellow",
            ),
        )

    # --------------------------------------------------------
    # Optional modules
    # --------------------------------------------------------

    optional_modules = [
        ("numpy", "numerical processing"),
        ("pandas", "data processing"),
        ("requests", "HTTP data access"),
        ("dotenv", "environment configuration"),
        ("sklearn", "machine learning"),
        ("xgboost", "ML model"),
        ("websockets", "streaming data"),
        ("web3", "settlement / blockchain"),
        ("redis", "runtime state"),
    ]

    for module_name, purpose in optional_modules:

        try:
            __import__(module_name)

            table.add_row(
                "✓",
                module_name,
                Text(
                    f"installed ({purpose})",
                    style="green",
                ),
            )

        except ImportError:

            table.add_row(
                "–",
                module_name,
                Text(
                    f"not installed ({purpose})",
                    style="yellow",
                ),
            )

    # --------------------------------------------------------
    # Environment
    # --------------------------------------------------------

    # These are intentionally informational only.
    # Paper trading must not require credentials.

    rpc_url = __import__("os").getenv("ETH_RPC_URL")

    if rpc_url:
        table.add_row(
            "✓",
            "ETH_RPC_URL",
            Text(
                "configured",
                style="green",
            ),
        )
    else:
        table.add_row(
            "–",
            "ETH_RPC_URL",
            Text(
                "not configured — optional for paper mode",
                style="dim",
            ),
        )

    if not silent:
        console.print(table)
        console.print(
            Rule(style="white")
        )

    return ok


# ============================================================
# BOT START
# ============================================================

def start_bot(
    simulation: bool,
    test_mode: bool,
    enable_grafana: bool,
    enable_tui: bool,
) -> None:
    """
    Start the integrated bot in paper mode.
    """

    try:
        from bot.runner import run_integrated_bot

    except ImportError as exc:

        console.print(
            Panel(
                f"[bold red]Could not import bot.runner[/bold red]\n\n"
                f"{exc}\n\n"
                "The repository structure or dependencies "
                "are not ready yet.",
                border_style="red",
                title="[red]STARTUP ERROR[/red]",
            )
        )

        sys.exit(1)

    logger.info(
        "Starting Polymarket BTC Paper Trader"
    )

    logger.info(
        "PAPER_TRADING=True"
    )

    logger.info(
        "LIVE_TRADING=False"
    )

    logger.info(
        f"simulation={simulation}"
    )

    logger.info(
        f"test_mode={test_mode}"
    )

    run_integrated_bot(
        simulation=True,
        enable_grafana=enable_grafana,
        test_mode=test_mode,
        enable_tui=enable_tui,
    )


# ============================================================
# CLI
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Polymarket BTC 5-minute "
            "paper-trading research bot"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  python main.py --test-mode

  python main.py --simulation

  python main.py --test-mode --no-grafana

  python main.py --test-mode --no-tui

  python main.py --test-mode --verbose
""",
    )

    mode_group = parser.add_mutually_exclusive_group()

    mode_group.add_argument(
        "--test-mode",
        action="store_true",
        help=(
            "Accelerated paper simulation "
            "for technical testing."
        ),
    )

    mode_group.add_argument(
        "--simulation",
        action="store_true",
        help=(
            "Normal 5-minute paper simulation."
        ),
    )

    parser.add_argument(
        "--no-grafana",
        action="store_true",
        help="Disable Grafana metrics.",
    )

    parser.add_argument(
        "--no-tui",
        action="store_true",
        help="Disable terminal UI.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG logging.",
    )

    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip pre-flight checks.",
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # Mode
    # --------------------------------------------------------

    if args.test_mode:

        simulation = True
        test_mode = True

    else:

        # Default mode is safe paper simulation.
        simulation = True
        test_mode = False

    enable_tui = not args.no_tui
    enable_grafana = not args.no_grafana

    # --------------------------------------------------------
    # Safety assertion
    # --------------------------------------------------------

    if not simulation:

        raise RuntimeError(
            "Only paper simulation is supported."
        )

    if LIVE_TRADING:

        raise RuntimeError(
            "LIVE_TRADING is disabled."
        )

    # --------------------------------------------------------
    # Startup
    # --------------------------------------------------------

    print_banner(
        simulation=simulation,
        test_mode=test_mode,
    )

    setup_logging(
        test_mode=test_mode,
        verbose=args.verbose,
        enable_tui=enable_tui,
    )

    # --------------------------------------------------------
    # Pre-flight
    # --------------------------------------------------------

    if not args.skip_checks:

        ok = preflight(
            simulation=simulation,
            silent=False,
        )

        if not ok:

            console.print()

            console.print(
                Panel(
                    "[bold red]"
                    "Pre-flight checks failed."
                    "[/bold red]\n\n"
                    "The paper trader was not started.",
                    border_style="red",
                    title="[red]ABORTED[/red]",
                )
            )

            sys.exit(1)

    # --------------------------------------------------------
    # Start
    # --------------------------------------------------------

    try:

        start_bot(
            simulation=simulation,
            test_mode=test_mode,
            enable_grafana=enable_grafana,
            enable_tui=enable_tui,
        )

    except KeyboardInterrupt:

        console.print()

        console.print(
            Rule(
                "[yellow]Shutting down[/yellow]",
                style="yellow",
            )
        )

        console.print(
            "[green]Paper trader stopped safely.[/green]"
        )

    except Exception as exc:

        logger.exception(
            f"Paper trader crashed: {exc}"
        )

        console.print()

        console.print(
            Panel(
                f"[bold red]Paper trader stopped[/bold red]\n\n"
                f"{exc}",
                border_style="red",
                title="[red]ERROR[/red]",
            )
        )

        sys.exit(1)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
