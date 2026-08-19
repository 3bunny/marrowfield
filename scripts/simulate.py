#!/usr/bin/env python3
"""
Marrowfield — the world engine.

Pure Python. No model, no API, no network. Given a world state and a day number
it advances the world by exactly one day and returns the chronicle entry for
that day. Deterministic: the same state and day always produce the same result,
because all randomness is seeded from (world_seed, day).

The rule the whole channel rests on: the episode is written FROM the state diff.
Nothing is narrated that the state does not justify. If we ever find ourselves
editing state to serve a story we want, the channel has become fiction with
extra steps and the point is lost.
"""

from __future__ import annotations

import random
from typing import Any

MONTHS = ["Reeds", "Rains", "Chalk", "Kiln-Smoke", "Long Dark"]
DAYS_PER_MONTH = 60


# ----------------------------------------------------------------------------
# calendar
# ----------------------------------------------------------------------------

def date_string(w: dict) -> str:
    return f"Day {w['calendar']['day']}, Month of {w['calendar']['month']}, Year {w['calendar']['year']}"


def advance_calendar(w: dict) -> None:
    c = w["calendar"]
    c["day"] += 1
    if c["day"] > DAYS_PER_MONTH:
        c["day"] = 1
        idx = MONTHS.index(c["month"])
        if idx + 1 >= len(MONTHS):
            c["month"] = MONTHS[0]
            c["year"] += 1
        else:
            c["month"] = MONTHS[idx + 1]


# ----------------------------------------------------------------------------
# environment
# ----------------------------------------------------------------------------

def step_river(w: dict, rng: random.Random) -> None:
    """The Vell rises in the Rains and falls through the Long Dark."""
    r = w["river"]

    if r["flooded"]:
        # Floodwater recedes. Once it is back in its banks the valley is in
        # aftermath, not flood, and the ordinary events become available again.
        r["level"] = max(40, r["level"] - 2)
        if r["level"] <= 48:
            r["flooded"] = False
            r["receded"] = True
            r["days_to_flood"] = 11 * DAYS_PER_MONTH * len(MONTHS)  # eleven years
        return

    month = w["calendar"]["month"]
    drift = {"Reeds": 0, "Rains": 3, "Chalk": 1, "Kiln-Smoke": -2, "Long Dark": -1}[month]
    noise = rng.choice([-1, 0, 0, 1])
    r["level"] = max(0, min(100, r["level"] + drift + noise))
    r["days_to_flood"] = max(0, r["days_to_flood"] - 1)
    if r["level"] >= 85:
        r["days_to_flood"] = min(r["days_to_flood"], 3)


def person(w: dict, key: str) -> dict:
    return w["people"][key]


def living(w: dict, key: str) -> bool:
    return w["people"][key]["alive"]


# ----------------------------------------------------------------------------
# events
#
# Each event is a dict:
#   id        unique string
#   once      if True it can fire at most once in the world's lifetime
#   phase     minimum tension required
#   requires  fn(w) -> bool, additional preconditions
#   weight    relative likelihood among eligible events
#   apply     fn(w) -> None, mutates state
#   scenes    fn(w) -> list of {prompt, lines}
#
# Texture events repeat and keep the calendar moving between plot beats.
# Plot events fire once and carry the arc. Both are chosen the same way.
# ----------------------------------------------------------------------------

STYLE = (
    "oil painting, visible brushwork, muted ochre and grey-green palette, "
    "soft overcast northern light, painterly, no text, no lettering"
)


def _s(prompt: str, *lines: str) -> dict:
    return {"prompt": f"{prompt}. {STYLE}", "lines": list(lines)}


EVENTS: list[dict[str, Any]] = []


def event(**kw):
    EVENTS.append(kw)
    return kw


# ---- plot: the forged record -------------------------------------------------

event(
    id="anneke_finds_alteration",
    once=True,
    phase=0,
    requires=lambda w: living(w, "anneke"),
    weight=500,
    apply=lambda w: (
        w["people"]["anneke"]["knows"].append("record_altered"),
        w.update(tension=w["tension"] + 2),
    ),
    scenes=lambda w: [
        _s("A wide pale chalk valley at dawn, a slow brown river winding through it, "
           "low mist on the water, a single stone bridge in the middle distance, no people",
           "The Almoners keep the flood record because someone has to,",
           "and because nobody else wanted the job."),
        _s("Extreme close-up of an old handwritten ledger page, iron-gall ink on yellowed rag paper, "
           "one entry written in a different cramped hand, warm candlelight raking across the paper",
           "Sister Anneke reaches the entry for the flood of three ninety-nine",
           "and finds it written in a hand she does not recognise."),
        _s("A woman in her forties in undyed grey wool robes sitting very still at a writing desk "
           "in a cold stone archive, one candle, breath faintly visible, heavy chiaroscuro",
           "The year has been changed. Someone added four to it.",
           "Which means the river is not four years from flooding.",
           "It is due."),
    ],
)

event(
    id="anneke_checks_second_ledger",
    once=True,
    phase=2,
    requires=lambda w: "record_altered" in person(w, "anneke")["knows"],
    weight=300,
    apply=lambda w: (
        w["people"]["anneke"]["knows"].append("two_hands_match"),
        w.update(tension=w["tension"] + 1),
    ),
    scenes=lambda w: [
        _s("Rows of leather-bound ledgers on stone shelves, one pulled out and open on a lectern, "
           "cold light from a high window",
           "There are four copies of the record. The Almoners are not careless."),
        _s("Two open ledger pages side by side under candlelight, the handwriting subtly different, "
           "close crop on the ink",
           "Three of them agree with each other.",
           "The fourth is the one the Kiln was shown."),
        _s("A grey-robed woman's hands resting flat on a closed ledger, knuckles pale, no face visible",
           "So it was not an error of copying.",
           "It was done once, carefully, for someone to read."),
    ],
)

event(
    id="odd_proposes_bridge",
    once=True,
    phase=1,
    requires=lambda w: living(w, "odd"),
    weight=250,
    apply=lambda w: (
        w["factions"]["reedfolk"].update(standing=w["factions"]["reedfolk"]["standing"] + 1),
        w["people"]["odd"].update(mood="stubborn"),
        w.update(tension=w["tension"] + 1),
    ),
    scenes=lambda w: [
        _s("A young man in patched fishing clothes standing on a muddy riverbank at low light, "
           "measuring the width of the water with a knotted rope, reeds bending",
           "Odd Hallow has measured the Vell at eleven places."),
        _s("A crude drawing of a timber bridge scratched on a plank in charcoal, laid on wet grass",
           "The narrowest crossing is upstream of the Kiln's bridge.",
           "Forty feet. Timber would do it."),
        _s("A small gathering of fisherfolk outside a low turf-roofed hut at dusk, listening, "
           "no clear faces, lantern light",
           "The Reedfolk listen politely.",
           "Nobody says the obvious thing — that the Kiln would never allow it."),
    ],
)

event(
    id="vesta_reads_the_toll",
    once=True,
    phase=1,
    requires=lambda w: living(w, "vesta"),
    weight=200,
    apply=lambda w: (
        w["factions"]["kiln"].update(coin=w["factions"]["kiln"]["coin"] + 2),
        w["people"]["vesta"]["knows"].append("toll_is_everything"),
    ),
    scenes=lambda w: [
        _s("An older woman in good dark wool at a counting table, brass weights and stacked coin, "
           "a ledger open, warm lamplight in a stone room",
           "Vesta Marrow has kept the Kiln's ledger for thirty-one years."),
        _s("Close-up of a column of figures in neat handwriting, coins beside it, shallow depth of field",
           "Two thirds of everything the Kiln has ever earned",
           "came across that bridge one cart at a time."),
        _s("A stone bridge seen from below at the waterline, carts crossing above, river running fast",
           "She does not think of it as a toll.",
           "She thinks of it as the only thing holding the valley in one piece."),
    ],
)

event(
    id="rumour_reaches_kiln",
    once=True,
    phase=4,
    requires=lambda w: "two_hands_match" in person(w, "anneke")["knows"],
    weight=300,
    apply=lambda w: (
        w["people"]["vesta"]["knows"].append("record_questioned"),
        w["factions"]["kiln"].update(grudge_almoners=w["factions"]["kiln"]["grudge_almoners"] + 2),
        w.update(tension=w["tension"] + 2),
    ),
    scenes=lambda w: [
        _s("Two women talking quietly at a market stall of grey pottery, heads close, "
           "other shoppers indistinct behind them",
           "It takes nine days for the rumour to cross the bridge."),
        _s("An older woman standing motionless in a doorway holding a ledger against her chest, "
           "lamplight behind her, expression not visible",
           "Vesta hears it from a woman buying two bowls."),
        _s("Night. A stone room, a ledger open on a table, a hand holding a candle very close to the page",
           "That night she reads her own copy of the flood record",
           "for the first time in eleven years."),
    ],
)

event(
    id="the_forger_named",
    once=True,
    phase=8,
    requires=lambda w: "record_questioned" in person(w, "vesta")["knows"],
    weight=400,
    apply=lambda w: (
        w["secrets"].update(forger_known=True),
        w.update(tension=w["tension"] + 3),
    ),
    scenes=lambda w: [
        _s("A stone archive at night, one candle, a grey-robed figure kneeling at the lowest shelf "
           "pulling out a bundle of loose papers",
           "The Almoners keep everything, including their own appointment rolls."),
        _s("A close crop of a signature on brittle paper, iron-gall ink, magnified by a glass lens",
           "The hand that altered the flood record",
           "signed the archive roll in the spring of four hundred and two."),
        _s("An empty stone corridor with a row of identical wooden doors, cold morning light, no people",
           "He was an Almoner. He is still alive.",
           "And he lives four doors from where Anneke sleeps."),
    ],
)

# ---- plot: the river ---------------------------------------------------------

event(
    id="the_flood",
    once=True,
    phase=0,
    requires=lambda w: w["river"]["days_to_flood"] <= 0 and not w["river"]["flooded"],
    weight=100000,
    apply=lambda w: (
        w["river"].update(flooded=True, level=100),
        w["factions"]["kiln"].update(coin=max(0, w["factions"]["kiln"]["coin"] - 6)),
        w.update(tension=w["tension"] + 5),
    ),
    scenes=lambda w: [
        _s("A river in violent flood at first light, brown water carrying broken timber, "
           "reeds flattened under the surface, low grey sky",
           "The Vell comes over its banks in the dark, without ceremony."),
        _s("A stone bridge with water breaking against its parapet, one arch already choked with debris, "
           "spray, nobody on it",
           "The Kiln's bridge holds. The approach road does not."),
        _s("A flooded valley floor seen from a chalk ridge at dawn, water standing in the fields, "
           "roofs above the waterline, no people",
           "By full light the valley has two halves and no crossing between them.",
           "The record said four more years."),
    ],
)

event(
    id="after_flood_counting",
    once=True,
    phase=0,
    requires=lambda w: w["river"]["flooded"],
    weight=800,
    apply=lambda w: w["factions"]["reedfolk"].update(
        standing=w["factions"]["reedfolk"]["standing"] + 2
    ),
    scenes=lambda w: [
        _s("Standing floodwater across low fields, a line of people wading with poles, seen distantly",
           "Nine days of standing water. Then the counting."),
        _s("A ruined timber jetty half submerged, rope trailing in the current",
           "The Reedfolk lose four boats and the whole of the lower reed bed."),
        _s("A young man in patched clothes standing at the water's edge looking at the far bank, "
           "seen from behind, grey light",
           "Odd Hallow does not say anything about the second bridge.",
           "He does not need to."),
    ],
)

# ---- texture: repeats, keeps the calendar honest -----------------------------

event(
    id="texture_kiln_firing",
    once=False,
    phase=0,
    requires=lambda w: True,
    weight=40,
    apply=lambda w: w["factions"]["kiln"].update(coin=w["factions"]["kiln"]["coin"] + 1),
    scenes=lambda w, rng: rng.choice([
        [
            _s("A brick kiln at night with the firing door glowing, smoke against a dark sky, silhouettes",
               "The Kiln fires twice a month and the whole valley knows it by the smell."),
            _s("Rows of unglazed grey pots cooling on a stone floor, shafts of dusty light",
               "Four hundred pieces. Perhaps thirty will crack."),
            _s("A cart loaded with straw-packed pottery on a stone bridge, morning mist, river below",
               "Every cart that crosses pays the toll."),
        ],
        [
            _s("A stack of split cordwood beside a brick kiln, wet bark, grey morning",
               "A firing takes nine cartloads of wood and two days of watching."),
            _s("A man asleep sitting upright against a warm kiln wall at night, blanket, low glow",
               "Somebody stays awake with it. It has always been somebody's turn."),
            _s("A cracked grey pot lying in mud beside a kiln, others stacked whole behind it",
               "The cracked ones go into the road.",
               "Half the Kiln's lane is made of its own failures."),
        ],
        [
            _s("Grey glazed bowls stacked in straw inside a wooden crate, close crop, dim light",
               "Marrowfield grey is not a colour anyone chose."),
            _s("A potter's wheel with wet clay on it in a dim workshop, hands not visible",
               "It is what the valley's clay does at the temperature its wood will reach."),
            _s("A wide chalk valley seen from above with a thin column of kiln smoke rising, overcast",
               "Buyers three days away ask for it by name",
               "and think it was a decision."),
        ],
    ]),
)

event(
    id="texture_reed_cutting",
    once=False,
    phase=0,
    requires=lambda w: not w["river"]["flooded"],
    weight=35,
    apply=lambda w: None,
    scenes=lambda w: [
        _s("Wide shallow reed beds at first light, mist on the water, a flat-bottomed boat moored",
           "The reeds are cut before the water rises."),
        _s("Bundled cut reeds stacked in a low boat, wet rope, close crop",
           "Thatch, baskets, boat caulking, winter fodder. All of it from the same water."),
        _s("A low turf-roofed hut with new pale thatch, grey sky, no people",
           "The Reedfolk have never needed the bridge for any of it.",
           "That is rather the point."),
    ],
)

event(
    id="texture_almoner_copying",
    once=False,
    phase=0,
    requires=lambda w: living(w, "anneke"),
    weight=30,
    apply=lambda w: None,
    scenes=lambda w, rng: rng.choice([
        [
            _s("A cold stone room lined with leather ledgers, one high window, dust in the light beam",
               "Every ledger is recopied before the ink begins to fail."),
            _s("A hand holding a quill above a half-copied page, ink pot, ruled lines, candlelight",
               "It takes an Almoner nine months to copy one flood record."),
            _s("A grey-robed figure seen from behind at a desk in a large empty archive",
               "Which is how a single altered year",
               "can survive four hundred honest hands."),
        ],
        [
            _s("Iron-gall ink being mixed in a shallow stone bowl with a bone spoon, close crop",
               "The Almoners make their own ink from oak galls and river iron."),
            _s("A page of handwriting where the older lines have faded to pale brown, close crop",
               "It bites into the paper, which is why it lasts,",
               "and eats the paper, which is why it must be copied."),
            _s("A row of leather ledger spines with dates tooled into them, cold side light",
           "Nothing in the archive is older than four hundred years.",
               "Everything in it claims to be."),
        ],
        [
            _s("An empty stone refectory with long benches and one bowl on a table, grey light",
               "There are eleven Almoners. There were forty once."),
            _s("A single grey-robed figure walking down a long stone corridor, seen from behind, small",
               "Nobody joins an order whose work is copying."),
            _s("A high archive window with rain against it, ledgers dim in the foreground",
               "They keep the flood record because someone has to.",
               "That has always been the whole of the argument."),
        ],
    ]),
)

event(
    id="texture_river_watch",
    once=False,
    phase=0,
    requires=lambda w: w["river"]["level"] >= 60 and not w["river"]["flooded"],
    weight=90,
    apply=lambda w: None,
    scenes=lambda w: [
        _s("A river running high and brown between chalk banks, reeds underwater, overcast",
           "The Vell is higher than it should be for the season."),
        _s("A notched wooden measuring post driven into a riverbank, water above the lower notches",
           "The post at the ford reads past the third notch."),
        _s("A stone bridge seen at dusk with fast water beneath, nobody crossing",
           "Nobody who lives here needs a record to tell them what that means.",
           "They look at it anyway."),
    ],
)

event(
    id="texture_market_day",
    once=False,
    phase=0,
    requires=lambda w: True,
    weight=25,
    apply=lambda w: None,
    scenes=lambda w: [
        _s("A small muddy market square with grey pottery laid on cloth, overcast, indistinct figures",
           "Market is on the Kiln's side of the river."),
        _s("Baskets of cut reeds and river fish beside stacked pots, wet ground",
           "The Reedfolk come across, pay the toll, and sell at the Kiln's prices."),
        _s("An empty market square at the end of day, trampled mud, one abandoned basket, low light",
           "They have done this for six generations",
           "and called it trade."),
    ],
)


# ---- act two: after the water ------------------------------------------------

event(
    id="anneke_confronts_the_forger",
    once=True,
    phase=13,
    requires=lambda w: w["secrets"]["forger_known"],
    weight=500,
    apply=lambda w: (
        w["secrets"].update(confessed=True),
        w["factions"]["almoners"].update(standing=w["factions"]["almoners"]["standing"] - 2),
        w.update(tension=w["tension"] + 2),
    ),
    scenes=lambda w: [
        _s("A narrow stone corridor with a single low wooden door, cold light, a grey-robed figure "
           "standing outside it, seen from behind",
           "She waits outside the door for most of an afternoon."),
        _s("A very old man sitting on the edge of a plain bed in a bare stone cell, hands in his lap, "
           "one small window, no expression readable",
           "He does not deny it. He asks her which entry she found."),
        _s("Close crop of two hands, one very old, resting on a closed ledger on a wooden table",
           "He says he was told the valley would not survive knowing.",
           "He does not say who told him."),
    ],
)

event(
    id="kiln_road_rebuild",
    once=True,
    phase=12,
    requires=lambda w: w["river"].get("receded") and living(w, "vesta"),
    weight=350,
    apply=lambda w: w["factions"]["kiln"].update(coin=max(0, w["factions"]["kiln"]["coin"] - 3)),
    scenes=lambda w: [
        _s("A washed-out stone approach road beside a river, deep ruts full of standing water, "
           "broken kerb stones",
           "The bridge survived. Forty yards of road did not."),
        _s("Men laying broken chalk and stone into a rutted roadbed, carts waiting, grey overcast",
           "The Kiln pays for the repair out of the ledger,",
           "because there is nobody else to pay for it."),
        _s("An older woman standing alone on a rebuilt road looking at a stone bridge, seen from behind",
           "Vesta Marrow writes the cost down in a column of its own",
           "and does not give it a name."),
    ],
)

event(
    id="second_bridge_permitted",
    once=True,
    phase=15,
    requires=lambda w: (
        w["river"].get("receded")
        and w["factions"]["reedfolk"]["standing"] >= 5
        and living(w, "odd")
    ),
    weight=450,
    apply=lambda w: (
        w["projects"].update(second_bridge="permitted"),
        w.update(tension=w["tension"] + 1),
    ),
    scenes=lambda w: [
        _s("A crowded low hall with a long table, men and women standing, lantern light, "
           "indistinct faces, tense posture",
           "The question is put at the Reeds-month assembly."),
        _s("A weathered plank with a charcoal drawing of a timber bridge on it, held up in lamplight",
           "Odd Hallow's drawing has been on the same plank for a year."),
        _s("A hand marking a tally in chalk on a slate, close crop, warm light",
           "It carries by four.",
           "The Kiln votes against and is outvoted for the first time in living memory."),
    ],
)

event(
    id="second_bridge_first_pile",
    once=True,
    phase=16,
    requires=lambda w: w["projects"].get("second_bridge") == "permitted",
    weight=400,
    apply=lambda w: w["projects"].update(second_bridge="building"),
    scenes=lambda w: [
        _s("A timber pile being driven into a riverbed by a rope-and-weight frame, shallow brown water, "
           "men on a raft, grey morning",
           "The first pile goes in at the narrow crossing on a still morning."),
        _s("A young man standing knee-deep in a river holding a plumb line against a timber post",
           "Odd Hallow is twenty now, and does not look pleased.",
           "He looks like a man checking a measurement."),
        _s("Two stone and timber crossings visible in the same wide valley view, river between chalk banks",
           "By the Long Dark the valley will have two crossings",
           "and one of them will be free."),
    ],
)

event(
    id="the_toll_falls",
    once=True,
    phase=18,
    requires=lambda w: w["projects"].get("second_bridge") == "building",
    weight=500,
    apply=lambda w: (
        w["factions"]["kiln"].update(coin=max(0, w["factions"]["kiln"]["coin"] - 4), standing=w["factions"]["kiln"]["standing"] - 2),
        w["projects"].update(toll="reduced"),
        w.update(tension=w["tension"] + 2),
    ),
    scenes=lambda w: [
        _s("A stone bridge with an empty toll post beside it, nobody waiting, morning mist",
           "The Kiln halves the toll before the second bridge is finished."),
        _s("A ledger page with a long column of figures and a much shorter one beside it, lamplight",
           "Vesta Marrow writes the new figure in the same steady hand",
           "she has used for thirty-two years."),
        _s("An older woman closing a ledger in a dim stone room, one lamp, seen slightly from behind",
           "She had said the toll was the only thing holding the valley together.",
           "She was wrong, and she is the one who worked out by how much."),
    ],
)

event(
    id="texture_chalk_cutting",
    once=False,
    phase=0,
    requires=lambda w: not w["river"]["flooded"],
    weight=30,
    apply=lambda w: None,
    scenes=lambda w: [
        _s("A white chalk cutting in a low hillside, tools leaning against the face, overcast",
           "The chalk comes out of the valley's own sides."),
        _s("Rough-cut chalk blocks stacked beside a cart track, wet grass",
           "It builds badly and burns well. The Kiln uses it for both."),
        _s("A pale chalk ridge above a river valley at dusk, no people",
           "Every wall in Marrowfield is the hill it stands on."),
    ],
)

event(
    id="texture_long_dark",
    once=False,
    phase=0,
    requires=lambda w: w["calendar"]["month"] == "Long Dark",
    weight=70,
    apply=lambda w: None,
    scenes=lambda w: [
        _s("A valley under low winter cloud at four in the afternoon, already nearly dark, frost",
           "In the Long Dark the light lasts six hours and is never direct."),
        _s("A single lit window in a turf-roofed hut seen across frozen reed beds",
           "The Reedfolk burn reed and dung. The Kiln burns chalk and wood."),
        _s("A frozen river edge with reeds locked in grey ice, flat light",
           "Nothing is decided in the Long Dark.",
           "Everything waits for the Rains."),
    ],
)

event(
    id="texture_bridge_watch",
    once=False,
    phase=0,
    requires=lambda w: w["projects"].get("second_bridge") == "building",
    weight=60,
    apply=lambda w: None,
    scenes=lambda w: [
        _s("A half-built timber bridge with three piles standing in shallow water, ropes, no workers",
           "The second bridge grows by about a pile a week."),
        _s("Rough-sawn timber beams stacked on a riverbank under wet sacking",
           "Nobody is paid for it. Everybody works on it."),
        _s("Two crossings in one wide valley view at dusk, one stone and old, one timber and unfinished",
           "The Kiln's bridge has stood for two hundred years.",
           "Nobody mentions how long the new one will last."),
    ],
)


# ----------------------------------------------------------------------------
# selection
# ----------------------------------------------------------------------------

def eligible(w: dict, day: int) -> list[dict]:
    out = []
    last = w.setdefault("last_fired", {})
    for e in EVENTS:
        if e["once"] and e["id"] in w["fired"]:
            continue
        if w["tension"] < e["phase"]:
            continue
        # Cooldown: a repeating event cannot fire again for `cooldown` days.
        # Without this the same texture beat lands four mornings running and
        # the channel looks broken even though the engine is behaving.
        cd = e.get("cooldown", 0 if e["once"] else 9)
        if day - last.get(e["id"], -9999) < cd:
            continue
        try:
            if not e["requires"](w):
                continue
        except Exception:
            continue
        out.append(e)
    return out


def pick(events: list[dict], rng: random.Random) -> dict:
    total = sum(e["weight"] for e in events)
    roll = rng.uniform(0, total)
    acc = 0.0
    for e in events:
        acc += e["weight"]
        if roll <= acc:
            return e
    return events[-1]


def step(world: dict, day: int) -> dict:
    """Advance the world one day. Returns the chronicle entry. Mutates world."""
    rng = random.Random(f"{world['seed']}:{day}")

    advance_calendar(world)
    step_river(world, rng)

    options = eligible(world, day)
    if not options:
        # Rather than crash the morning run, relax the cooldowns and try again.
        # A repeated beat is a much smaller failure than a missing episode.
        world["last_fired"] = {}
        options = eligible(world, day)
    if not options:
        raise RuntimeError("No eligible events — the world has painted itself into a corner.")

    chosen = pick(options, rng)
    before_tension = world["tension"]
    chosen["apply"](world)
    world["fired"].append(chosen["id"])
    world.setdefault("last_fired", {})[chosen["id"]] = day
    world["day"] = day

    # Quiet days accumulate pressure. Without this the arc fires everything it
    # can in the first week and then coasts for a year.
    if not chosen["once"]:
        world["quiet_days"] = world.get("quiet_days", 0) + 1
        # Pressure builds more slowly as the arc progresses, so the authored
        # beats spread across the year instead of all firing in week one.
        threshold = 4 + world["tension"] // 3
        if world["quiet_days"] >= threshold:
            world["quiet_days"] = 0
            world["tension"] += 1
    else:
        world["quiet_days"] = 0

    # Texture events accept the rng so they can vary their narration between
    # firings. Without that, a beat that fires sixty times a year produces sixty
    # episodes with identical words over different pictures, which reads as a
    # broken channel rather than a quiet one.
    try:
        scenes = chosen["scenes"](world, rng)
    except TypeError:
        scenes = chosen["scenes"](world)

    return {
        "day": day,
        "date": date_string(world),
        "event": chosen["id"],
        "recurring": not chosen["once"],
        "tension_before": before_tension,
        "tension_after": world["tension"],
        "river_level": world["river"]["level"],
        "days_to_flood": world["river"]["days_to_flood"],
        "flooded": world["river"]["flooded"],
        "scenes": scenes,
        "eligible_count": len(options),
    }
