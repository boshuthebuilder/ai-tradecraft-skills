#!/usr/bin/env python3
"""Capture each scenario's Deadlines page as the family-ai-os roll-up renders it, so the tests read the real bytes.

The scenario folders beside this script hold the wiki pages and, once captured, `01 Deadlines/01 Deadlines.md`. The
suite never imports family-ai-os: run this by hand, with a checkout's `src` on the path, only to refresh the capture.

    python3 capture.py --src <family-ai-os>/src [--now 2024-06-30]

The page is rendered by `roll_up_deadlines(root, wiki_dir, None, now)` into a copy and copied back; the roll-up's
own frontmatter (`last-updated`) is the `--now` day, which the tests' frozen clock matches.
"""
import argparse
import datetime
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join("01 Deadlines", "01 Deadlines.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--now", default="2024-06-30")
    a = ap.parse_args()
    sys.path.insert(0, a.src)
    from family_ai.storage import wiki_rollups
    now = datetime.datetime.strptime(a.now, "%Y-%m-%d").replace(hour=12)
    for name in sorted(os.listdir(HERE)):
        folder = os.path.join(HERE, name)
        if not os.path.isdir(folder):
            continue
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "root")
            wiki = os.path.join(root, "Wiki")
            shutil.copytree(folder, wiki)
            os.makedirs(os.path.join(wiki, "01 Deadlines"), exist_ok=True)
            page = os.path.join(wiki, PAGE)
            if os.path.exists(page):
                os.remove(page)
            result = wiki_rollups.roll_up_deadlines(__import__("pathlib").Path(root), "Wiki", None, now)
            os.makedirs(os.path.dirname(os.path.join(folder, PAGE)), exist_ok=True)
            shutil.copy(page, os.path.join(folder, PAGE))
            print(name, result)


if __name__ == "__main__":
    main()
