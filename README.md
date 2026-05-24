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
Copy `.env.example` and fill in real values.

## Docker

A minimal image is provided for CI smoke checks and headless deployment to
a Linux VM. The local venv is still the primary dev environment.

```bash
docker build -t episodic-pivot .
docker run --rm episodic-pivot                    # runs `pytest`
docker run --rm -it --entrypoint bash episodic-pivot
docker run --rm --env-file .env episodic-pivot ...   # later phases
```

`.dockerignore` keeps `.env`, the venv, caches, and the planning docs out of
the build context — secrets are never baked into the image.
