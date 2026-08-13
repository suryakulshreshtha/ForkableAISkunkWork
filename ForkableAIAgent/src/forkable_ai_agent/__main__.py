"""Allow `python -m forkable_ai_agent ...`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
