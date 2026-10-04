#!/usr/bin/env python3
"""Capture each scenario's Deadlines page as a real roll-up renders it, so the tests read the real bytes.

The scenario folders beside this script hold the wiki pages and, once captured, `01 Deadlines/01 Deadlines.md`. The
suite never imports a deployment: run this by hand, naming the renderer to capture, only to refresh the capture.

    python3 capture.py --renderer <module>:<function> [--pythonpath <folder> ...] [--now 2024-06-30]

`--renderer` names a function importable once each `--pythonpath` folder is on `sys.path`; there is no default. It is
called as `function(root, wiki_dir, None, now)`: `root` is a `pathlib.Path` to a folder holding the wiki, `wiki_dir`
the wiki's folder name under it, the third argument a project id (`None` here: nothing is recorded) and `now` a
`datetime.datetime`. It must write `<wiki_dir>/01 Deadlines/01 Deadlines.md` under `root`, its own `last-updated`
frontmatter the `--now` day (which the tests' frozen clock matches), and return a mapping describing the run, which
is printed beside the scenario's name.
"""
import argparse
import datetime
import importlib
import os
import pathlib
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join("01 Deadlines", "01 Deadlines.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--renderer", required=True, metavar="MODULE:FUNCTION", help="the function that renders the page")
    ap.add_argument("--pythonpath", action="append", default=[], metavar="FOLDER",
                    help="a folder to put on sys.path before the module is imported (repeatable)")
    ap.add_argument("--now", default="2024-06-30")
    a = ap.parse_args()
    module, _, func = a.renderer.partition(":")
    if not module or not func:
        ap.error("--renderer is MODULE:FUNCTION")
    sys.path[:0] = [os.path.abspath(p) for p in a.pythonpath]
    render = getattr(importlib.import_module(module), func)
    now = datetime.datetime.strptime(a.now, "%Y-%m-%d").replace(hour=12)
    for name in sorted(os.listdir(HERE)):
        folder = os.path.join(HERE, name)
        if not os.path.isdir(folder) or name == "__pycache__":
            continue
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "root")
            wiki = os.path.join(root, "Wiki")
            shutil.copytree(folder, wiki)
            os.makedirs(os.path.join(wiki, "01 Deadlines"), exist_ok=True)
            page = os.path.join(wiki, PAGE)
            if os.path.exists(page):
                os.remove(page)
            result = render(pathlib.Path(root), "Wiki", None, now)
            os.makedirs(os.path.dirname(os.path.join(folder, PAGE)), exist_ok=True)
            shutil.copy(page, os.path.join(folder, PAGE))
            print(name, result)


if __name__ == "__main__":
    main()
