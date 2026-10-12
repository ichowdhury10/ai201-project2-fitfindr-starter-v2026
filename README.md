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
$ python app.py ask '...'

```

**The three tools, tested one at a time**

```
$ python -c "from tools import search_listings; print(search_listings('graphic tee', max_price=30))"

```

```
$ python -c "from tools import suggest_outfit; ..."

```

```
$ python -c "from tools import create_fit_card; ..."

```

---

## How I Used AI

<!-- Two specific moments. What you asked, what came back, what you changed.

     "I used Claude to help me code" is not enough.

     "I gave Claude my search_listings spec. It returned None on no match
     instead of an empty list, so I changed it" is the level we want. -->

**Moment 1**

- *What I asked for:*
- *What came back:*
- *What I changed:*

**Moment 2**

- *What I asked for:*
- *What came back:*
- *What I changed:*

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

**Happy path**

```

```

**Empty search**

```

```

**On the MCP move:** <!-- what changed in your code, and whether anything
behaved differently afterwards. If the rewire didn't work, say exactly where it
broke — the error text and the last thing that worked. That earns the point in
full. -->



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
