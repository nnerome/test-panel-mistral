"""Export "down" feedback as JSONL in the evals/conversations.jsonl shape, plus status=to_review.

Run:  DATABASE_URL=... uv run --no-sync python evals/export_feedback.py [--out evals/feedback_export.jsonl]

The existing evaluation set (evals/conversations.jsonl) is never modified: output goes to a
separate file (default evals/feedback_export.jsonl), gitignored or committed at your choice.
Each line keeps the runner's keys (id, category, message, expected_intent, expected_tools,
expect) so the exported cases can be replayed, and adds status/feedback fields for review."""

import argparse
import asyncio
import json
from pathlib import Path

from db import accessors as acc
from db.engine import get_session_maker

ROOT = Path(__file__).resolve().parents[1]


async def export(out_path: Path) -> int:
    async with get_session_maker()() as session:
        downs = await acc.feedback.list_recent(session, rating="down", limit=100_000)
        turns = {t.correlation_id: t for t in await acc.turn_records.list_all(session)}
    lines = []
    for fb in downs:
        turn = turns.get(fb.correlation_id)
        lines.append(
            {
                "id": f"fb-{str(fb.id).replace('-', '')[:8]}",
                "category": "feedback_down",
                "message": fb.message_excerpt or "",
                "expected_intent": turn.intent if turn else "unknown",
                "expected_tools": [],
                "expect": {"review": "down"},
                "status": "to_review",
                "feedback_id": str(fb.id),
                "correlation_id": fb.correlation_id,
                "reason": fb.reason,
                "comment": fb.comment,
                "answer_excerpt": fb.answer_excerpt,
            }
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    return len(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "evals" / "feedback_export.jsonl")
    args = parser.parse_args()
    count = asyncio.run(export(args.out))
    print(f"exported {count} down-feedback rows -> {args.out}")


if __name__ == "__main__":
    main()
