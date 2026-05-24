# Episodic Pivot

Automated swing-trading system for the **Episodic Pivot** setup: a stock gaps up
hard on a genuine catalyst, then breaks out of its opening range on heavy volume
and trends for days to weeks.

## Documents

- [`EpisodicPivot.md`](./EpisodicPivot.md) — phased build plan (Phase 0–7).
- [`CLAUDE.md`](./CLAUDE.md) — hard constraints and locked strategy decisions.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # installs the project in editable mode + dev tools

pytest          # run the test suite
ruff check      # lint
```

Secrets (FMP, Alpaca, OpenRouter keys) live in `.env`, which is gitignored.
Copy `.env.example` (created in Phase 0.2) and fill in real values.
