# Marrowfield

A chalk valley with a river, three factions, and a lie in the historical record.

Every morning the world advances exactly one day under its own rules, and the
episode is written from what *changed* — not from what would make a good story.
Nothing is retconned. If someone dies they stay dead.

`world.json` is the canon. It is the only file here that cannot be regenerated.

## What is finished and what is not

**Working and tested:**

- `scripts/simulate.py` — the world engine. Pure Python, no model, no network.
  Deterministic: the same state and day always yield the same episode, because
  all randomness is seeded from `(world_seed, day)`. Ran 365 simulated days
  without breaking.
- `scripts/run_day.py` — steps the world, generates three images, composes a
  39-second vertical Short with typeset narration, uploads it, commits the state.
  The whole render chain is tested end to end with placeholder images.
- The GitHub Actions workflow, at 08:00 Seoul time daily.

**The honest gap: the authoring is about a fifth done.**

There are 13 plot beats and 8 recurring texture events. Over 365 days that
produces only ~25 distinct episodes — the arc completes around day 75 and then
the channel would visibly loop. Which is why `total_days` is set to **90**, not
365: the story genuinely finishes inside that window, and ninety episodes with a
real ending beats a year that repeats itself.

Even at 90 days there are two thin stretches (days 47–72 is a long quiet run).
Roughly ten more mid-arc beats would fix it.

## Setup

You already have the Cloudflare secrets from The Same Room and they can be
reused verbatim. What's new is the channel and its own upload token.

1. **Create the channel.** YouTube → Settings → Add or manage your channel(s) →
   Create a channel → `Marrowfield`.
2. **New repo**, drop these files in. Note that Windows drag-and-drop silently
   skips dot-folders, so `.github/` and `.gitignore` need creating by hand
   through *Add file → Create new file*.
3. **Cloudflare secrets** — same two values as The Same Room:
   `CF_ACCOUNT_ID`, `CF_API_TOKEN`.
4. **A new YouTube refresh token.** The OAuth client can be reused, but a
   refresh token is bound to one channel. Run this once locally and pick
   **Marrowfield** at the account picker:

   ```
   python scripts/get_youtube_token.py client_secret.json
   ```

   Add `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` as secrets.
5. **Set `start_date`** in `config.json` to the day you want Day 1 to be.
6. **Dry run:** Actions → Marrowfield — daily → Run workflow → tick the dry-run
   box. Costs about 300 Cloudflare neurons — 3% of one day's free allowance —
   and uploads nothing.

## Layout

```
world.json              the canon — mutable, committed daily
canon/seed_world.json   immutable day-zero state for reference
scripts/simulate.py     the world engine
scripts/run_day.py      the daily job
chronicle/day-NNNN.json one file per episode: event, scenes, narration
archive/day-NNNN/       the three images for that day
log.jsonl               one line per day
```

## Running the engine on its own

The simulation needs nothing but Python, so the whole year can be dry-run in a
second — useful before authoring new beats:

```python
import json, sys; sys.path.insert(0, 'scripts')
import simulate
w = json.load(open('canon/seed_world.json')); w['projects'] = {}
for d in range(1, 91):
    e = simulate.step(w, d)
    print(e['day'], e['event'], e['date'])
```

## Adding beats

Append to `EVENTS` in `simulate.py`. An event needs `id`, `once`, `phase`
(minimum tension), `requires(w)`, `weight`, `apply(w)`, and `scenes(w)` — or
`scenes(w, rng)` if it repeats and should vary its narration between firings.

Because the world state persists, beats can be added mid-series without
disturbing anything already chronicled. The engine will simply start offering
them once their preconditions are met.
