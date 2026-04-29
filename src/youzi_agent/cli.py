"""CLI entry: python -m youzi_agent [date] [--no-llm] [--refresh] [--json]."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from .graph import build_graph


def _default_date() -> str:
    today = _dt.date.today()
    while today.weekday() >= 5:
        today -= _dt.timedelta(days=1)
    return today.isoformat()


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="youzi-agent",
                                description="A-share retail-style multi-agent trading research")
    p.add_argument("date", nargs="?", default=None, help="trading date YYYY-MM-DD (default: today)")
    p.add_argument("--no-llm", action="store_true", help="skip LLM calls, use rule fallbacks")
    p.add_argument("--refresh", action="store_true", help="bypass on-disk cache")
    p.add_argument("--json", action="store_true", help="emit final state as JSON to stdout")
    p.add_argument("--checkpoint", default="checkpoints.db")
    p.add_argument("--runs-dir", default="runs")
    return p


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    os.environ["YOUZI_AUTO_RESUME"] = "1"
    args = _build_parser().parse_args(argv)
    date = args.date or _default_date()
    if args.refresh:
        os.environ["YOUZI_REFRESH"] = "1"
    graph = build_graph(checkpoint_path=args.checkpoint)
    thread_id = f"{date}-{uuid.uuid4().hex[:8]}"
    state = graph.invoke(
        {"target_date": date, "use_llm": not args.no_llm},
        config={"configurable": {"thread_id": thread_id}},
    )
    if args.json:
        from .reporting import state_to_json
        print(json.dumps(state_to_json(state), ensure_ascii=False, indent=2))
    else:
        report_md = Path(args.runs_dir) / date / "report.md"
        if report_md.exists():
            print(report_md.read_text())
    if state.get("errors"):
        return 2
    if state.get("plan") is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
