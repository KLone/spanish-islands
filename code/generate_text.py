"""
generate_text.py

Generates a plain text reference file from sentences.json.
Output: islands.txt

Usage:
  python3 generate_text.py
"""

import json

INPUT_FILE  = "sentences.json"
OUTPUT_FILE = "islands.txt"


def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        cards = json.load(f)

    # Group by island
    islands = {}
    for card in cards:
        key = (card["island_num"], card["island_slug"])
        islands.setdefault(key, []).append(card)

    lines = []
    for (num, slug), cards in sorted(islands.items()):
        lines.append(f"{'=' * 60}")
        lines.append(f"Island {num:02d}: {slug.replace('-', ' ').title()}")
        lines.append(f"{'=' * 60}")
        lines.append("")

        for card in cards:
            label = f"{card['card_type'].title()} {card['card_num']}"
            lines.append(f"[{label}]")
            lines.append(f"Q (EN): {card['q_en']}")
            lines.append(f"Q (ES): {card['q_es']}")
            lines.append("")
            lines.append(f"A (EN): {card['a_en']}")
            lines.append(f"A (ES): {card['a_es']}")
            lines.append("")

    output = "\n".join(lines)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"Written to {OUTPUT_FILE} ({len(cards)} cards across {len(islands)} island(s)).")


if __name__ == "__main__":
    main()
