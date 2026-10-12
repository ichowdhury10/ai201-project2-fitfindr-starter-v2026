"""
Score a run_eval.py run against criteria.md. ← added in unit 4

    python score_run.py                       scores the newest results/run_*.json
    python score_run.py results/run_X.json    scores a specific run

run_eval.py runs the scenarios and saves every try's session as JSON next to
its markdown report. This reads those exact tries and applies each criterion's
"How to check" line from criteria.md, one check per line of the criterion, so a
FAIL always says which part failed. It prints the run-log table rows for the
README.

It doesn't run the agent, and it doesn't change anything. It only reads.
"""

import json
import re
import sys
from pathlib import Path

from tools import price_text

RESULTS = Path(__file__).parent / "results"

# criterion number → passes needed out of 5, from criteria.md
TARGETS = {1: 4, 2: 5, 3: 5, 4: 4, 5: 4}
LABELS = {
    1: "Matching query completes all three tools",
    2: "Impossible query stops before suggest_outfit",
    3: "Item search found is the item both model tools receive",
    4: "Fit card has exact price, platform, 2–4 sentences, ≤80 words",
    5: "Empty wardrobe completes, outfit never says your/yours",
}
PLATFORMS = {"depop": "Depop", "thredup": "thredUP", "poshmark": "Poshmark"}


def count_sentences(text: str) -> int:
    """Sentence-ending . ! ? (a run like '...' or '!!' counts once). Emoji don't."""
    return len(re.findall(r"[.!?]+(?=\s|$)", text.strip()))


def check_1(t):
    s = t["session"]
    tools = [c["tool"] for c in s["tool_calls"]]
    problems = []
    if s["error"] is not None:
        problems.append(f"error set: {s['error'][:60]}")
    if not (isinstance(s["fit_card"], str) and s["fit_card"].strip()):
        problems.append("no fit card")
    if tools != ["search_listings", "suggest_outfit", "create_fit_card"]:
        problems.append(f"tool_calls were {tools}")
    return problems


def check_2(t):
    s = t["session"]
    tools = {c["tool"] for c in s["tool_calls"]}
    error = s["error"] or ""
    problems = []
    if s["fit_card"] is not None or s["outfit_suggestion"] is not None:
        problems.append("outfit or fit card was produced")
    if tools & {"suggest_outfit", "create_fit_card"}:
        problems.append("a model tool was called")
    if t["model_calls"] != 0:
        problems.append(f"{t['model_calls']} model calls")
    if not re.search(r"\b(price|size|words)\b", error, re.IGNORECASE):
        problems.append(f"message doesn't name what to change: {error[:60]!r}")
    return problems


def check_3(t):
    s = t["session"]
    if s["error"] is not None or not s["selected_item"]:
        return [f"run didn't reach the model tools: {s['error']}"]
    ids = {
        "selected_item": s["selected_item"]["id"],
        "search_results[0]": s["search_results"][0]["id"],
    }
    for call in s["tool_calls"]:
        if call["tool"] in ("suggest_outfit", "create_fit_card"):
            ids[call["tool"]] = call.get("item_id")
    problems = []
    for tool in ("suggest_outfit", "create_fit_card"):
        if tool not in ids:
            problems.append(f"no {tool} call recorded")
    if len(set(ids.values())) != 1:
        problems.append(f"ids differ: {ids}")
    return problems


def check_4(t):
    s = t["session"]
    card = s["fit_card"]
    if not card:
        return [f"no fit card: {s['error']}"]
    item = s["selected_item"]
    price = price_text(item["price"])
    platform = PLATFORMS.get(item["platform"].lower(), item["platform"])
    words = len(card.split())
    sentences = count_sentences(card)
    problems = []
    if price not in card:
        problems.append(f"price {price} missing")
    if platform.lower() not in card.lower():
        problems.append(f"platform {platform} missing")
    if not 2 <= sentences <= 4:
        problems.append(f"{sentences} sentences")
    if words > 80:
        problems.append(f"{words} words")
    return problems


def check_5(t):
    s = t["session"]
    problems = []
    if s["error"] is not None:
        problems.append(f"error set: {s['error'][:60]}")
    if not (isinstance(s["fit_card"], str) and s["fit_card"].strip()):
        problems.append("no fit card")
    hits = re.findall(r"\byours?\b", s["outfit_suggestion"] or "", re.IGNORECASE)
    if hits:
        problems.append(f"outfit says {', '.join(repr(h) for h in hits)}")
    return problems


# Criterion 5 as revised in unit 4 (criteria.md keeps the original above it).
_STYLING_CLAIM = re.compile(
    r"\bI(?:'m|’m| am)?\s+(?:just\s+)?(?:\w+ing|threw|tucked|layered|paired|styled|wore|put)\s+(?:it|this)\b",
    re.IGNORECASE,
)


def check_5r(t):
    s = t["session"]
    problems = []
    if s["error"] is not None:
        problems.append(f"error set: {s['error'][:60]}")
    card = s["fit_card"] or ""
    if not card.strip():
        problems.append("no fit card")
    for match in _STYLING_CLAIM.finditer(card):
        rest = re.split(r"(?<=[.!?])\s", card[match.end():], maxsplit=1)[0]
        if re.search(r"\b(with|over|under|into)\b", rest, re.IGNORECASE):
            problems.append(f"claims an owned piece: {(match.group(0) + rest)[:70]!r}")
    return problems


CHECKS = {1: check_1, 2: check_2, 3: check_3, 4: check_4, 5: check_5}
REVISED = {5: ("5r", check_5r, "REVISED: empty-wardrobe fit card claims no owned piece")}


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        runs = sorted(RESULTS.glob("run_*.json"))
        if not runs:
            sys.exit("No results/run_*.json yet. Run `python run_eval.py --label before` first.")
        path = runs[-1]

    rows = json.loads(path.read_text(encoding="utf-8"))
    print(f"Scoring {path.name}\n")

    table = [
        "| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |",
        "|---|---|---|---|---|---|---|---|",
    ]
    details = []

    def score(name, label, check, target, tries):
        cells = []
        for i, t in enumerate(tries, 1):
            problems = [f"crashed: {t['crashed']}"] if t.get("crashed") else check(t)
            cells.append("FAIL" if problems else "PASS")
            if problems:
                details.append(f"  criterion {name}, try {i}: " + "; ".join(problems))
        passes = cells.count("PASS")
        verdict = "MET" if passes >= target else "MISSED"
        table.append(
            f"| {name}. {label} | {target} of 5 | "
            + " | ".join(cells)
            + f" | {verdict} ({passes}/{len(cells)}) |"
        )

    cards = []
    for row in rows:
        number = row["scenario"].get("criterion")
        cards += [(t["session"] or {}).get("fit_card") for t in row["tries"] if t.get("session")]
        if number not in CHECKS:
            continue
        score(number, LABELS[number], CHECKS[number], TARGETS[number], row["tries"])
        if number in REVISED:
            name, check, label = REVISED[number]
            score(name, label, check, TARGETS[number], row["tries"])

    print("\n".join(table))
    print("\nWhy each FAIL failed:" if details else "\nNo FAILs.")
    print("\n".join(details))

    # Not a criterion: how often the fit cards open the same way.
    cards = [c for c in cards if c]
    openers = {}
    for card in cards:
        opener = " ".join(card.split()[:2])
        openers[opener] = openers.get(opener, 0) + 1
    top = sorted(openers.items(), key=lambda kv: -kv[1])[:3]
    print(f"\nFit card openers across all {len(cards)} cards (not a criterion): "
          + ", ".join(f"{o!r} ×{n}" for o, n in top))


if __name__ == "__main__":
    main()
