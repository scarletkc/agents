#!/usr/bin/env python3
"""Profile a personal writing corpus exported from Telegram Desktop.

The export itself stays out of the repository. Point the tool at a local
config file holding the export path, the sender ids that belong to you, and
any chats to drop before analysis:

    {
      "export": "/path/to/DataExport/result.json",
      "self_ids": ["user123456789"],
      "exclude_chats": ["a chat name"]
    }

Usage:
    python scripts/telegram_corpus.py stats --config .telegram-corpus.json
    python scripts/telegram_corpus.py sample --config .telegram-corpus.json

`stats` prints aggregate ratios only. `sample` prints candidate messages for
manual review, so treat its output as private until you have redacted it.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class CorpusError(ValueError):
    """Raised when the export or the config cannot be used."""


EMOJI = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf"
    "\U0001f000-\U0001f2ff⬀-⯿️←-⇿]"
)
CJK = re.compile(r"[一-鿿]")
KANA = re.compile(r"[぀-ヿ]")
LATIN = re.compile(r"[A-Za-z]")
LATIN_RUN = re.compile(r"[A-Za-z][A-Za-z0-9._-]+")
# A message made only of these entities carries no prose worth studying.
STRUCT_ONLY_ENTITIES = frozenset(
    {"bot_command", "link", "mention", "hashtag", "email", "phone", "cashtag"}
)
# Entities that usually drag identifying details along with them.
IDENTIFYING_ENTITIES = frozenset({"link", "text_link", "mention", "email", "phone"})
# Structure that a person does not type by hand in a chat box.
PASTE_MARKERS = re.compile(
    r"[—⸻✅⚠✔▪]|\*\*|^#{1,4} |\n#{1,4} "
    r"|\n\d[)）.．] |\n[-*] "
)
PASTE_LENGTH = 200
PASTE_BLOCK_LENGTH = 60
PASTE_BLOCK_LINES = 2

LENGTH_BUCKETS = ((0, 5), (6, 15), (16, 30), (31, 60), (61, 1_000_000))


@dataclass(frozen=True)
class Message:
    """One message written by the corpus owner."""

    chat: str
    date: str
    text: str
    entity_kinds: frozenset[str]
    is_reply: bool
    edited: bool
    sender: str


def flatten_text(value: object) -> tuple[str, frozenset[str]]:
    """Return the plain text of a Telegram `text` field and its entity kinds.

    The field is either a string or a list mixing strings with entity dicts.
    """
    if isinstance(value, str):
        return value, frozenset()
    if value is None:
        return "", frozenset()
    if not isinstance(value, list):
        raise CorpusError(f"unexpected text field of type {type(value).__name__}")

    parts: list[str] = []
    kinds: set[str] = set()
    for segment in value:
        if isinstance(segment, str):
            parts.append(segment)
            continue
        if not isinstance(segment, dict):
            raise CorpusError(
                f"unexpected text segment of type {type(segment).__name__}"
            )
        parts.append(str(segment.get("text", "")))
        kind = segment.get("type")
        if kind:
            kinds.add(str(kind))
    return "".join(parts), frozenset(kinds)


def looks_pasted(text: str) -> bool:
    """Heuristic for third-party content pasted in by hand.

    Telegram only marks messages forwarded through the client, so anything
    copied out of another app arrives looking like the owner wrote it. Long
    or structurally formatted messages are treated as foreign; this trades a
    few false positives for a corpus that is not polluted by AI output.
    """
    if len(text) >= PASTE_LENGTH:
        return True
    if PASTE_MARKERS.search(text):
        return True
    return len(text) >= PASTE_BLOCK_LENGTH and text.count("\n") >= PASTE_BLOCK_LINES


def load_messages(
    export_path: Path,
    self_ids: frozenset[str],
    exclude_chats: frozenset[str] = frozenset(),
) -> tuple[list[Message], collections.Counter]:
    """Read the export and keep only prose the owner typed themselves."""
    try:
        raw = json.loads(export_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CorpusError(f"cannot read {export_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CorpusError(f"{export_path}: invalid JSON: {exc.msg}") from exc

    chats = raw.get("chats")
    if not isinstance(chats, dict) or not isinstance(chats.get("list"), list):
        raise CorpusError(
            f"{export_path}: expected a full account export with a chats list"
        )

    kept: list[Message] = []
    dropped: collections.Counter = collections.Counter()

    for chat in chats["list"]:
        name = str(chat.get("name") or "")
        messages = chat.get("messages") or []
        if name in exclude_chats:
            dropped["excluded_chat"] += len(messages)
            continue

        for message in messages:
            if message.get("type") != "message":
                dropped["service"] += 1
                continue
            sender = str(message.get("from_id") or "")
            if sender not in self_ids:
                dropped["other_sender"] += 1
                continue
            if message.get("forwarded_from") or message.get("forwarded_from_id"):
                dropped["forwarded"] += 1
                continue

            text, kinds = flatten_text(message.get("text"))
            text = text.strip()
            if not text:
                dropped["media_only"] += 1
                continue
            if kinds and kinds <= STRUCT_ONLY_ENTITIES:
                dropped["structural_only"] += 1
                continue
            if text.startswith("/"):
                dropped["bot_command"] += 1
                continue
            if not (
                CJK.search(EMOJI.sub("", text))
                or KANA.search(text)
                or LATIN.search(text)
            ):
                dropped["no_words"] += 1
                continue

            kept.append(
                Message(
                    chat=name,
                    date=str(message.get("date") or ""),
                    text=text,
                    entity_kinds=kinds,
                    is_reply=bool(message.get("reply_to_message_id")),
                    edited=bool(message.get("edited")),
                    sender=sender,
                )
            )

    if not kept:
        raise CorpusError(
            f"{export_path}: no messages matched self_ids {sorted(self_ids)}"
        )
    return kept, dropped


def _percentile(sorted_values: list[int], fraction: float) -> int:
    index = min(int(len(sorted_values) * fraction), len(sorted_values) - 1)
    return sorted_values[index]


def _burst_ratio(messages: list[Message], within_seconds: int = 60) -> float:
    """Share of messages sent within a minute of the previous one, per chat."""
    by_chat: dict[str, list[datetime]] = collections.defaultdict(list)
    for message in messages:
        try:
            by_chat[message.chat].append(datetime.fromisoformat(message.date))
        except ValueError:
            continue

    pairs = bursts = 0
    for stamps in by_chat.values():
        stamps.sort()
        for earlier, later in zip(stamps, stamps[1:]):
            pairs += 1
            if (later - earlier).total_seconds() < within_seconds:
                bursts += 1
    return bursts / pairs if pairs else 0.0


def profile(messages: list[Message]) -> dict:
    """Compute the ratios used to calibrate the voice rules."""
    if not messages:
        raise CorpusError("cannot profile an empty corpus")

    texts = [message.text for message in messages]
    total = len(texts)
    lengths = sorted(len(text) for text in texts)

    def share(pattern: str) -> float:
        compiled = re.compile(pattern)
        return sum(1 for text in texts if compiled.search(text)) / total

    runs = [run for text in texts for run in LATIN_RUN.findall(text)]
    lowercase_runs = sum(1 for run in runs if run.islower())

    buckets = collections.Counter()
    for length in lengths:
        for low, high in LENGTH_BUCKETS:
            if low <= length <= high:
                buckets[f"{low}-{high}" if high < 1_000_000 else f"{low}+"] += 1
                break

    return {
        "messages": total,
        "chats": len({message.chat for message in messages}),
        "length": {
            f"p{int(fraction * 100)}": _percentile(lengths, fraction)
            for fraction in (0.25, 0.5, 0.75, 0.9, 0.95)
        }
        | {"max": lengths[-1]},
        "length_buckets": dict(buckets),
        "punctuation": {
            "no_trailing_mark": share(r"[^。，、！？!?,.…~～)）\"']$"),
            "no_marks_at_all": 1 - share(r"[。，、；：！？!?,.]"),
            "full_stop": share(r"。"),
            "comma": share(r"，"),
            "colon": share(r"[：:]"),
            "semicolon": share(r"[；;]"),
            "em_dash": share(r"—"),
            "curly_quotes": share(r"[“”]"),
            "bold_markup": share(r"\*\*"),
            "emoji": sum(1 for text in texts if EMOJI.search(text)) / total,
            "space_as_pause": share(r"[一-鿿] +[一-鿿]"),
            "question_mark": share(r"[?？]"),
            "repeated_question_marks": share(r"[?？]{2,}"),
            "exclamation_mark": share(r"[!！]"),
            "repeated_exclamations": share(r"[!！]{2,}"),
            "binary_reversal": share(r"不是.{1,12}(?:而是|是)"),
        },
        "rhythm": {
            "interrogative": share(r"[?？]|什么|为什么|怎么|有没有|是不是|能不能|吗"),
            "repeated_character": share(r"(.)\1{2,}"),
            "burst_within_60s": _burst_ratio(messages),
            "reply": sum(1 for message in messages if message.is_reply) / total,
            "edited": sum(1 for message in messages if message.edited) / total,
        },
        "latin": {
            "messages_with_latin": share(r"[A-Za-z]"),
            "adjacent_to_cjk": share(r"[一-鿿][A-Za-z]|[A-Za-z][一-鿿]"),
            "runs": len(runs),
            "all_lowercase_share": lowercase_runs / len(runs) if runs else 0.0,
        },
    }


def render_profile(data: dict, dropped: collections.Counter, pasted: int) -> str:
    """Render the profile as plain text, safe to paste into a pull request."""
    lines = [
        f"messages: {data['messages']} across {data['chats']} chats",
        f"dropped in cleaning: "
        + ", ".join(f"{key}={value}" for key, value in dropped.most_common()),
        f"removed as pasted: {pasted}",
        "",
        "length: "
        + ", ".join(f"{key}={value}" for key, value in data["length"].items()),
        "buckets: "
        + ", ".join(f"{key}={value}" for key, value in data["length_buckets"].items()),
    ]
    for section in ("punctuation", "rhythm", "latin"):
        lines.append("")
        lines.append(f"[{section}]")
        for key, value in data[section].items():
            if isinstance(value, float):
                lines.append(f"  {key}: {value * 100:.1f}%")
            else:
                lines.append(f"  {key}: {value}")
    return "\n".join(lines)


def select_samples(
    messages: list[Message],
    *,
    min_length: int = 10,
    max_repeats: int = 2,
    per_bucket: int = 40,
) -> list[Message]:
    """Pick review candidates, spread across length buckets.

    Messages repeated more than `max_repeats` times across the corpus are
    canned replies rather than voice samples. Anything carrying a link,
    mention, or other identifying entity is left out to keep the review from
    turning into a redaction exercise.
    """
    counts = collections.Counter(message.text for message in messages)
    seen: set[str] = set()
    by_bucket: dict[tuple[int, int], list[Message]] = collections.defaultdict(list)

    for message in messages:
        text = message.text
        if len(text) < min_length or counts[text] > max_repeats or text in seen:
            continue
        if message.entity_kinds & IDENTIFYING_ENTITIES:
            continue
        if looks_pasted(text):
            continue
        seen.add(text)
        for low, high in LENGTH_BUCKETS:
            if low <= len(text) <= high:
                by_bucket[(low, high)].append(message)
                break

    selected: list[Message] = []
    for bounds in LENGTH_BUCKETS:
        bucket = by_bucket.get(bounds, [])
        if not bucket:
            continue
        # Even stride keeps the spread across time instead of front-loading.
        stride = max(1, len(bucket) // per_bucket)
        selected.extend(bucket[::stride][:per_bucket])
    return selected


def render_samples(samples: list[Message]) -> str:
    """Render candidates as a checklist for manual selection."""
    lines = [
        "# 候选样本",
        "",
        "逐条判断有没有新习惯值得提炼成 surface-profiles.md 的 Chat 规则。",
        "这份文件包含聊天原文，不要提交进仓库。",
        "",
    ]
    for index, message in enumerate(samples, start=1):
        text = message.text.replace("\n", " / ")
        lines.append(f"{index:3d}. [{len(message.text)}字 {message.date[:7]}] {text}")
    return "\n".join(lines)


def load_config(path: Path) -> dict:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CorpusError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CorpusError(f"{path}: invalid JSON: {exc.msg}") from exc
    if not isinstance(config, dict):
        raise CorpusError(f"{path}: expected a JSON object")
    return config


def resolve_settings(args: argparse.Namespace) -> tuple[Path, frozenset[str], frozenset[str]]:
    config = load_config(args.config) if args.config else {}

    export = args.export or config.get("export")
    if not export:
        raise CorpusError("no export path given; use --export or config.export")

    self_ids = frozenset(args.self_id or config.get("self_ids") or ())
    if not self_ids:
        raise CorpusError("no sender ids given; use --self-id or config.self_ids")

    exclude = frozenset(args.exclude_chat or config.get("exclude_chats") or ())
    return Path(export), self_ids, exclude


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "command", choices=("stats", "sample"), help="report ratios or list candidates"
    )
    parser.add_argument("--config", type=Path, help="path to a local JSON config")
    parser.add_argument("--export", help="path to result.json (overrides config)")
    parser.add_argument(
        "--self-id", action="append", help="sender id to keep (repeatable)"
    )
    parser.add_argument(
        "--exclude-chat", action="append", help="chat name to drop (repeatable)"
    )
    parser.add_argument(
        "--keep-pasted",
        action="store_true",
        help="stats only: skip the pasted-content filter",
    )
    parser.add_argument(
        "--min-length", type=int, default=10, help="sample only: shortest candidate"
    )
    parser.add_argument(
        "--per-bucket", type=int, default=40, help="sample only: candidates per bucket"
    )
    parser.add_argument("--out", type=Path, help="write to a file instead of stdout")
    args = parser.parse_args(argv)

    try:
        export, self_ids, exclude = resolve_settings(args)
        messages, dropped = load_messages(export, self_ids, exclude)
        pasted = sum(1 for message in messages if looks_pasted(message.text))
        if not args.keep_pasted:
            messages = [m for m in messages if not looks_pasted(m.text)]

        if args.command == "stats":
            output = render_profile(profile(messages), dropped, pasted)
        else:
            output = render_samples(
                select_samples(
                    messages,
                    min_length=args.min_length,
                    per_bucket=args.per_bucket,
                )
            )
    except CorpusError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.out:
        args.out.write_text(output + "\n", encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
