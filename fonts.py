"""Fonts, fetched on first use and never committed.

Every font here is under the SIL Open Font License, taken from the Google
Fonts repository at a pinned commit and checked against git's own hash of
the file before it is used. They land in .work/fonts (ignored by git) with
the OFL text that travels with them.

The code used to name macOS system fonts by path -- Snell Roundhand, Big
Caslon, Baskerville, Times New Roman, Georgia -- which exist on no other
system, and whose licences were never meant for handing films on.

Stdlib only: Blender's Python, the venvs and the MCP servers all use it.
"""

from __future__ import annotations

import hashlib
import os
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, ".work", "fonts")
COMMIT = "9710da1eacb3be272583c3224dcb70f9da6eadbb"
BASE = f"https://raw.githubusercontent.com/google/fonts/{COMMIT}/ofl/"

# what each is for: (directory in google/fonts, file, git blob hash)
FONTS = {
    # the title and chapter cards (was Snell Roundhand)
    "script": ("pinyonscript", "PinyonScript-Regular.ttf", "fb2458f7cdd09cffdcf6b8008617fc9d203ff04c"),
    # place cards, book spines, the visions' labels (was Big Caslon)
    "caslon": ("librecaslondisplay", "LibreCaslonDisplay-Regular.ttf", "85304456a69e0d6bb48255cf8ce73f86dc471f3d"),
    # relativity's panels (was Georgia); one variable-weight file, 400 to 700
    "serif": ("librebaskerville", "LibreBaskerville[wght].ttf", "eae4eba83203138da3a3a7603b598b7ebc5a5238"),
    # the Petersburg street signs, one of them in Russian (was Baskerville;
    # Libre Baskerville has no Cyrillic, and a sign with no glyphs renders
    # blank) -- Old Standard is cut after Russian book faces of the 1800s
    "sign": ("oldstandardtt", "OldStandard-Regular.ttf", "655abd750736123c26a11c69fa2ad711a5ac22d7"),
    # the mathematics in the visions, pi and infinity among it (was Times
    # New Roman Italic); STIX Two is made for mathematics
    "italic": ("stixtwotext", "STIXTwoText-Italic[wght].ttf", "f7b444d116d5f00e678abb9f0b2e480869a31718"),
}
LICENCES = {
    "pinyonscript": "75bbb4792e1403280ce87cbcd7de0c7ea6ceccf2",
    "librecaslondisplay": "80e580640e38632d712deebc31a592dee686ec92",
    "librebaskerville": "92b1e6ca1cfa6f9dfe4ec67468596606fc334c4f",
    "oldstandardtt": "618d209cf110925dabf2c533df818e701fa068da",
    "stixtwotext": "4190bc7de7812f55886f062ce7cbf58f6d667796",
}


def _blob_hash(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _fetch(folder: str, name: str, want: str) -> str:
    out = os.path.join(CACHE, folder, name)
    if os.path.exists(out):
        with open(out, "rb") as fh:
            if _blob_hash(fh.read()) == want:
                return out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    url = BASE + folder + "/" + urllib.parse.quote(name)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    if _blob_hash(data) != want:
        raise RuntimeError(f"{url} is not the file pinned in fonts.py")
    tmp = f"{out}.{os.getpid()}.part"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, out)
    return out


def path(role: str) -> str:
    """Local path of the font for `role` (see FONTS), fetching it if needed."""
    folder, name, want = FONTS[role]
    _fetch(folder, "OFL.txt", LICENCES[folder])
    return _fetch(folder, name, want)


def fetch_all() -> dict:
    """Fetch every font now -- before Blender processes start in parallel."""
    return {role: path(role) for role in FONTS}


if __name__ == "__main__":
    for role, p in fetch_all().items():
        print(f"{role:7s} {p}")
