"""
The FitFindr planning loop.

This is the file that makes FitFindr an agent rather than a script. It decides
which tool to run next based on what the last one returned.

If your loop calls all three tools no matter what comes back, you have a list
of function calls. A loop looks at the last result before it picks the next
step. **That branch is the graded part of this unit.**

Build and test your three tools in `tools.py` first. Then come here.

    python agent.py          runs both example paths below
"""

import re

import config
import trace
from tools import (
    STOPWORDS,
    create_fit_card,
    normalize_size,
    price_text,
    suggest_outfit,
)
from generate import ModelUnavailable
from mcp_client import call_tool


# ── session state ─────────────────────────────────────────────────────────────

def new_session(query: str, wardrobe: dict) -> dict:
    """
    A fresh session for one user interaction.

    The session is the single source of truth for a run. Every tool result goes
    in here, and the next tool reads it back out.

    You could pass values straight from one call to the next. It would work,
    and you would not be able to test it — you can't print a variable you have
    already overwritten. Going through the session is what makes the state
    visible, and unit 4 has you write a criterion about exactly that.

    Add fields if you need them.
    """
    return {
        "query": query,              # what the user typed
        "parsed": {},                # description / size / max_price you pulled out of it
        "search_results": [],        # everything search_listings returned
        "selected_item": None,       # the one you chose — goes into suggest_outfit
        "wardrobe": wardrobe,        # the user's wardrobe
        "outfit_suggestion": None,   # what suggest_outfit returned
        "fit_card": None,            # what create_fit_card returned
        "error": None,               # set when the run ended early
        "searched": False,           # True once search_listings has run, so [] means "found nothing"
        "tool_calls": [],            # every tool call, in order, with what it was given
    }


# ── query parsing ─────────────────────────────────────────────────────────────

# "under $30", "below 30", "max $25.50", "up to $40" — or a bare "$30".
_PRICE_RE = re.compile(
    r"(?:under|below|less than|max(?:imum)?|up to|at most|no more than|<=?)"
    r"\s*\$?\s*(\d+(?:\.\d{1,2})?)"
    r"|\$\s*(\d+(?:\.\d{1,2})?)",
    re.IGNORECASE,
)

# Only a size that follows the word "size" — "medium wash" is a denim colour in
# this data, so a bare "medium" can't be trusted to mean a size.
_SIZE_RE = re.compile(
    r"\b(?:size|sz)\.?\s*:?\s*"
    r"(us\s*\d+(?:\.\d+)?|w\d{2}|\d+(?:\.\d+)?|x{0,3}[sl]|m"
    r"|small|medium|large|x-?small|x-?large|extra (?:small|large))\b",
    re.IGNORECASE,
)

_FILLER = STOPWORDS | {"dollars", "dollar", "bucks"}


def parse_query(query: str) -> dict:
    """
    Pull a description, a size and a max_price out of plain text, with regex.

    "vintage graphic tee under $30, size M"
        → {"description": "vintage graphic tee", "size": "M", "max_price": 30.0}
    """
    rest = query
    max_price = None
    size = None

    price = _PRICE_RE.search(rest)
    if price:
        max_price = float(price.group(1) or price.group(2))
        rest = rest[: price.start()] + " " + rest[price.end():]

    size_match = _SIZE_RE.search(rest)
    if size_match:
        size = normalize_size(size_match.group(1))
        rest = rest[: size_match.start()] + " " + rest[size_match.end():]

    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", rest)
    description = " ".join(w.lower() for w in words if w.lower() not in _FILLER)

    return {"description": description, "size": size, "max_price": max_price}


# ── search, through MCP ───────────────────────────────────────────────────────

def _search(session: dict, description: str, size, max_price, note: str = "") -> list[dict]:
    """
    Every search goes through the MCP server (mcp_server.py), never a direct
    call to tools.search_listings. Each call is recorded in the session.
    """
    inputs = {"description": description, "size": size, "max_price": max_price}
    record = {"tool": "search_listings", "inputs": inputs}
    if note:
        record["note"] = note
    session["tool_calls"].append(record)
    return call_tool("search_listings", inputs)


# ── the empty-search message ──────────────────────────────────────────────────

def _explain_empty(session: dict) -> str:
    """
    Say what to change, not just that nothing matched. Re-run the search with
    one filter dropped at a time to find out which one emptied it.
    """
    parsed = session["parsed"]
    desc, size, max_price = parsed["description"], parsed["size"], parsed["max_price"]

    if not desc:
        return (
            "Your search had a size or price but no item words, so there was "
            "nothing to match on. Say what you're looking for — for example "
            "'graphic tee under $30' or 'denim jacket size M'."
        )

    asked = f'"{desc}"'
    if size:
        asked += f" in size {size}"
    if max_price is not None:
        asked += f" under {price_text(max_price)}"

    def retry(retry_size, retry_price):
        return _search(session, desc, retry_size, retry_price,
                       note="explaining the empty search")

    if max_price is not None:
        hits = retry(size, None)
        if hits:
            best = hits[0]
            return (
                f"No listings matched {asked}. The price is what's ruling them "
                f"out — the closest match, \"{best['title']}\", is "
                f"{price_text(best['price'])}. Raise your max price to "
                f"{price_text(best['price'])} to see it."
            )

    if size:
        hits = retry(None, max_price)
        if hits:
            sizes = ", ".join(sorted({h["size"] for h in hits})[:4])
            return (
                f"No listings matched {asked}. The size is what's ruling them "
                f"out — matches come in {sizes}. Try one of those sizes, or "
                f"leave the size out."
            )

    if size and max_price is not None:
        hits = retry(None, None)
        if hits:
            best = hits[0]
            return (
                f"No listings matched {asked}. The size and the price together "
                f"rule everything out — the closest match, \"{best['title']}\", "
                f"is size {best['size']} at {price_text(best['price'])}. Drop "
                f"the size and raise your max price."
            )

    return (
        f"No listings matched {asked}. Nothing in the listings matches the "
        f'words "{desc}" at any size or price, so changing the filters won\'t '
        "help. Try broader words: a category (tee, jeans, jacket, sneakers) or "
        "a style (vintage, y2k, grunge, cottagecore)."
    )


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Run the loop once and return the finished session.

    Args:
        query:    what the user asked for, in plain language
                  (e.g. "vintage graphic tee under $30, size M").
        wardrobe: a wardrobe dict — get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py.

    Returns:
        The session dict. **Check session["error"] first** — if it isn't None,
        the run ended early and the later fields will still be None.

    Each time round, _next_step() reads the session and names one step. The
    branch is "stop_empty": an empty search ends the run before suggest_outfit
    is ever called.

    ─────────────────────────────────────────────────────────────────────────
    IN UNIT 4 you come back and add two things:

      • Trace calls. One per step. `trace.step("search_listings", inputs=...,
        returned=...)` — see trace.py. Your README needs the output.

      • A handler for ModelUnavailable, so a bad key produces a message rather
        than a stack trace. The import is already at the top of this file.
    """
    session = new_session(query, wardrobe)
    count = 0

    while True:
        count += 1
        trace.check_iterations(count)
        step = _next_step(session)

        if step == "parse":
            session["parsed"] = parse_query(session["query"])

        elif step == "search":
            parsed = session["parsed"]
            session["search_results"] = _search(
                session, parsed["description"], parsed["size"], parsed["max_price"]
            )
            session["searched"] = True

        elif step == "stop_empty":
            session["error"] = _explain_empty(session)
            return session

        elif step == "select":
            session["selected_item"] = session["search_results"][0]

        elif step == "suggest_outfit":
            item = session["selected_item"]
            session["tool_calls"].append({"tool": "suggest_outfit", "item_id": item["id"]})
            session["outfit_suggestion"] = suggest_outfit(item, session["wardrobe"])

        elif step == "create_fit_card":
            item = session["selected_item"]
            session["tool_calls"].append({"tool": "create_fit_card", "item_id": item["id"]})
            session["fit_card"] = create_fit_card(session["outfit_suggestion"], item)

        else:  # "done"
            return session


def _next_step(session: dict) -> str:
    """Pick the next step from what's in the session — nothing else."""
    if not session["parsed"]:
        return "parse"
    if not session["searched"]:
        return "search"
    if not session["search_results"]:
        return "stop_empty"
    if session["selected_item"] is None:
        return "select"
    if session["outfit_suggestion"] is None:
        return "suggest_outfit"
    if session["fit_card"] is None:
        return "create_fit_card"
    return "done"


# ── running it directly ───────────────────────────────────────────────────────

def _show(session: dict) -> None:
    if session["error"]:
        print(f"  stopped: {session['error']}")
        print(f"  fit_card is {session['fit_card']!r} — it should still be None here")
        return

    item = session["selected_item"] or {}
    print(f"  found:    {item.get('title')} — ${item.get('price')} on {item.get('platform')}")
    print(f"  outfit:   {session['outfit_suggestion']}")
    print(f"  fit card: {session['fit_card']}")


if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== A query the data can match ===")
    _show(run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    ))

    print("\n=== A query it can't ===")
    _show(run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    ))

    print(
        "\nThe second one should stop before the fit card. If both paths look "
        "the same,\nthe branch isn't doing anything yet."
    )
