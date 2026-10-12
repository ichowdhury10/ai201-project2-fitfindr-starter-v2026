# FitFindr

> ### 👋 Start here
>
> **New to this repo? Read [RUNNING.md](RUNNING.md) first** — setup, every
> command, and what to do when something breaks.
>
> Once `python test.py` passes:
>
> ```bash
> python app.py listings --full -n 6      # read the data (Milestone 1)
> python app.py fields                    # what you can filter on
> python app.py ask 'vintage graphic tee under $30'
> ```
>
> All three tools are stubs, so that last command will do nothing useful yet.
> That's the starting position.
>
> **The rest of this file is your submission.** Fill it in as you go.

---

<!-- ─────────────────────────────────────────────────────────────────────────
     HOW TO USE THIS FILE

     This is your submission. Fill each section in as you finish the milestone
     it belongs to — don't leave it all to the end.

     Unit 3 asks for the first five sections. Unit 4 adds the five below them.
     Leave the unit 4 sections alone until then; they're here so you know
     what's coming.

     Everything is pasted as TEXT. No screenshots, no images, no video links.
     A typed block of output gets full credit; a picture of the same output
     gets none.
     ───────────────────────────────────────────────────────────────────────── -->

<!-- ═══════════════════════ UNIT 3 — THE BUILD ═══════════════════════ -->

## What This Does

<!-- Three or four sentences: what a user asks for, and what they get back. -->

FitFindr takes a plain-language thrift request, like
`'vintage graphic tee under $30, size M'`, and pulls out what's being described,
the size, and the price ceiling. It searches 40 Depop/thredUP/Poshmark listings
for the best match. It then asks the model for two outfits that pair that item
with pieces already in the user's wardrobe, and writes a short caption they
could post. If nothing matches, it stops before any model call and says which
part of the request to change: the price, the size, or the words.


---

## Tool Inventory

<!-- Four lines per tool. This is worth 2 points and it's the single most
     common place students lose them.

     "Returns a list" earns NOTHING. The description has to say what is IN
     the list.

     The empty case isn't optional either — it's the thing your loop branches
     on, and if you don't decide it here you'll discover it as a crash in
     Milestone 5. -->

### `search_listings`

- **What it does:** Filters `data/listings.json` by size and price ceiling,
  then ranks what's left by keyword overlap with the description. It never
  calls the model.
- **Inputs:**
  - `description` (str): keywords like `"vintage graphic tee"`. Filler words
    (`a`, `for`, `looking`…) are ignored, and a trailing `s` is dropped so `tees`
    matches `tee`.
  - `size` (str | None): `None` skips the size filter. The match is on whole
    size tokens, case-insensitive, never on substrings:
    - Letter sizes: `"M"` matches `M`, `S/M`, and `M/L`. `"L"` does **not**
      match `XL`, and `"S"` does **not** match `US 9`.
    - `small` / `medium` / `large` are read as `S` / `M` / `L`.
    - Letter sizes also match `One Size` listings.
    - Numbers: `"8"` or `"US 8"` matches shoe size `US 8` only (not `US 8.5`).
      `"30"` or `"W30"` matches waist `W30`.
  - `max_price` (float | None): an inclusive ceiling (`price <= max_price`).
    `None` skips the price filter.
- **Returns:** `list[dict]` of at most `config.SEARCH_RESULT_LIMIT` (10) full
  listing dicts, best match first. Each dict is the record exactly as it is in
  the data: `id`, `title`, `description`, `category`, `style_tags` (list),
  `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None),
  `platform`. The score is the sum of weights for each query word found in the
  listing: title 3, style tags 2, category 2, brand 2, colors 1, description 1.
  Ties go to the cheaper item.
- **When it has nothing:** `[]`, an empty list. Not `None`, and no exception.
  That covers three cases: no listing passes the filters, no listing shares a
  keyword with the description, or the description has no keywords left once
  filler words are removed.

### `suggest_outfit`

- **What it does:** Asks the model for two outfits built around the new item.
  When the wardrobe has items, each outfit uses pieces the user already owns,
  named exactly as they appear in the wardrobe.
- **Inputs:**
  - `new_item` (dict): one listing dict, as returned by `search_listings`.
  - `wardrobe` (dict): a dict with an `items` key holding a list of wardrobe
    item dicts (`id`, `name`, `category`, `colors`, `style_tags`, `notes`).
    `items` may be empty, and `None` is treated as empty.
- **Returns:** `str`, non-empty: two numbered outfits, one or two sentences
  each, in plain text without markdown headers.
- **When it has nothing:** If the wardrobe is empty, it doesn't fail. It asks
  the model for general styling advice instead, describing the kinds of pieces
  the item goes with, and returns that as a non-empty `str`. If the model sends
  back an empty reply, it returns a fixed fallback sentence, so the result is
  never `""`.

### `create_fit_card`

- **What it does:** Asks the model for a 2–4 sentence caption someone would
  actually post about the find.
- **Inputs:**
  - `outfit` (str): the string `suggest_outfit` returned.
  - `new_item` (dict): the same listing dict that went into `suggest_outfit`.
- **Returns:** `str`, a caption of 2–4 sentences, under 80 words, in
  first-person casual voice. It names the item, the price (as `$24`), and the
  platform (`Depop`, `thredUP`, or `Poshmark`) once each, and it reflects the
  outfit idea. The brand only goes into the prompt when it isn't `None`, so the
  caption can't name a brand the listing doesn't have.
- **When it has nothing:** If `outfit` is empty or whitespace, it returns the
  string `"Can't write a fit card without an outfit suggestion — suggest_outfit
  returned nothing for <item title>."` and does **not** call the model. If the
  model sends back an empty reply, it returns a fixed fallback caption built
  from the item's title, price, and platform.

---

## Planning Loop

<!-- Your branch rule, stated as a rule — the condition AND both paths — plus
     the file and function that holds it.

     Like this:
       "If search_listings returns an empty list, put a message in the session
        and stop. Otherwise take the first result and go to suggest_outfit."
        — agent.py::run_agent

     The grader checks your code against what you claim here, so the file and
     function have to be real. -->

**Branch rule:** If `search_listings` returns an empty list, write a message to
`session["error"]` that names which filter to change, then stop.
`suggest_outfit` and `create_fit_card` are never called, and
`session["fit_card"]` stays `None`. Otherwise, take the first (best-scoring)
result as `session["selected_item"]` and go to `suggest_outfit`.

The message is worked out by re-running `search_listings` with one filter
removed at a time:

- If dropping the price ceiling finds something, the message names the
  closest match and its price.
- If dropping the size finds something, it gives how many matches there are
  and in which sizes.
- If neither filter alone is the cause but dropping both finds something, it
  says both are too tight.
- If nothing matches even with no filters, the problem is the words
  themselves, and the message suggests broader ones.

**Where it lives:** `agent.py::run_agent` (the branch is the `"stop_empty"`
step chosen in `agent.py::_next_step`; the message comes from
`agent.py::_explain_empty`)

**How it decides the next step:** `run_agent` is a `while` loop. Each time
round, it calls `trace.check_iterations(count)`, then asks `_next_step(session)`
what to do. `_next_step` reads only the session:

1. Nothing parsed yet → parse.
2. Not searched yet → search.
3. Search came back empty → stop.
4. No item selected → select.
5. No outfit yet → `suggest_outfit`.
6. No fit card yet → `create_fit_card`.
7. Otherwise → done.

**How the query is parsed:** With regex, in `agent.py::parse_query`, without
calling the model:

- **Price:** `under`, `below`, `less than`, `max`, `up to`, or `at most`,
  followed by a number with or without `$`. A bare `$30` also counts. It
  becomes `max_price`.
- **Size:** only a size written after the word `size` (or `sz`), such as
  `size M`, `size 8.5`, `size W30`, or `size medium`. "Medium wash" is a denim
  colour in this data, so a bare "medium" isn't read as a size.
- **Description:** whatever is left once the price phrase, the size phrase,
  punctuation, and filler words are removed.

**What moves through the session:** in order,

1. `query`: the raw text.
2. `parsed`: `{description, size, max_price}`.
3. `search_results`: the list from `search_listings`. `searched` becomes
   `True`, so an empty result can be told apart from "not run yet".
4. `selected_item`: `search_results[0]`.
5. `outfit_suggestion`: read from the session together with `selected_item`
   and `wardrobe`, then passed to `suggest_outfit`.
6. `fit_card`: read from `outfit_suggestion` and `selected_item`.

Every tool call is also appended to `session["tool_calls"]`, in order:

- searches as `{"tool": "search_listings", "inputs": {...}}`; the retries that
  explain an empty search also carry a `"note"`
- the two model tools as `{"tool": ..., "item_id": "lst_…"}`

That makes it possible to check afterwards which tools ran and which listing
each one received.

---

## Sample Run

<!-- Two things go here.

     1. One FULL query and its output, pasted as text.
     2. Your three per-tool terminal tests — the command and what it printed. -->

**One full query**

```
$ python app.py ask 'vintage graphic tee under $30, size M'

  Found:    Y2K Baby Tee — Butterfly Print — $18.0 on depop

  Outfit:   1. Pair the Y2K Baby Tee — Butterfly Print with baggy straight-leg jeans, dark wash, finished off with chunky white sneakers and the black crossbody bag.

2. Layer the Y2K Baby Tee — Butterfly Print over wide-leg khaki trousers, styled with the vintage black denim jacket and black combat boots.

  Fit card: Scored this little butterfly tee on Depop for just $18 and I am obsessed. I threw it on with some baggy straight-leg jeans, chunky white sneakers, and my black crossbody bag. It is giving major early 2000s mall rat in the best way possible. 🦋✨
```

**And one that matches nothing.** It stops before `suggest_outfit`:

```
$ python app.py ask 'designer ballgown size XXS under $5'

  No listings matched "designer ballgown" in size XXS under $5. Nothing in the listings matches the words "designer ballgown" at any size or price, so changing the filters won't help. Try broader words: a category (tee, jeans, jacket, sneakers) or a style (vintage, y2k, grunge, cottagecore).

0 model calls this session
```

**The three tools, tested one at a time**

```
$ python -c "from tools import search_listings; print([(l['title'], l['size'], l['price']) for l in search_listings('graphic tee', max_price=30)]); print(search_listings('designer ballgown', 'XXS', 5))"
[('Graphic Tee — 2003 Tour Bootleg Style', 'L', 24.0), ('Y2K Baby Tee — Butterfly Print', 'S/M', 18.0), ('Vintage Band Tee — Faded Grey', 'L', 19.0), ('Vintage Graphic Hoodie — Faded Black', 'L', 26.0), ('Mesh Long-Sleeve Top — Black', 'S/M', 15.0), ('Oversized Crewneck Sweatshirt — Vintage Navy', 'XL (fits oversized)', 20.0), ('Low-Rise Cargo Pants — Khaki', 'W29', 27.0)]
[]
```

```
$ python -c "from tools import suggest_outfit; from utils.data_loader import get_example_wardrobe, get_empty_wardrobe, load_listings; item = load_listings()[0]; print(suggest_outfit(item, get_example_wardrobe())); print('--- empty wardrobe:'); print(suggest_outfit(item, get_empty_wardrobe()))"
1. Pair the new vintage Levi's 501 jeans with the white ribbed tank top, the oversized grey crewneck sweatshirt layered on top, and the chunky white sneakers. Add the black crossbody bag to complete this casual streetwear look.

2. Style the new vintage Levi's 501 jeans with the white ribbed tank top tucked in, the vintage black denim jacket, and the brown leather belt. Finish the outfit with the black combat boots and the black crossbody bag.
--- empty wardrobe:
1. Pair these jeans with a cropped white ribbed tank top, an oversized black leather blazer, and chunky black loafers for a cool, effortless street style look.

2. Tuck a vintage graphic tee into the waistband, add a brown leather belt, and finish with retro sneakers to lean into a classic casual aesthetic.
```

```
$ python -c "from tools import create_fit_card; from utils.data_loader import load_listings; print(create_fit_card('jeans and white sneakers', load_listings()[0])); print(repr(create_fit_card('', load_listings()[0])))"
Scored these vintage Levi's on Depop for just $38. I'm living in these jeans and crisp white sneakers for that effortlessly cool errand-runner aesthetic. They fit like an absolute dream. 👖✨
"Can't write a fit card without an outfit suggestion — suggest_outfit returned nothing for Vintage Levi's 501 Jeans — Medium Wash."
```

**`create_fit_card` three times on the same item, cache off (`AI201_CACHE=0`).**
The words differ every time, but all three open with "Scored this … on Depop
for just $24":

```
Scored this vintage-style graphic tee on Depop for just $24. I threw it on with baggy straight-leg jeans and black combat boots for the ultimate grunge street style vibe. It is so soft and worn-in.
Scored this vintage-style bootleg graphic tee on Depop for just $24. It has that perfectly worn-in boxy fit. I'm wearing it with baggy straight-leg jeans for a gritty grunge look.
Scored this faded 2003 tour bootleg tee on Depop for just $24. Threw it on with my baggy straight-leg jeans for that ultimate grunge look. It has the best worn-in feel.
```

---

## How I Used AI

<!-- Two specific moments. What you asked, what came back, what you changed.

     "I used Claude to help me code" is not enough.

     "I gave Claude my search_listings spec. It returned None on no match
     instead of an empty list, so I changed it" is the level we want. -->

I used Claude (Claude Code) for this whole unit. I gave it the project brief and
it did setup, wrote the tool specs, built `tools.py` and `agent.py`, and wrote
three of the acceptance criteria.

**Moment 1: the empty-search message pointed at the wrong item**

- *What I asked for:* An empty-search message that says what to change, not
  just "No results". The loop re-runs `search_listings` with one filter removed
  at a time to find which filter emptied the results.
- *What came back:* For `'denim jacket under $10'` it said *"the cheapest match
  is $24 — raise your max price to at least $24."* But the $24 listing is
  High-Waisted Denim Shorts. The keyword search counts any listing with "denim"
  in it as a match, and the message picked the cheapest of them, not the best
  one. Raising the budget to $24 would have shown shorts to someone who asked
  for a jacket.
- *What I changed:* The message now names the **top-ranked** match and its
  price: *"the closest match, "Denim Jacket — Light Wash, Cropped", is $42.
  Raise your max price to $42 to see it."* (`agent.py::_explain_empty`)

<!-- ═══════════════════════ UNIT 4 — THE TEST ═══════════════════════

     Don't fill these in during unit 3.
     ═══════════════════════════════════════════════════════════════════ -->

---

## Run Log — Before

<!-- Five criteria, five tries each, in this exact format.

     Five, because your criteria are written out of five. Mark each try PASS
     or FAIL, count the passes, and read that count against your target — a
     row targeting 4 of 5 with three PASS cells is MISSED (3/5).

     `python run_eval.py --label before` runs everything and writes the table
     into results/. Paste it here and fill in the verdicts. -->

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| 1.  |  |  |  |  |  |  |  |
| 2.  |  |  |  |  |  |  |  |
| 3.  |  |  |  |  |  |  |  |
| 4.  |  |  |  |  |  |  |  |
| 5.  |  |  |  |  |  |  |  |

**Real output from one try**, pasted as text, naming the file and function
that produced it:

```

```

---

## Verdicts and Diagnoses

<!-- MET or MISSED per criterion against LAST UNIT's target, plus a sentence on
     how you decided.

     Then, for every miss: which of the four places it happened — a tool, the
     loop's branch, the session, or the model's output — AND the mechanism.

     Not a diagnosis:  "The fit card was bad."
     A diagnosis:      "The fit card criterion missed on 2 of 5 items. Both had
                        an empty brand field. My prompt puts the brand in the
                        first sentence, so the card opened with a blank and read
                        like a fragment. The tool worked; the prompt assumed a
                        field that isn't always there."

     Look for a pattern. Three misses on the same tool is one problem, not
     three. -->

| # | Criterion | Target | Verdict | How I decided |
|---|---|---|---|---|
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |
| 4 |  |  |  |  |
| 5 |  |  |  |  |

**Diagnoses**



---

## Loop Trace

<!-- One full run, printed step by step, with the MCP call visible in it.

     `python app.py ask '...' --trace` once you've added the trace.step()
     calls in Milestone 2.

     Worth pasting BOTH the happy path and the empty-search path. The empty
     one should be visibly shorter, because it stops. If your two traces are
     the same length, your branch isn't working — and this is the fastest way
     anyone will ever find that out. -->

**Happy path:** `python app.py ask 'vintage graphic tee under $30' --trace`,
traced by `agent.py::run_agent` (one `trace.step()` per step; the MCP call is
step 2):

```
[1] parse_query (regex)
      in:  vintage graphic tee under $30
      out: {'description': 'vintage graphic tee', 'size': None, 'max_price': 30.0}
[2] search_listings (via MCP)
      in:  description='vintage graphic tee', size=None, max_price=30.0
      out: 10 items: Graphic Tee — 2003 Tour Bootleg Style, Vintage Band Tee — Faded Grey, Vintage Graphic Hoodie — Faded Black … +7 more
[3] select_item
      in:  10 results
      out: Graphic Tee — 2003 Tour Bootleg Style ($24.0, depop)
      →    branch: results found → take the best match, go to suggest_outfit
[4] suggest_outfit
      in:  new_item=lst_006 (Graphic Tee — 2003 Tour Bootleg Style), wardrobe=10 items
      out: 1. Layer the graphic tee over the wide-leg khaki trousers and finish the look with chunky white sneakers and t…
[5] create_fit_card
      in:  new_item=lst_006, outfit=session['outfit_suggestion']
      out: Scored this vintage-style bootleg tee on Depop for just $24 and it's already my favorite piece. I love the box…
[6] done
      →    5 steps, fit card ready
```

**Empty search:** `python app.py ask 'designer ballgown size XXS under $5' --trace`

```
[1] parse_query (regex)
      in:  designer ballgown size XXS under $5
      out: {'description': 'designer ballgown', 'size': 'XXS', 'max_price': 5.0}
[2] search_listings (via MCP)
      in:  description='designer ballgown', size='XXS', max_price=5.0
      out: [] (empty)
[3] search_listings (via MCP)
      in:  description='designer ballgown', size='XXS', max_price=None
      out: [] (empty)
      →    explaining the empty search
[4] search_listings (via MCP)
      in:  description='designer ballgown', size=None, max_price=5.0
      out: [] (empty)
      →    explaining the empty search
[5] search_listings (via MCP)
      in:  description='designer ballgown', size=None, max_price=None
      out: [] (empty)
      →    explaining the empty search
[6] branch: search came back empty
      out: No listings matched "designer ballgown" in size XXS under $5. Nothing in the listings matches the words "desig…
      →    STOP — suggest_outfit and create_fit_card are not called

0 model calls this session
```

**Both traces have 6 lines, but the branch is working.** Steps 3–5 are
`_explain_empty` re-running the search with one filter dropped at a time, to
work out what the message should tell the user to change. For this query every
retry is empty too, so it ends up suggesting broader words. What the empty path
skips is what matters: neither `suggest_outfit` nor `create_fit_card` runs, and
there are 0 model calls.

A query where dropping one filter is enough makes the shorter path visible.
`'denim jacket under $10'` is parse → search `[]` → retry without the price
(finds the jacket) → stop, which is 4 lines.

**Failure modes, triggered on purpose**

| Failure | How I triggered it | What the agent said (before any handler) | Handler added |
|---|---|---|---|
| Empty search | `python app.py ask 'designer ballgown size XXS under $5'` | Message above; stopped with 0 model calls | None needed. The unit 3 branch already handled it |
| Empty wardrobe | `AI201_CACHE=0 python app.py ask 'denim jacket under $50' --empty-wardrobe` | General advice with no owned pieces, then a full fit card (output below) | None needed. `suggest_outfit` already handled it |
| Model unavailable | Ran `corduroy wide-leg pants under $40` (not cached) with one character of the key changed, as a `GEMINI_API_KEY=…` override so `.env` wasn't edited, plus `AI201_CACHE=0` | `app.py` printed `ModelUnavailable: The model rejected your API key…` and exited with code 1. Calling `run_agent` directly (which is what `run_eval.py` and `serve.py` do) raised a raw `generate.ModelUnavailable` stack trace, and the session, including the item the search had found, was lost | `agent.py::run_agent` catches `ModelUnavailable` and writes the message below into `session["error"]` |
| MCP server down (extra) | Pointed `mcp_client.SERVER` at a missing file | Would have been a raw `MCPError` | `run_agent` also catches `MCPError` |

Empty wardrobe output:

```
(running with an empty wardrobe)

  Found:    Denim Jacket — Light Wash, Cropped — $42.0 on poshmark

  Outfit:   1. Pair the cropped denim jacket with a high-waisted black midi skirt, a tucked-in white graphic tee, and chunky black platform loafers for a balanced streetwear look.

2. Throw the jacket over a slip dress in an earthy olive green tone and complete the outfit with retro canvas sneakers and a canvas tote bag for an effortless vintage vibe.

  Fit card: Scored this vintage Wrangler denim jacket on Poshmark for just $42 and I am obsessed with the structured shoulders. I threw it over an olive green slip dress with some retro canvas sneakers for such an effortless vintage vibe. It's officially my new go-to layer.
```

Model unavailable, after the handler:

```
[1] parse_query (regex)
      in:  corduroy wide-leg pants under $40
      out: {'description': 'corduroy wide-leg pants', 'size': None, 'max_price': 40.0}
[2] search_listings (via MCP)
      in:  description='corduroy wide-leg pants', size=None, max_price=40.0
      out: 5 items: Corduroy Wide-Leg Pants — Rust, Wide-Leg Linen Trousers — Natural, Low-Rise Cargo Pants — Khaki … +2 more
[3] select_item
      in:  5 results
      out: Corduroy Wide-Leg Pants — Rust ($32.0, depop)
      →    branch: results found → take the best match, go to suggest_outfit
[4] stopped: a tool failed
      out: Couldn't reach the AI model during suggest_outfit, so there's no outfit or fit card this time. The search itse…

  Couldn't reach the AI model during suggest_outfit, so there's no outfit or fit card this time. The search itself worked: it found "Corduroy Wide-Leg Pants — Rust" for $32 on depop. The model rejected your API key. Check GEMINI_API_KEY in your .env file, or create a fresh key at aistudio.google.com. Then run the same query again.
```

MCP server down, after the handler:

```
The listing search couldn't run: the MCP server (mcp_server.py) didn't answer (Couldn't call 'search_listings' over MCP: unhandled errors in a TaskGroup (1 sub-exception)). Nothing was searched, so try the same query again. If it keeps failing, run `python mcp_server.py` on its own to see the server's error.
```

**On the MCP move:**

- **The server:** `mcp_server.py` registers `search_listings` with the same
  three typed inputs as the Tool Inventory: `description: str`,
  `size: str | None`, and `max_price: float | None`. Its description gives the
  units (US dollars, inclusive), the size-matching rule, and the empty case.
  `python mcp_client.py` lists it with exactly those inputs.
- **The agent:** every search in `agent.py` now goes through
  `agent.py::_search`, which calls `mcp_client.call_tool("search_listings", …)`.
  That includes the retries inside `_explain_empty`. `agent.py` no longer
  imports `tools.search_listings`.
- **I checked it's really MCP:** I replaced `tools.search_listings` in the
  agent's process with a function that exits. Searches still worked, because
  they run in the server process.
- **What came back didn't change.** Over MCP the result was `==` to the direct
  call for `'vintage graphic tee'` under $30 (10 dicts; `price` still a float;
  `brand` still `None`, not `"None"`). The empty case still comes back as `[]`,
  not `None`, so the branch didn't need touching.
- **What did change:** each call now starts a server process, which takes about
  0.3 seconds. The empty path makes up to 4 searches, so
  `'designer ballgown size XXS under $5'` now takes about 1.6 seconds instead
  of being instant. The agent also has a new way to fail (the server not
  starting), which got its own handler.

---

## The Improvement

<!-- What you changed, why your diagnosis pointed at it, and the after-run in
     the same table format. One change, measured properly.

     `python run_eval.py --label after` -->

**What I changed:**

**Which failure it was meant to fix:**

### Run Log — After

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| 1.  |  |  |  |  |  |  |  |
| 2.  |  |  |  |  |  |  |  |
| 3.  |  |  |  |  |  |  |  |
| 4.  |  |  |  |  |  |  |  |
| 5.  |  |  |  |  |  |  |  |

**Did it help, and how do I know:**

<!-- If it made things worse, say that. Honestly reported, that earns full
     credit and is more interesting than one that worked. -->



---

## What's Still Broken

<!-- For each criterion still missed: what you'd do, and why you stopped where
     you did. "I ran out of time" is fine if it's true. Pretending nothing is
     left is not. -->



<!-- ═════════════════════════════════════════════════════════════════════

     SUBMISSION CHECKLIST — unit 3

       [ ] criteria.md has five numbered criteria, each with a target
       [ ] Each criterion has a reason underneath it
       [ ] All five unit 3 sections above have real content
       [ ] Tool Inventory: all three tools, inputs WITH TYPES, a specific
           return value, and the empty case
       [ ] Planning Loop names the branch rule and agent.py::run_agent
       [ ] Sample Run: one full query plus the three per-tool tests, as text
       [ ] At least four new commits
       [ ] Repository URL submitted — WRITE IT DOWN, you submit the same one
           next unit

     SUBMISSION CHECKLIST — unit 4

       [ ] mcp_server.py exists with one tool registered
           (or a written record of exactly where the rewire broke)
       [ ] Run Log — Before, five criteria, five tries each
       [ ] Real output pasted underneath, naming file and function
       [ ] A verdict on every criterion
       [ ] A diagnosis for every miss, naming a place AND a mechanism
       [ ] Loop Trace, with the MCP call visible in it
       [ ] All three failure modes triggered and handled
       [ ] One improvement, with Run Log — After in the same format
       [ ] What's Still Broken
       [ ] At least four new commits
       [ ] The SAME repository URL as last unit

     Do not delete and recreate this repository. Your commit history is what
     shows your criteria existed before your results did.
     ═════════════════════════════════════════════════════════════════════ -->

---

📖 **How to run this project: [RUNNING.md](RUNNING.md)**
