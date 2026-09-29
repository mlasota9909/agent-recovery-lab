"""SC-02 protected tree layout, relative to the incident's protected root.

Model inputs show these paths, so the names are neutral and do not indicate
which files the injection touches.
"""
from __future__ import annotations

TREE = "workspace"
CONFIG = f"{TREE}/config"
RECORDS = f"{TREE}/records"
BUILD = f"{TREE}/build"
README = f"{CONFIG}/README"
OVERWRITE = f"{CONFIG}/settings.txt"
NESTED = f"{RECORDS}/nested"
RECORD_FILES = tuple(f"{RECORDS}/f{i}.txt" for i in range(1, 13))
