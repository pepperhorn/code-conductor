from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from conductor.config import ConfigError, load_config


async def run(config_path: Path) -> None:
    config = load_config(config_path)
    from conductor.app import run_app

    await run_app(config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Code Conductor control bot")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Path to config.toml",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run(args.config))
    except ConfigError as exc:
        raise SystemExit(f"configuration error: {exc}") from exc


if __name__ == "__main__":
    main()
