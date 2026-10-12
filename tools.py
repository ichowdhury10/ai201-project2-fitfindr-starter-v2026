"""
The three FitFindr tools.

Each one is a standalone function you can call and test on its own, before any
of them are wired into the loop. Build and test them one at a time — three
untested tools joined by a loop is one problem that looks like six, because you
can't tell which layer is lying to you.

    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)             → str
    create_fit_card(outfit, new_item)              → str

The specs these follow are in the README under Tool Inventory.

⚠️ Before you write any of them, fill in the **Tool Inventory** section of your
README (Milestone 2). Four lines per tool: what it does, each input with its
type, exactly what it returns, and what it returns when it has nothing to give.
That last line is what your loop branches on. "Returns a list" earns nothing —
the description has to say what is *in* the list.
"""

import re

import config
from generate import generate
from utils.data_loader import load_listings


# ── Shared helpers ────────────────────────────────────────────────────────────

# Words that say nothing about the item. Dropped from the description before
# scoring, so "looking for a tee" scores the same as "tee". The agent's parser
# uses this list too.
STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "in", "on", "of", "to", "with",
    "i", "im", "i'm", "me", "my", "want", "need", "looking", "find", "show",
    "some", "something", "please", "any", "that", "is", "it", "under", "below",
    "size", "around", "about", "like", "would", "get",
}

# Listing field → how much a keyword hit in that field is worth.
_FIELD_WEIGHTS = {
    "title": 3,
    "style_tags": 2,
    "category": 2,
    "brand": 2,
    "colors": 1,
    "description": 1,
}

_LETTER_SIZES = {"XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL"}
_SIZE_WORDS = {
    "SMALL": "S", "MEDIUM": "M", "LARGE": "L",
    "XSMALL": "XS", "X-SMALL": "XS", "EXTRA SMALL": "XS",
    "XLARGE": "XL", "X-LARGE": "XL", "EXTRA LARGE": "XL",
}

_PLATFORM_NAMES = {"depop": "Depop", "thredup": "thredUP", "poshmark": "Poshmark"}


def _stem(word: str) -> str:
    """Crude plural folding: tees → tee, jeans → jean. Leaves 'dress' alone."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _keywords(text: str) -> set[str]:
    """Lowercase words in `text`, minus filler, with plurals folded."""
    text = text.lower().replace("t-shirt", "tee").replace("tshirt", "tee")
    words = re.findall(r"[a-z0-9]+", text)
    return {_stem(w) for w in words if len(w) > 1 and w not in STOPWORDS}


def _field_text(listing: dict, field: str) -> str:
    value = listing.get(field)
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)


def _score(listing: dict, query_words: set[str]) -> int:
    score = 0
    for field, weight in _FIELD_WEIGHTS.items():
        field_words = _keywords(_field_text(listing, field))
        score += weight * len(query_words & field_words)
    return score


def normalize_size(size: str) -> str:
    """'medium' → 'M', 'US 8' → '8', 'w30' → 'W30', ' m ' → 'M'."""
    s = re.sub(r"\s+", " ", size.strip().upper())
    s = _SIZE_WORDS.get(s, s)
    s = re.sub(r"^US\s*", "", s)
    return s


def _size_tokens(listing_size: str) -> list[str]:
    """'S/M' → ['S', 'M'], 'US 8.5' → ['US', '8.5'], 'W30 L30' → ['W30', 'L30']."""
    return re.findall(r"[A-Z]+\d*|\d+(?:\.\d+)?", listing_size.upper())


def _size_matches(wanted: str, listing_size: str) -> bool:
    """
    Whole-token size matching, never substring. See the Tool Inventory in the
    README for the rules. "L" must not match "XL", and "S" must not match "US 9".
    """
    want = normalize_size(wanted)
    tokens = _size_tokens(listing_size)
    one_size = "ONE" in tokens and "SIZE" in tokens

    if want in _LETTER_SIZES:
        return want in tokens or one_size

    if re.fullmatch(r"\d+(?:\.\d+)?", want):
        # A bare number is a shoe size (US 8) or a waist (W30).
        number = float(want)
        if "US" in tokens:
            return any(
                re.fullmatch(r"\d+(?:\.\d+)?", t) and float(t) == number
                for t in tokens
            )
        return f"W{want}" in tokens

    return want in tokens


def price_text(price: float) -> str:
    return f"${price:.0f}" if float(price).is_integer() else f"${price:.2f}"


def _platform_name(platform: str) -> str:
    return _PLATFORM_NAMES.get(str(platform).lower(), str(platform))


def _describe_item(item: dict) -> str:
    """The listing as prompt lines. Brand only appears when there is one."""
    lines = [
        f"Title: {item.get('title')}",
        f"Category: {item.get('category')}",
        f"Colors: {', '.join(item.get('colors') or [])}",
        f"Style: {', '.join(item.get('style_tags') or [])}",
        f"Size: {item.get('size')}",
        f"Condition: {item.get('condition')}",
        f"Price: {price_text(item.get('price', 0))}",
        f"Platform: {_platform_name(item.get('platform', ''))}",
    ]
    if item.get("brand"):
        lines.append(f"Brand: {item['brand']}")
    if item.get("description"):
        lines.append(f"Seller's description: {item['description']}")
    return "\n".join(lines)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the listings data for items matching a description, and optionally a
    size and a price ceiling.

    This is the tool that doesn't call the model, which makes it the easiest one
    to test and the one to move onto MCP in unit 4.

    Args:
        description: keywords describing what the user wants
                     (e.g. "vintage graphic tee").
        size:        a size string to filter by, or None to skip size filtering.
                     Match case-insensitively — "M" should match "S/M".

                     ⚠️ Read the sizes in the data before you reach for a plain
                     substring test. `"s" in "us 9"` is True, and so is
                     `"l" in "xl"`. A filter that returns shoes when someone
                     asked for a small top reads like a broken search, and it
                     will quietly cost you in unit 4 when you test criterion 1.
                     What counts as a size match is part of your spec — decide
                     it and write it into your Tool Inventory.
        max_price:   maximum price, inclusive, or None to skip price filtering.

    Returns:
        A list of matching listing dicts, best match first.
        **Returns an empty list when nothing matches — an empty list, not None,
        and not an exception.** Your loop branches on this.

    Each listing dict has these fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand (str or None), platform

    Note that `brand` is None for most listings. That is deliberate and
    realistic — thrift listings often have no brand. If something you write
    assumes a brand is always there, you will find out in unit 4.

    Test it from a terminal before you move on:
        python -c "from tools import search_listings; print(search_listings('graphic tee', max_price=30))"
    """
    query_words = _keywords(description or "")
    if not query_words:
        return []

    scored = []
    for listing in load_listings():
        if max_price is not None and listing["price"] > max_price:
            continue
        if size and not _size_matches(size, listing["size"]):
            continue
        score = _score(listing, query_words)
        if score > 0:
            scored.append((score, listing))

    # Best score first; on a tie, the cheaper item first.
    scored.sort(key=lambda pair: (-pair[0], pair[1]["price"]))
    return [listing for _, listing in scored[: config.SEARCH_RESULT_LIMIT]]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest one or two outfits.

    This one calls the model, through `generate()`. You don't need to think
    about rate limits — the adapter handles pacing for you.

    Args:
        new_item: a listing dict — the item the user is considering.
        wardrobe: a wardrobe dict with an 'items' key holding a list of items.
                  **It may be empty.** Handle that.

    Returns:
        A non-empty string with outfit suggestions.
        With an empty wardrobe, return general styling advice rather than
        raising or returning "". Unit 4 has you trigger the empty wardrobe on
        purpose, so decide now what it should do.

    Test it from a terminal before you move on:
        python -c "from tools import suggest_outfit; from utils.data_loader import get_example_wardrobe, load_listings; print(suggest_outfit(load_listings()[0], get_example_wardrobe()))"
    """
    items = (wardrobe or {}).get("items") or []

    system = (
        "You are a thrift stylist. Suggest exactly two outfits built around the "
        "new item. Number them 1. and 2. Each outfit is one or two sentences. "
        "Plain text only: no markdown headers, no bold, no bullet lists."
    )

    if not items:
        prompt = (
            "Someone is thinking about buying this thrifted item. They haven't "
            "told us anything about their wardrobe, so give general styling "
            "advice: describe the kinds of pieces (cut, color, shoes) that "
            "would go with it.\n\n"
            f"{_describe_item(new_item)}"
        )
    else:
        owned = "\n".join(
            f"- {piece.get('name')} ({piece.get('category')}"
            + (f"; {piece['notes']}" if piece.get("notes") else "")
            + ")"
            for piece in items
        )
        prompt = (
            "Someone is thinking about buying this thrifted item:\n\n"
            f"{_describe_item(new_item)}\n\n"
            "Here is what they already own:\n"
            f"{owned}\n\n"
            "Build each outfit from the new item plus pieces from that list. "
            "Name each owned piece exactly as it's written in the list. Don't "
            "invent pieces they don't own."
        )

    response = generate(prompt, system=system)
    if not response.strip():
        return (
            f"Pair the {new_item.get('title', 'item')} with simple basics in "
            "neutral colors and let it be the statement piece."
        )
    return response


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Write a short caption someone would actually post about the find.

    This calls the model too.

    Args:
        outfit:   the outfit suggestion string from suggest_outfit().
        new_item: the listing dict for the item.

    Returns:
        A two-to-four sentence caption.
        If `outfit` is empty or whitespace, return a descriptive message rather
        than raising.

    The caption should read like a real post rather than a product description,
    mention the item and its price and platform once each, and be specific about
    the vibe.

    It should also come out **differently for different inputs**. If you run
    this three times on the same item and get three word-for-word identical
    strings, it's one of two things, and both are near the top of `config.py`:

        • CACHE_ENABLED — the adapter handed back an answer it already had
        • TEMPERATURE   — at 0.0 the model gives the same words every time

    Test it from a terminal before you move on:
        python -c "from tools import create_fit_card; from utils.data_loader import load_listings; print(create_fit_card('jeans and white sneakers', load_listings()[0]))"
    """
    title = new_item.get("title", "this item")
    if not outfit or not outfit.strip():
        return (
            "Can't write a fit card without an outfit suggestion — "
            f"suggest_outfit returned nothing for {title}."
        )

    price = price_text(new_item.get("price", 0))
    platform = _platform_name(new_item.get("platform", ""))

    system = (
        "You write short social media captions for thrift finds. Write like a "
        "real person posting about something they just found, not like a "
        "product listing. 2 to 4 sentences, under 80 words, first person. No "
        "hashtags. At most two emoji. Plain text only."
    )
    # Unit 4 improvement: the outfit is a set of ideas that may use pieces the
    # user doesn't own (always, when the wardrobe is empty), so it is no longer
    # introduced as "How I'm styling it".
    prompt = (
        "Write a caption for this thrift find.\n\n"
        f"{_describe_item(new_item)}\n\n"
        "Outfit ideas for it (these may include pieces I don't own):\n"
        f"{outfit.strip()}\n\n"
        f"Mention the item, the price ({price}), and where I got it "
        f"({platform}), each exactly once. Pick one outfit idea and be "
        "specific about the vibe, but describe the other pieces as plans or "
        "ideas, never as something I'm already wearing or have already worn. "
        "Only mention a brand if one is listed above."
    )

    response = generate(prompt, system=system)
    if not response.strip():
        return f"Thrifted this {title} for {price} on {platform} and I'm obsessed."
    return response
