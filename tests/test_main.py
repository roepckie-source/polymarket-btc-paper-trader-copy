"""
Safety tests for the Polymarket BTC Paper Trader.

These tests intentionally do not import the complete trading stack.
They inspect the entry point itself so that the safety guarantees
can be tested even when optional trading dependencies are not installed.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = PROJECT_ROOT / "main.py"


def read_main() -> str:
    """Return the complete main.py source."""
    return MAIN_FILE.read_text(encoding="utf-8")


def test_main_exists():
    """The main entry point must exist."""
    assert MAIN_FILE.exists(), "main.py is missing"


def test_paper_trading_is_enabled():
    """Paper trading must be explicitly enabled."""
    source = read_main()

    assert "PAPER_TRADING = True" in source


def test_live_trading_is_disabled():
    """Live trading must be explicitly disabled."""
    source = read_main()

    assert "LIVE_TRADING = False" in source


def test_live_trading_cannot_be_started_from_cli():
    """
    The new project must not expose a --live command.

    Live trading is intentionally removed from this research version.
    """
    source = read_main()

    assert '"--live"' not in source
    assert "'--live'" not in source


def test_only_paper_simulation_is_started():
    """
    The bot runner must be called with simulation=True.

    This prevents an accidental switch to live execution through
    the central entry point.
    """
    source = read_main()

    assert "simulation=True" in source


def test_no_private_key_is_required_by_main():
    """
    main.py must not read a private key directly.
    """
    source = read_main()

    assert "POLYMARKET_PK" not in source
    assert "PRIVATE_KEY" not in source


def test_no_wallet_is_required_by_main():
    """
    main.py must not require a wallet address to start paper mode.
    """
    source = read_main()

    assert "POLYMARKET_FUNDER" not in source


def test_supported_modes_are_paper_only():
    """
    The documented CLI modes must remain paper/simulation modes.
    """
    source = read_main()

    assert "--test-mode" in source
    assert "--simulation" in source


def test_python_requirement_is_documented():
    """
    The project targets Python 3.14+.
    """
    pyproject = PROJECT_ROOT / "pyproject.toml"

    assert pyproject.exists()

    source = pyproject.read_text(encoding="utf-8")

    assert 'requires-python = ">=3.14"' in source


def test_environment_template_contains_no_real_credentials():
    """
    The public example environment file must not contain
    an actual private key or API secret.
    """
    env_file = PROJECT_ROOT / ".env.example"

    assert env_file.exists()

    source = env_file.read_text(encoding="utf-8")

    assert "POLYMARKET_PK=" in source
    assert "POLYMARKET_API_KEY=" in source
    assert "POLYMARKET_API_SECRET=" in source

    # The example values must remain empty.
    assert "POLYMARKET_PK=\n" in source
    assert "POLYMARKET_API_KEY=\n" in source
    assert "POLYMARKET_API_SECRET=\n" in source
