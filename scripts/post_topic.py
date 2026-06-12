#!/usr/bin/env python3
"""post_topic.py — Generate post drafts about a specific topic without a session.

This script supports the `/post [about]` feature. It:
1. Reads the topic argument
2. Searches wiki pages for relevant context
3. Builds a "mini-session" log
4. Runs the content pipeline state machine

Usage:
    ./scripts/post_topic.py <topic>
    ./scripts/post_topic.py <topic> --dry-run  # Show what would be done

Run this via: pipeline.sh content post about "<topic>"
or:             engine.py content post about "<topic>"
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from state_machine import (
    StateMachine,
    read_wiki_state,
    write_wiki_state,
    acquire_lock,
    release_lock,
    VAULT,
)

from logger import logged


@logged()
def search_wiki(topic: str) -> dict:
    """Search wiki pages for relevant context about the topic.
    Returns {page_name: {summary, content_preview, filepath}}."""
    topic_lower = topic.lower()
    results = {}

    for dirname in ["concepts", "entities"]:
        dirpath = VAULT / dirname
        if not dirpath.exists():
            continue
        for f in sorted(dirpath.glob("*.md")):
            content = f.read_text()
            fname_lower = f.stem.lower().replace("-", " ")

            # Score: title match > body mention
            title_match = topic_lower in fname_lower
            body_match = topic_lower in content.lower()

            if title_match or body_match:
                preview = content[:500]  # first 500 chars
                first_line = content.split("\n")[0].strip("# ")
                results[f.stem] = {
                    "filepath": str(f),
                    "type": dirname,
                    "title": first_line or f.stem,
                    "preview": preview,
                    "score": 2 if title_match else 1,
                }

    return dict(sorted(results.items(), key=lambda x: x[1]["score"], reverse=True))


@logged()
def build_topic_session(topic: str, wiki_results: dict) -> str:
    """Build a mini-session log entry for the topic."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    page_count = len(wiki_results)
    top_pages = list(wiki_results.keys())[:5]

    session = f"""---
type: topic-request
topic: {topic}
created: {now}
wiki_pages_found: {page_count}
---

# Topic Request: {topic}

This is an LLM-generated session context for the topic: **{topic}**.

## Relevant Wiki Pages

{chr(10).join(f'- [[{p}]]: {wiki_results[p]["title"]}' for p in top_pages)}

## Instructions

1. Read the strategy pages (commands/post.md for the full list)
2. Classify this topic: what archetype (S1-S10), what vertical, what funnel stage, what ICP layer?
3. Run the 4 strategic questions
4. Draft posts in the user's voice using templates/
5. Pass all gates before saving to queue

## Sensitivity Check

- Does this topic contain internal architecture?
- Does it leak strategy or schema details?
- Is it in the user's domain?
"""
    return session


@logged()
def print_topic_context(topic: str, wiki_results: dict) -> None:
    """Print topic context for the LLM to use."""
    print("═══ Topic Post: /post about", topic, "═══")
    print()
    if not wiki_results:
        print(f"⚠ No wiki pages found about '{topic}'.")
        print("  The LLM will need to work from general knowledge.")
        print()
        return

    print(f"Found {len(wiki_results)} relevant wiki page(s):")
    print()
    for name, info in wiki_results.items():
        icon = "●" if info["score"] == 2 else "○"
        print(f"  {icon} [[{name}]] ({info['type']})")
        print(f"      {info['title'][:80]}")
    print()
    print("Top pages to read:")
    for name in list(wiki_results.keys())[:3]:
        print(f"  - concepts/{name}.md" if wiki_results[name]["type"] == "concepts" else f"  - entities/{name}.md")
    print()


def main():
    parser = argparse.ArgumentParser(description="Generate posts about a topic")
    parser.add_argument("topic", nargs="*", help="Topic to write about")
    parser.add_argument("--dry-run", action="store_true", help="Show context without generating")
    args = parser.parse_args()

    topic = " ".join(args.topic) if args.topic else ""
    if not topic:
        print("Usage: post_topic.py <topic>")
        print("Example: post_topic.py second brain")
        return 1

    # Search wiki for relevant context
    wiki_results = search_wiki(topic)

    if args.dry_run:
        print_topic_context(topic, wiki_results)
        return 0

    # Acquire lock and start pipeline
    if not acquire_lock():
        print("ERROR: Another pipeline is running.", file=sys.stderr)
        return 1

    try:
        state = read_wiki_state()
        state["loop"] = "CONTENT"
        state["current_state"] = "SESSION_CAPTURE"
        state["pending_action"] = f"post about {topic}"
        write_wiki_state(state)

        print_topic_context(topic, wiki_results)

        # Create a mini-session log
        session_log = build_topic_session(topic, wiki_results)
        session_dir = VAULT / "content" / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / f"{datetime.now().strftime('%Y-%m-%d')}-topic-{topic.lower().replace(' ', '-')[:30]}.md"
        session_file.write_text(session_log)
        print(f"Session context saved: content/sessions/{session_file.name}")
        print()

        print("=== NEXT STEPS ===")
        print("The LLM should now:")
        print(f"  1. Read wiki pages about '{topic}' (listed above)")
        print("  2. Load strategy pages (see commands/post.md)")
        print("  3. Classify the topic (archetype, vertical, funnel stage)")
        print("  4. Run the 4 strategic questions")
        print("  5. Draft posts using templates/")
        print("  6. Pass all gates before saving to content/queue/")
        print()
        print("After drafting, run: engine.py content queue")

    finally:
        release_lock()

    return 0


if __name__ == "__main__":
    sys.exit(main())
