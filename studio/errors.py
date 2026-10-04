"""The one line of an engine's output worth putting in front of a caller.

Engines are noisy. GIMP announces itself and complains about the display it
does not have, torch warns about the future, and the reason something
actually failed is usually the last line that is none of those.
"""

NOISE = ("CVDisplayLink", "GIMP is started", "Welcome to GIMP",
         "stray image", "batch command executed", "Warning", "warn(")


def last_line(text: str) -> str:
    """The last line of `text` that says something, or a stand-in."""
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line and not any(n in line for n in NOISE):
            return line
    return "it gave no reason"


def failed(e: BaseException) -> str:
    """A job's FAILED line for `e`. It starts a line of its own, since a progress bar may have
    left the last one unfinished, and it is one line, so a reason spread over several (a loader's
    error, then the file it was reading) reaches the person whole."""
    msg = e.args[0] if isinstance(e, KeyError) and e.args else str(e)
    return "\nFAILED " + (" ".join(str(msg).split()) or type(e).__name__)
