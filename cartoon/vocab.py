"""The words a cartoon document may use, and nothing else.

Stdlib only. `script.py` checks documents against these under any venv, and
the Blender side animates from the same tables, so an `act` the document
may name is by construction one the renderer knows. An unknown name is an
error with the list in it, never a shrug and a character standing still.
"""

from __future__ import annotations

# What a speaker's body does on its line.
ACTS = {
    "write":         "chalks the line's `board` onto the slate",
    "listen":        "stays still, head cocked toward a sound",
    "sniff":         "sniffs: nostrils flare, head bobs, antennae quiver",
    "turn_to_voice": "turns toward whoever spoke last (Euler: slightly off, he is blind)",
    "savour":        "eyes shut, rolls a taste around",
    "lean_in":       "leans toward the other character",
    "tap_temple":    "taps a finger on the temple",
    "shrug":         "shoulders (or arms) up and down",
    "laugh":         "a laugh through the body",
    "puff":          "breathes out a cloud of scent",
    "fan_tongue":    "fans its burning tongue with a hand",
    "count":         "counts on its fingers, one per clause",
    "realise":       "stops, lifts a finger: the idea arriving",
    "gasp":          "a sharp intake, eyes wide",
    "spin":          "a slow delighted spin in the air",
    "tap_board":     "taps the slate with the chalk",
    "tilt":          "tilts the head, antennae following",
    "turn_hand":     "turns an open hand a quarter turn",
    "pinch":         "a chef's pinch of seasoning",
    "touch_hand":    "rests a hand on the other's hand",
    "exit":          "zips out of the window",
}

# Beats with no words.
DOS = {
    "title":         "a title card over the establishing shot",
    "ship_descends": "the ship comes down through the snow",
    "window_opens":  "the study window swings open; something drifts in",
    "lick":          "the tongue goes out and licks along `target` on the slate",
    "vision":        "cut to the taste: `vision` names which one",
    "write":         "Euler chalks `board` without speaking",
    "ship_toots":    "the ship toots outside and puffs coloured steam",
    "slurp":         "one enormous lick takes the whole slate clean",
    "knock":         "a knock at the study door",
    "skywriting":    "the ship's steam writes the identity across the dawn sky",
}

VISIONS = {
    "basel":    "rings of flavour, each smaller, settling on one warm glow",
    "harmonic": "a flavour that keeps climbing, slowly, and never settles",
    "product":  "the pages of a cookbook fly into a rack of spice jars",
    "wheel":    "rising bread curls into a circle round the flavour wheel",
    "nothing":  "every colour drains into one perfectly clear drop",
}

SCENES = {"petersburg": ("night", "dawn"), "study": ("night", "morning")}
