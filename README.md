# Polymarket BTC Paper Trader

Paper-trading research project for BTC 5-minute prediction markets on Polymarket.

## Status

🚧 Development / Research

This repository is currently **PAPER TRADING ONLY**.

- No live trading
- No real orders
- No wallet
- No private keys
- No real funds
- No live order execution

## Strategy

The project is based on a multi-signal BTC 5-minute trading architecture.

The research pipeline includes:

- BTC market data
- Polymarket market data
- Order book information
- Tick velocity
- CVD / order-flow information
- Funding and open interest
- Liquidation information
- Price divergence
- Volatility / momentum indicators
- Sentiment
- Spike detection
- Signal fusion
- Machine-learning probability estimation
- Polymarket price vs. estimated probability
- Risk management
- Paper-trade execution
- Trade and feature recording

The original strategy is kept separate from later research and optimization.

## Research principle

No strategy parameters are changed before the original implementation has been reproduced and tested.

The project therefore follows this order:

1. Reproduce the supplied strategy
2. Make the paper-trading pipeline work
3. Collect and validate data
4. Train / validate the ML component
5. Run historical analysis
6. Run forward paper trading
7. Analyze results
8. Only then consider strategy changes

## Safety

Live trading is disabled during the research phase.

Any future live-trading functionality must be explicitly enabled and separately tested.

## Data

The project may create local runtime data such as:

- SQLite databases
- feature records
- signal recordings
- ML models
- logs

Runtime data and credentials must not be committed to GitHub.

## Python

The supplied project targets Python 3.14+.

## Project structure

```text
polymarket-btc-paper-trader/
│
├── bot/
├── core/
├── data_sources/
├── execution/
├── models/
├── config/
├── scripts/
├── tests/
├── data/
│
├── main.py
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
