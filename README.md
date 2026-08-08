# Daily Quant Decision Brief

Multi-asset quant market report designed for day-start decision making.

**Features**
- Global multi-asset coverage (Equities, Rates, Credit, FX, Commodities, Vol, Crypto, EM)
- Rich risk gauges (Risk-On/Off, Term Premium, Vol Risk Premium, Carry/Basis, Liquidity, etc.)
- Emerging Markets dashboard
- Trending Themes & Fund Flow Radar (AI, Semiconductors, Rare Earths, Space, etc.)
- Scenario analysis + historical analogs + research anchors
- Responsive HTML output (mobile-first, light JS)

## Status
Plan locked (2026-08-08). Implementation in progress.

## Project Structure
```
daily-quant-decision-brief/
├── data/               # Cached market data
├── docs/               # Specifications & locked plan
├── notebooks/          # Exploration & research
├── output/             # Generated HTML reports
├── src/
│   ├── gauges/         # Risk gauge calculations
│   ├── pipeline/       # Data download & cleaning
│   ├── report/         # HTML generation
│   └── themes/         # Thematic radar logic
├── templates/          # HTML / Jinja templates
└── README.md
```

## Notion Hub
Project documentation lives in Notion: [Daily Quant Decision Brief](https://app.notion.com/p/3b6ed415e65b8119b598dcea065a8dea)

## Quick Start (coming soon)
```bash
python -m src.pipeline.update_data
python -m src.report.generate
```

## License
Private – for personal use.
