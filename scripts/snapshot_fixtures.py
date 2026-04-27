"""One-shot script to capture today's akshare data into tests/fixtures/{date}/.

Usage:
    python scripts/snapshot_fixtures.py 2026-04-25
"""
import sys
from pathlib import Path
from youzi_agent.data.akshare_client import AkshareClient


def main(date: str):
    out_dir = Path("tests/fixtures") / date
    out_dir.mkdir(parents=True, exist_ok=True)
    cli = AkshareClient(cache_dir=out_dir.parent)  # writes under tests/fixtures/{date}/
    print(f"snapshotting {date} → {out_dir}")
    cli.limit_up_pool(date)
    prev = (__import__("pandas").Timestamp(date) - __import__("pandas").Timedelta(days=1)).strftime("%Y-%m-%d")
    cli.limit_up_pool(prev)
    cli.blast_pool(prev)
    cli.index_daily("sh000001")
    cli.index_daily("sz399006")
    cli.market_activity(date)
    cli.code_list(date)
    cli.concept_list_ths(date)
    print("done")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else __import__("datetime").date.today().isoformat())
