# Chart goldens

Each input (`<kind>.csv` or `<kind>.json`) and the output `wiki.py chart` gives for it (`<kind>.md`), rendered
against the fixture folder, whose files the rows cite. `../../test_charts.py` holds each input's title and checks
the outputs; `python3 tests/test_charts.py --update` rewrites them and the render probe page.

The bar, pie, gantt and timeline inputs carry only figures their cited fixture file states, and the fixture wiki
carries the same charts. `line.json` is synthetic: no fixture file states three dated figures, so its periods and
values are made up to exercise the tool, and it cites an existing file only because the tool requires one. It is
not fixture data; never copy it into a fixture page.
