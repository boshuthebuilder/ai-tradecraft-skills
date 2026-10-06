"""Three invented folders that arrange one pool of invented documents three ways, for the structure tests.

A smaller equivalent of the three folders the structure assessment was first tried on: `well_kept` is a tidy tree,
`half_messy` is that tree with one mixed catch-all folder (`Money/Misc`, 21 documents) and a copy of one year's health
folder, and `messy` files the same documents in accidental homes (a flat dump, two catch-alls, strays at the root, an old
laptop's copy of the half-sorted folders under a chain of single-child folders). Nothing is real: every name, party and
document is made up, and the same pool gives every arrangement, so a difference between two folders is a difference of
arrangement and never of content.

`build(dest)` lays out each folder as small text files, audits it with the real `audit.py` (a frozen clock, so the
manifest is the same every run) and writes a hand-made card per content, as `cards.py` would (`card_meta.path` included).
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "..", "tools")
NOW = "1788696000"      # 2026-09-06T12:00:00Z
OWNER, CHILD = "Morgan Example", "Kit Example"
FIN, HOME, HEALTH, EDU, WORK = "Finance & Tax", "Home & Household", "Health", "Education", "Work & Career"
POOL = {}      # key -> {issuer, kind, date, party, category, name}
ORDER = []     # keys in definition order


def doc(key, kind, issuer, date, category, party=OWNER, name=None):
    POOL[key] = {"key": key, "kind": kind, "issuer": issuer, "date": date, "party": party, "category": category,
                 "name": name or "%s %s" % (kind, date)}
    ORDER.append(key)


def series(prefix, kind, issuer, category, dates, party=OWNER, name=None):
    for i, d in enumerate(dates):
        doc("%s_%s" % (prefix, d.replace("-", "")), kind, issuer, d, category, party,
            name="%s %s" % (name or kind, d))


series("stmt", "Bank statement", "Example Bank plc", FIN, ["2023-01-31", "2023-04-30", "2023-07-31", "2023-10-31",
                                                           "2024-01-31", "2024-04-30"])
series("sa22", "Tax return", "Example Revenue Service", FIN, ["2022-12-10", "2022-12-20", "2023-01-05"])
series("sa23", "Tax return", "Example Revenue Service", FIN, ["2023-12-10", "2023-12-20", "2024-01-05"])
series("pension", "Pension statement", "Example Pension Trust", FIN, ["2022-06-01", "2023-06-01"])
series("carins", "Insurance renewal", "Example Mutual", FIN, ["2021-03-12", "2022-03-15", "2023-03-13", "2024-03-11"])
series("carsvc", "Service receipt", "Example Motors", HOME, ["2022-04-08", "2023-04-08", "2024-04-08"])
series("gp21", "GP letter", "Example Surgery", HEALTH, ["2021-06-02", "2021-11-20"])
series("hosp22", "Hospital letter", "Example Health Trust", HEALTH, ["2022-02-17", "2022-04-11", "2022-05-30"])
doc("flu22", "Vaccination record", "Example Surgery", "2022-10-05", HEALTH, party=CHILD)
series("gp23", "GP letter", "Example Surgery", HEALTH, ["2023-01-19", "2023-05-22", "2023-10-02", "2023-11-14"])
series("lease", "Tenancy agreement", "Example Lettings", HOME, ["2021-05-01", "2022-05-01", "2023-05-01"])
series("ut22", "Energy bill", "Example Energy Ltd", HOME, ["2022-08-02", "2022-09-15"])
series("ut23", "Water bill", "Example Water", HOME, ["2023-02-02", "2023-08-02", "2023-09-15"])
series("ut24", "Broadband bill", "Example Telecom", HOME, ["2024-02-02", "2024-08-02", "2024-09-15"])
series("school", "School report", "Example School", EDU, ["2022-07-20", "2023-07-20", "2024-07-20"], party=CHILD)
doc("trip", "Consent form", "Example School", "2024-05-02", EDU, party=CHILD)
series("emp", "Employment contract", "Example Employer Ltd", WORK, ["2020-09-01", "2022-04-01", "2023-04-01"])
series("pay", "Payslip", "Example Employer Ltd", WORK, ["2023-01-31", "2023-02-28", "2023-03-31", "2023-04-30"])
CORE = list(ORDER)
# the catch-all of Half Messy: bills, letters and receipts of every kind, a few of them named by a scanner
series("misc_ut", "Council tax letter", "Example Borough Council", HOME,
       ["2024-%02d-01" % m for m in range(3, 11)])
series("misc_gp", "GP letter", "Example Surgery", HEALTH, ["2024-01-10", "2024-02-10", "2024-03-10"])
series("misc_pen", "Pension statement", "Example Pension Trust", FIN, ["2024-06-01"])
series("misc_tax", "Tax receipt", "Example Revenue Service", FIN, ["2024-01-31", "2024-07-31"])
series("misc_car", "Service receipt", "Example Motors", HOME, ["2024-10-08", "2024-11-08"])
series("misc_sch", "School report", "Example School", EDU, ["2024-12-20", "2024-12-21", "2024-12-22"],
       party=CHILD)
series("misc_pay", "Payslip", "Example Employer Ltd", WORK, ["2024-01-31", "2024-02-28"])
MISC = [k for k in ORDER if k.startswith("misc_")]
SCANNED = {MISC[i]: n for i, n in zip((0, 4, 6, 9, 12, 15), ("Scan 002", "Document (3)", "IMG_4410", "Scan 017",
                                                             "Screenshot 2024-08-26 at 10.02.11", "Document (18)"))}
assert len(MISC) == 21


def text(key):
    d = POOL[key]
    return "%s\n%s\nFor: %s\nDate: %s\nReference: %s\n" % (d["issuer"], d["kind"].upper(), d["party"], d["date"],
                                                         key.upper())


def tidy(key):
    """Where a careful person files a core document."""
    d, y = POOL[key], POOL[key]["date"][:4]
    name = "%s.txt" % d["name"]
    if key.startswith("carins"):
        return "Car/Insurance/" + name
    if key.startswith("carsvc"):
        return "Car/Servicing/" + name
    if d["category"] == HEALTH:
        return "Health/%s/%s" % (y, name)
    if key.startswith("lease"):
        return "Home/Lease/" + name
    if key.startswith("ut"):
        return "Home/Utilities/%s/%s" % (y, name)
    if d["party"] == CHILD and d["category"] == EDU:
        return "Kit/School/" + name
    if key.startswith("stmt"):
        return "Money/Bank/" + name
    if key.startswith(("sa22", "sa23")):
        return "Money/Tax/%s/%s" % ("2022" if key.startswith("sa22") else "2023", name)
    if key.startswith("pension"):
        return "Money/Pension/" + name
    if key.startswith("pay"):
        return "Work/Payslips/%s/%s" % (y, name)
    return "Work/Employment/" + name


def well_kept():
    return [(tidy(k), k) for k in CORE]


def half_messy():
    rows = [(tidy(k), k) for k in CORE]
    rows += [("Money/Misc/%s.txt" % SCANNED.get(k, POOL[k]["name"]), k) for k in MISC]
    rows += [("Money/Misc/old health/" + os.path.basename(p), k) for p, k in rows if p.startswith("Health/2022/")]
    return rows


def messy():
    rows, taken = [], set()

    def put(folder, keys, generic=False):
        for i, k in enumerate(keys):
            stem = "%s %03d" % (("Scan", "Document")[i % 2], i + 4) if generic and i % 3 != 2 else POOL[k]["name"]
            rows.append((("%s/" % folder if folder else "") + stem + ".txt", k))
            taken.add(k)
    half_sorted = {"Bank": [k for k in CORE if k.startswith("stmt")][:5],
                   "Taxes": [k for k in CORE if k.startswith(("sa22", "sa23"))][:4],
                   "Health stuff": ["gp21_20210602", "hosp22_20220217", "gp23_20230119"],
                   "House": [k for k in CORE if k.startswith("lease")],
                   "Car": ["carsvc_20230408", "carsvc_20240408"]}
    for folder, keys in half_sorted.items():
        put(folder, keys)
    put("", ["stmt_20240430", "carins_20240311", "emp_20230401"])                       # strays at the root
    put("Stuff", ["pay_20230131", "pension_20220601", "ut22_20220915", "carins_20230313", "sa23_20240105",
                  "school_20230720"])
    put("New folder (2)", ["pay_20230228", "ut23_20230802", "flu22"])
    rest = [k for k in CORE + MISC if k not in taken]
    put("Downloads from phone", rest, generic=True)
    chain = "Old laptop backup/Users/morgan/Documents/"
    for folder, sub in (("Bank", "Bank"), ("Taxes", "Tax"), ("Health stuff", "Health"), ("House", "House"),
                        ("Car", "Car")):
        rows += [("%s%s/%s" % (chain, sub, os.path.basename(p)), k) for p, k in rows if p.startswith(folder + "/")]
    return rows


LAYOUTS = {"well_kept": well_kept, "half_messy": half_messy, "messy": messy}


def run_tool(tool, *args):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, tool)] + list(args), capture_output=True, text=True,
                       env=dict(os.environ, PRE_ONBOARDING_NOW=NOW), timeout=600)
    if r.returncode:
        raise RuntimeError("%s failed (%d): %s" % (tool, r.returncode, r.stderr[-500:]))
    return r.stdout


def card_for(key, entry_id, path):
    d = POOL[key]
    return {"id": entry_id, "doc_type": d["kind"], "party": d["party"], "parties": [d["issuer"]],
            "doc_date": d["date"], "title": "%s, %s, %s" % (d["kind"], d["issuer"], d["date"][:7]),
            "summary": "%s from %s, dated %s." % (d["kind"], d["issuer"], d["date"]),
            "key_facts": {"dates": [d["date"]], "amounts": [], "reference_numbers": [key.upper()]},
            "category": d["category"], "language": "en", "sensitive": False, "confidence": "high", "look": "",
            "proposed_name": "", "card_meta": {"model": "hand", "via": "hand", "shield_sha256": "none",
                                               "batch": "structure-tests", "path": path}}


def build(dest, names=tuple(LAYOUTS)):
    """Lay out, audit and card each named folder under `dest`; returns {name: folder path}."""
    out = {}
    for name in names:
        root = os.path.join(dest, name.replace("_", " ").title())
        rows = LAYOUTS[name]()
        assert len({p for p, _k in rows}) == len(rows), name
        for rel, key in rows:
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text(key))
        run_tool("audit.py", "--root", root, "--work", os.path.join(dest, "work-" + name))
        with open(os.path.join(root, "_Audit", "manifest.json"), encoding="utf-8") as f:
            entries = json.load(f)["entries"]
        by_path = {c["path"]: h for h, e in entries.items() for c in e.get("copies") or [{"path": e["current_path"]}]}
        os.makedirs(os.path.join(root, "_Audit", "cards"), exist_ok=True)
        made = {}
        for rel, key in rows:
            h = by_path[rel]
            made.setdefault(h, card_for(key, h, entries[h]["current_path"]))
        for h, card in made.items():
            with open(os.path.join(root, "_Audit", "cards", h + ".json"), "w", encoding="utf-8") as f:
                f.write(json.dumps(card, ensure_ascii=False, indent=1))
        out[name] = root
    return out
