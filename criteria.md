# Acceptance criteria — FitFindr

Five criteria that say what "working" means for this agent, written in unit 3
**before** any results existed.

An acceptance criterion names a target: a number, a count, a rate, or something
a person could plainly observe. *"The agent handles errors"* is an opinion.
*"When search returns nothing, the agent stops before calling the second tool,
in 5 of 5 tries"* is a criterion.

Under each one, write a sentence or two on **why that target** and not a
stricter one. A reason that says something about your tools, your loop, or the
data earns credit; *"80% seemed reasonable"* does not.

> Missing your own targets next unit costs you nothing. Setting a target so
> easy you can't miss it does.

**Two are written for you. You write three.**

Every "try" below is one run of `agent.py::run_agent` with the response cache
off (`run_eval.py` turns it off, or set `AI201_CACHE=0`), so each model call is
a real call.

---

## 1. A matching query completes all three tools

Given a query that matches at least one listing, the agent completes all three
tool calls and returns a fit card — in at least 4 of 5 tries.

**How to check:** Run `'vintage graphic tee under $30'` with the example
wardrobe. A try passes if `session["error"]` is `None`, `session["fit_card"]`
is a non-empty string, and `session["tool_calls"]` lists `search_listings`,
`suggest_outfit`, and `create_fit_card` in that order. A crash counts as a
fail.

**Why this target:** For a fixed query, the parsing (regex) and
`search_listings` (keyword scoring, no model) are deterministic. If the search
finds the tee once, it finds it every time, so the search can't be what causes
an occasional miss. The variation is in the two model calls.
`generate()` raises `ModelUnavailable` on any error that isn't a rate limit,
and it raises a `RuntimeError` after 5 rate-limit retries. `run_agent` doesn't
catch either one until unit 4. So I'm allowing one try in five for a network or quota
failure. I'm not allowing more than one, because this query's top match
(`lst_006`) is a strong keyword hit on all three words.

---

## 2. An impossible query stops before the second tool

Given a query that matches no listings, the agent stops before calling
`suggest_outfit` and returns a message naming what to change — 5 of 5 tries.

**How to check:** Run `'designer ballgown size XXS under $5'`. A try passes if
all four of these hold:

- `session["fit_card"]` and `session["outfit_suggestion"]` are both `None`.
- No entry in `session["tool_calls"]` is `suggest_outfit` or `create_fit_card`.
- The run used 0 model calls.
- `session["error"]` names the price, the size, or the specific words as the
  thing to change. "No results" alone fails.

**Why this target:** This path never touches the model. It's regex,
`search_listings`, a Python `if`, and `_explain_empty`, which picks one of four
fixed message templates. The same input produces the same output every time,
so there's no randomness to leave room for. A single miss would mean the branch
itself is wrong, and that's exactly what this criterion exists to catch.

---

## 3. The item search found is the item the next two tools receive

For `'vintage graphic tee under $30, size M'`, in 5 of 5 tries, the `id` of
`session["selected_item"]` equals `session["search_results"][0]["id"]`, and it
also equals the `item_id` recorded in `session["tool_calls"]` for both the
`suggest_outfit` call and the `create_fit_card` call.

**How to check:** After each run, print `session["selected_item"]["id"]`,
`session["search_results"][0]["id"]`, and the `item_id` of the
`suggest_outfit` and `create_fit_card` entries in `session["tool_calls"]`. All
four have to be the same listing id. `run_agent` records each tool call's
`item_id` from the exact dict it passes to that tool, so the record shows what
the tool actually received.

**Why this target:** Passing the item along is plain Python dict handling, with
no model involved, so nothing about it should vary between tries. The ways it
could break are bugs in my loop: picking from a stale list, re-searching between
steps, or one tool reading a different field than the other. Accepting 4 of 5
would mean accepting one of those bugs. I chose a query with a size filter so
that the item that has to flow through (`S/M`, not one of the `L` tees) is
different from what an unfiltered search would put first.

---

## 4. The fit card gets the facts right, whatever words it uses

For `'vintage graphic tee under $30'`, at least 4 of 5 fit cards must meet all
three of these:

- They contain the selected item's price written exactly as
  `tools.price_text` formats it (e.g. `$24`).
- They name the item's platform (`Depop`, `thredUP`, or `Poshmark`; any
  capitalization).
- They are 2 to 4 sentences long and at most 80 words.

**How to check:** For each try, search `session["fit_card"]` for the price
string and the platform name. Count words by splitting on spaces. Count
sentences by the `.`, `!`, and `?` that end one; emoji after the last sentence
don't count as one.

**Why this target:** The words are supposed to change from try to try. That's
the temperature (0.9) doing its job, so I'm not scoring the wording. What makes
the variation acceptable is that the facts and the length stay fixed: someone
posting it needs the right price and platform, and a caption past 80 words
isn't a caption. The prompt in `tools.py::create_fit_card` gives the exact price
string and platform name, and asks for 2–4 sentences under 80 words. But
nothing checks the reply or retries, so the model can still drop the platform
or run long, and that's why it isn't 5 of 5. It isn't 3 of 5 because every fact
it needs is spelled out in the prompt rather than left for the model to infer.

---

## 5. An empty wardrobe still gets a full run, without inventing a closet

With an empty wardrobe and `'denim jacket under $50'`, in at least 4 of 5 tries,
the agent completes all three tool calls and returns a fit card. In addition,
`session["outfit_suggestion"]` does not contain the word "your" or "yours" as a
whole word, in any capitalization.

**How to check:** Run `python app.py ask 'denim jacket under $50'
--empty-wardrobe`, or use run_eval's "empty wardrobe" scenario. A try passes if
`session["error"]` is `None`, `session["fit_card"]` is non-empty, and a
whole-word, case-insensitive search of `session["outfit_suggestion"]` for
`your` or `yours` finds nothing.

**Why this target:** When the wardrobe is empty, the agent knows nothing about
what the user owns. So "pair it with your favorite jeans" is the agent making
up a closet, and that's the failure I care about on this path.
`suggest_outfit` sends a different prompt here, one that says nothing is known
about the wardrobe. But it doesn't forbid second-person phrasing, and at
temperature 0.9 the model may fall back on "your" because that's how most
styling advice is written. It's 4 of 5 rather than 5 of 5 for two reasons: the
same model-call failures as criterion 1, and a prompt that only steers this
rather than enforcing it. It isn't lower because the prompt does say outright
that the wardrobe is unknown.

---

<!-- ─────────────────────────────────────────────────────────────────────────
     UNIT 4 — read this before you change anything above.

     If a criterion turns out to be BROKEN rather than merely unmet, you can
     revise it, and that earns credit. But never delete or edit the original
     line. Add the revision underneath it, like this:

         ## 4. Something about the fit card

         The fit card is different every time.

         **Why this target:** ...

         > **Revised in unit 4:** For 5 different items, the 5 fit cards share
         > no opening sentence.
         >
         > **Why revised:** "different" wasn't checkable — two cards that
         > differed by one word still counted. The new version is something I
         > can actually score.

     That's a revision because the criterion couldn't be MEASURED.

     Lowering a target because you missed it is not a revision, and it costs
     you the point:

         ✗ "I said the empty search stops it 5 of 5 times, but I got 3 of 5,
            so 3 of 5 is more realistic."

     A number you missed stays where it is, gets diagnosed, and gets a fix
     attempted. That's where the points are.
     ───────────────────────────────────────────────────────────────────────── -->
