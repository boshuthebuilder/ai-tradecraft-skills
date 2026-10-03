# Render probe

One chart of each kind `wiki.py chart` renders, each followed by its data table, and one callout, its marker alone on its line. Open
this page in each Markdown app the wiki will be read in. For every section, note whether the chart draws, whether
its labels, values and dates read as in the table under it, and anything clipped or misplaced. A kind that does not
draw in every app is taken out of the tool. The page is generated: `tests/test_charts.py --update` rewrites it from
the golden inputs in `tests/golden/charts/`, and a test fails when it differs from the tool's output.

> [!note]
> **Callout.** A box in Obsidian and in Typora. The marker stands alone on its line: Typora prints it as text when
> anything follows it there.

## bar

```mermaid
xychart-beta
    title "Current account, March 2024 (GBP)"
    x-axis ["Opening balance", "Salary in", "Rent out", "Closing balance"]
    y-axis "GBP" 0 --> 4160.00
    bar [2410.00, 3200.00, 1450.00, 4160.00]
```

| Label | Value (GBP) | Source |
| --- | ---: | --- |
| Opening balance | 2410.00 | `02 Finance/Bank statement 2024-03.pdf` |
| Salary in | 3200.00 | `02 Finance/Bank statement 2024-03.pdf` |
| Rent out | 1450.00 | `02 Finance/Bank statement 2024-03.pdf` |
| Closing balance | 4160.00 | `02 Finance/Bank statement 2024-03.pdf` |

## line

```mermaid
xychart-beta
    title "Synthetic line series (tool input, not fixture data)"
    x-axis ["2024-01", "2024-02", "2024-03", "2024-04"]
    y-axis "units" 0 --> 8
    line [3, 7.5, 5, 8]
```

| Period | Value (units) | Source |
| --- | ---: | --- |
| 2024-01 | 3 | `02 Finance/Bank statement 2024-03.pdf` |
| 2024-02 | 7.5 | `02 Finance/Bank statement 2024-03.pdf` |
| 2024-03 | 5 | `02 Finance/Bank statement 2024-03.pdf` |
| 2024-04 | 8 | `02 Finance/Bank statement 2024-03.pdf` |

## pie

```mermaid
pie title Planned monthly spending (GBP)
    "Rent" : 1450
    "Utilities" : 150
    "Savings" : 400
```

| Label | Value (GBP) | Source |
| --- | ---: | --- |
| Rent | 1450 | `02 Finance/Tax/Budget final.xlsx` |
| Utilities | 150 | `02 Finance/Tax/Budget final.xlsx` |
| Savings | 400 | `02 Finance/Tax/Budget final.xlsx` |

## gantt

```mermaid
gantt
    title Passport validity
    dateFormat YYYY-MM-DD
    section Passport
    P1234567 :2021-07-15, 2031-07-15
```

| Section | Label | Start | End | Source |
| --- | --- | --- | --- | --- |
| Passport | P1234567 | 2021-07-15 | 2031-07-15 | `01 Identity/Passport scan.pdf` |

## timeline

```mermaid
timeline
    title Home
    2024-05-01 : Lease renewed to 2025-04-30
    2024-03-15 : Electricity bill GBP 96.40
```

| Date | Label | Source |
| --- | --- | --- |
| 2024-05-01 | Lease renewed to 2025-04-30 | `03 Home/Lease renewal.pdf` |
| 2024-03-15 | Electricity bill GBP 96.40 | `03 Home/Utilities /Electricity bill.pdf` |
