from bakery import assert_equal
from drafter import *
from dataclasses import dataclass
import random
import time

# Tennis Serve Simulator
# Pick a serve type, target, and side. The site decides if the
# serve went in and keeps track of your serve percentages.


# Global constants (never changed while the site runs).
# Base chance that a serve goes in, based on where it's aimed.
# Safer targets (body) have a higher chance than the lines (T, wide).
BASE_CHANCE = {"body": 0.80, "T": 0.65, "wide": 0.60}

# How much each serve type changes the chance.
# Kick is the safest serve, flat is the riskiest.
TYPE_ADJUSTMENT = {"flat": -0.10, "slice": 0.0, "kick": 0.05}

RUSHED_PENALTY = 0.15
SLICE_WIDE_DEUCE_BONUS = 0.05

# A serve is "rushed" if it's hit less than this many seconds
# after the previous serve.
RUSH_LIMIT = 5.0

SERVE_TYPES = ["flat", "slice", "kick"]
TARGETS = ["T", "body", "wide"]
SIDES = ["deuce", "ad"]


@dataclass
class Serve:
    serve_type: str
    target: str
    side: str
    rushed: bool
    landed_in: bool


@dataclass
class State:
    player_name: str
    history: list[Serve]
    total_serves: int
    serves_in: int
    last_serve_time: float   # 0.0 means no serve has been hit yet


# ---------------------------------------------------------------
# Helper functions (logic only, no pages)
# ---------------------------------------------------------------

def chance_to_go_in(serve_type: str, target: str, side: str,
                    rushed: bool) -> float:
    """Returns the chance (0 to 1) that this serve lands in."""
    chance = BASE_CHANCE[target] + TYPE_ADJUSTMENT[serve_type]
    if rushed:
        chance = chance - RUSHED_PENALTY
    if serve_type == "slice" and target == "wide" and side == "deuce":
        chance = chance + SLICE_WIDE_DEUCE_BONUS
    # round(number, 2) keeps 2 decimal places. Adding decimals can leave
    # tiny errors (like 0.7000000001), so rounding keeps tests exact.
    return round(chance, 2)


def serve_goes_in(chance: float, roll: float) -> bool:
    """Returns True if the random roll (0 to 1) is less than the chance."""
    return roll < chance


def is_rushed(last_time: float, now: float) -> bool:
    """
    Returns True if this serve came less than RUSH_LIMIT seconds
    after the last one. The first serve (last_time is 0.0) is never
    rushed.
    """
    if last_time == 0.0:
        return False
    return now - last_time < RUSH_LIMIT


def record_serve(state: State, serve: Serve, now: float) -> State:
    """Adds a serve to the history, updates the totals, and saves the time."""
    state.history.append(serve)
    state.total_serves = state.total_serves + 1
    if serve.landed_in:
        state.serves_in = state.serves_in + 1
    state.last_serve_time = now
    return state


def rushed_message(rushed: bool) -> str:
    """Returns the message shown on the result page about rushing."""
    if rushed:
        return ("That serve was RUSHED! Wait at least "
                + str(round(RUSH_LIMIT)) + " seconds between serves.")
    return "Nice tempo, that serve wasn't rushed."


def serve_percentage(made: int, total: int) -> int:
    """Turns made/total into a whole-number percent. 0 serves gives 0%."""
    if total == 0:
        return 0
    return round(made / total * 100)


def count_serves_of_type(history: list[Serve],
                         serve_type: str) -> list[int]:
    """Returns [serves made, total serves] for one serve type."""
    made = 0
    total = 0
    for serve in history:
        if serve.serve_type == serve_type:
            total = total + 1
            if serve.landed_in:
                made = made + 1
    return [made, total]


def best_serve(history: list[Serve]) -> str:
    """Returns the serve type with the highest serve percentage."""
    best_type = "none yet"
    best_percent = -1
    for serve_type in SERVE_TYPES:
        counts = count_serves_of_type(history, serve_type)
        if counts[1] > 0:
            percent = serve_percentage(counts[0], counts[1])
            if percent > best_percent:
                best_percent = percent
                best_type = serve_type
    return best_type


def in_or_out(landed_in: bool) -> str:
    """Returns "IN" or "OUT" for a serve result."""
    if landed_in:
        return "IN"
    return "OUT"


def yes_or_no(value: bool) -> str:
    """Returns "yes" or "no" for a True/False value."""
    if value:
        return "yes"
    return "no"


def percent_text(made: int, total: int) -> str:
    """Returns a percent as text, like "75%"."""
    return str(serve_percentage(made, total)) + "%"


def history_rows(history: list[Serve]) -> list[list[str]]:
    """Turns the list of serves into rows for the history table."""
    rows = []
    number = 1
    for serve in history:
        rows.append([str(number), serve.serve_type, serve.target,
                     serve.side, yes_or_no(serve.rushed),
                     in_or_out(serve.landed_in)])
        number = number + 1
    return rows


# ---------------------------------------------------------------
# Routes (pages)
# ---------------------------------------------------------------

@route
def index(state: State) -> Page:
    """Home page: name box, total serves, and overall serve %."""
    return Page(state, [
        Header("Tennis Serve Simulator"),
        "Pick a serve and see if it goes in!",
        "Player name:",
        TextBox("name", state.player_name),
        "Total serves: " + str(state.total_serves)
        + " | In: " + str(state.serves_in),
        "Overall serve %: "
        + percent_text(state.serves_in, state.total_serves),
        Button("Start", set_name),
        Button("View History", view_history),
    ])


@route
def set_name(state: State, name: str) -> Page:
    """Saves the player's name, then shows the serve form."""
    # .strip() removes spaces from the start and end of the text,
    # so a name of only spaces counts as empty.
    if name.strip() == "":
        state.player_name = "Player"
    else:
        state.player_name = name.strip()
    return serve_form(state)


@route
def serve_form(state: State) -> Page:
    """Page where the player picks serve type, target, and side."""
    return Page(state, [
        Header("Pick Your Serve, " + state.player_name),
        "Serve type:",
        SelectBox("serve_type", SERVE_TYPES, "flat"),
        "Target:",
        SelectBox("target", TARGETS, "body"),
        "Side:",
        SelectBox("side", SIDES, "deuce"),
        "Serves hit less than " + str(round(RUSH_LIMIT))
        + " seconds apart count as rushed.",
        Button("Serve!", hit_serve),
        Button("Home", index),
    ])


@route
def hit_serve(state: State, serve_type: str, target: str,
              side: str) -> Page:
    """
    Simulates one serve, saves it to the history, and shows the result.

    Not unit tested: random.random() and time.time() give a different
    number every run, so the result page can't be predicted. The logic
    it uses (is_rushed, chance_to_go_in, serve_goes_in, record_serve,
    rushed_message) is tested below instead.
    """
    # time.time() returns the current time in seconds. Comparing it to
    # the last serve's time tells us how fast the player served again.
    now = time.time()
    rushed = is_rushed(state.last_serve_time, now)

    chance = chance_to_go_in(serve_type, target, side, rushed)
    # random.random() returns a random decimal from 0 up to (not
    # including) 1, like rolling a die for whether the serve goes in.
    landed_in = serve_goes_in(chance, random.random())

    state = record_serve(state, Serve(serve_type, target, side, rushed,
                                      landed_in), now)

    counts = count_serves_of_type(state.history, serve_type)
    return Page(state, [
        Header("Result"),
        "Your " + serve_type + " serve to the " + target
        + " (" + side + " side) was...",
        Header(in_or_out(landed_in) + "!", 2),
        rushed_message(rushed),
        serve_type + " serve %: " + percent_text(counts[0], counts[1])
        + " (" + str(counts[0]) + " of " + str(counts[1]) + ")",
        Button("Serve Again", serve_form),
        Button("View Stats", view_stats),
        Button("Home", index),
    ])


@route
def view_history(state: State) -> Page:
    """Shows a table of every serve hit so far."""
    if len(state.history) == 0:
        return Page(state, [
            Header("Serve History"),
            "No serves yet!",
            Button("Home", index),
        ])
    return Page(state, [
        Header("Serve History"),
        Table(history_rows(state.history),
              ["#", "Type", "Target", "Side", "Rushed", "Result"]),
        Button("View Stats", view_stats),
        Button("Clear History", clear_history),
        Button("Home", index),
    ])


@route
def view_stats(state: State) -> Page:
    """Shows the serve % for each serve type and the best serve."""
    if state.total_serves == 0:
        return Page(state, [
            Header("Serve Stats"),
            "No serves yet!",
            Button("Home", index),
        ])
    rows = []
    for serve_type in SERVE_TYPES:
        counts = count_serves_of_type(state.history, serve_type)
        rows.append([serve_type,
                     str(counts[0]) + " / " + str(counts[1]),
                     percent_text(counts[0], counts[1])])
    return Page(state, [
        Header("Serve Stats"),
        Table(rows, ["Serve type", "In / Total", "Serve %"]),
        "Best serve: " + best_serve(state.history),
        Button("View History", view_history),
        Button("Home", index),
    ])


@route
def clear_history(state: State) -> Page:
    """Deletes all serves, resets the totals and timer, and goes home."""
    state.history = []
    state.total_serves = 0
    state.serves_in = 0
    # Reset the timer too, so the next serve isn't marked rushed.
    state.last_serve_time = 0.0
    return index(state)


# ---------------------------------------------------------------
# Tests
# ---------------------------------------------------------------

# chance_to_go_in
assert_equal(chance_to_go_in("slice", "body", "deuce", False), 0.8)
assert_equal(chance_to_go_in("flat", "T", "ad", False), 0.55)
assert_equal(chance_to_go_in("kick", "wide", "ad", True), 0.5)
assert_equal(chance_to_go_in("slice", "wide", "deuce", False), 0.65)

# serve_goes_in
assert_equal(serve_goes_in(0.8, 0.5), True)
assert_equal(serve_goes_in(0.8, 0.9), False)
assert_equal(serve_goes_in(0.8, 0.8), False)

# is_rushed
assert_equal(is_rushed(0.0, 100.0), False)    # first serve
assert_equal(is_rushed(100.0, 103.0), True)   # 3 seconds later
assert_equal(is_rushed(100.0, 110.0), False)  # 10 seconds later
assert_equal(is_rushed(100.0, 105.0), False)  # exactly the limit

# record_serve
assert_equal(
    record_serve(State("Ryan", [], 0, 0, 0.0),
                 Serve("flat", "T", "deuce", False, True), 50.0),
    State("Ryan", [Serve("flat", "T", "deuce", False, True)], 1, 1, 50.0))
assert_equal(
    record_serve(State("Ryan", [Serve("flat", "T", "deuce", False, True)],
                       1, 1, 50.0),
                 Serve("kick", "wide", "ad", True, False), 52.0),
    State("Ryan", [Serve("flat", "T", "deuce", False, True),
                   Serve("kick", "wide", "ad", True, False)], 2, 1, 52.0))

# rushed_message
assert_equal(rushed_message(True),
             "That serve was RUSHED! Wait at least 5 seconds between serves.")
assert_equal(rushed_message(False), "Nice tempo, that serve wasn't rushed.")

# serve_percentage and percent_text
assert_equal(serve_percentage(3, 4), 75)
assert_equal(serve_percentage(2, 3), 67)
assert_equal(serve_percentage(0, 0), 0)
assert_equal(percent_text(1, 2), "50%")

# in_or_out and yes_or_no
assert_equal(in_or_out(True), "IN")
assert_equal(in_or_out(False), "OUT")
assert_equal(yes_or_no(True), "yes")
assert_equal(yes_or_no(False), "no")

# count_serves_of_type and best_serve
TEST_HISTORY = [
    Serve("flat", "T", "deuce", False, False),
    Serve("kick", "body", "ad", False, True),
    Serve("kick", "wide", "deuce", True, True),
    Serve("flat", "body", "ad", False, True),
]
assert_equal(count_serves_of_type(TEST_HISTORY, "flat"), [1, 2])
assert_equal(count_serves_of_type(TEST_HISTORY, "kick"), [2, 2])
assert_equal(count_serves_of_type(TEST_HISTORY, "slice"), [0, 0])
assert_equal(count_serves_of_type([], "flat"), [0, 0])
assert_equal(best_serve(TEST_HISTORY), "kick")
assert_equal(best_serve([]), "none yet")

# history_rows
assert_equal(history_rows([]), [])
assert_equal(history_rows(TEST_HISTORY),
             [["1", "flat", "T", "deuce", "no", "OUT"],
              ["2", "kick", "body", "ad", "no", "IN"],
              ["3", "kick", "wide", "deuce", "yes", "IN"],
              ["4", "flat", "body", "ad", "no", "IN"]])

# index
assert_equal(
    index(State("Ryan", TEST_HISTORY, 4, 3, 100.0)),
    Page(State("Ryan", TEST_HISTORY, 4, 3, 100.0), [
        Header("Tennis Serve Simulator"),
        "Pick a serve and see if it goes in!",
        "Player name:",
        TextBox("name", "Ryan"),
        "Total serves: 4 | In: 3",
        "Overall serve %: 75%",
        Button("Start", set_name),
        Button("View History", view_history),
    ]))

# set_name
assert_equal(
    set_name(State("", [], 0, 0, 0.0), "  "),
    serve_form(State("Player", [], 0, 0, 0.0)))
assert_equal(
    set_name(State("", [], 0, 0, 0.0), " Ryan "),
    serve_form(State("Ryan", [], 0, 0, 0.0)))

# serve_form
assert_equal(
    serve_form(State("Ryan", [], 0, 0, 0.0)),
    Page(State("Ryan", [], 0, 0, 0.0), [
        Header("Pick Your Serve, Ryan"),
        "Serve type:",
        SelectBox("serve_type", SERVE_TYPES, "flat"),
        "Target:",
        SelectBox("target", TARGETS, "body"),
        "Side:",
        SelectBox("side", SIDES, "deuce"),
        "Serves hit less than 5 seconds apart count as rushed.",
        Button("Serve!", hit_serve),
        Button("Home", index),
    ]))

# view_history
assert_equal(
    view_history(State("Ryan", [], 0, 0, 0.0)),
    Page(State("Ryan", [], 0, 0, 0.0), [
        Header("Serve History"),
        "No serves yet!",
        Button("Home", index),
    ]))
assert_equal(
    view_history(State("Ryan", TEST_HISTORY, 4, 3, 100.0)),
    Page(State("Ryan", TEST_HISTORY, 4, 3, 100.0), [
        Header("Serve History"),
        Table([["1", "flat", "T", "deuce", "no", "OUT"],
               ["2", "kick", "body", "ad", "no", "IN"],
               ["3", "kick", "wide", "deuce", "yes", "IN"],
               ["4", "flat", "body", "ad", "no", "IN"]],
              ["#", "Type", "Target", "Side", "Rushed", "Result"]),
        Button("View Stats", view_stats),
        Button("Clear History", clear_history),
        Button("Home", index),
    ]))

# view_stats
assert_equal(
    view_stats(State("Ryan", [], 0, 0, 0.0)),
    Page(State("Ryan", [], 0, 0, 0.0), [
        Header("Serve Stats"),
        "No serves yet!",
        Button("Home", index),
    ]))
assert_equal(
    view_stats(State("Ryan", TEST_HISTORY, 4, 3, 100.0)),
    Page(State("Ryan", TEST_HISTORY, 4, 3, 100.0), [
        Header("Serve Stats"),
        Table([["flat", "1 / 2", "50%"],
               ["slice", "0 / 0", "0%"],
               ["kick", "2 / 2", "100%"]],
              ["Serve type", "In / Total", "Serve %"]),
        "Best serve: kick",
        Button("View History", view_history),
        Button("Home", index),
    ]))

# clear_history
assert_equal(
    clear_history(State("Ryan", TEST_HISTORY, 4, 3, 100.0)),
    index(State("Ryan", [], 0, 0, 0.0)))

start_server(State("", [], 0, 0, 0.0))
