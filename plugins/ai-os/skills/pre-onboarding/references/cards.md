# The card contract

A card is one document's catalogue entry: what it is, whose, of when, what it says that matters and why it is in
the folder. Every live document gets one, written by a bulk engine from the document's whole extracted text, and
the wiki is drafted from the cards. This page is the contract `tools/cards.py` holds, with `tools/refs.py`,
`tools/isolation.py` and `tools/engines.py` beside it: what a card holds, how the engine writes it, how its answer is
joined to the right document, and how it is checked against the isolation list. It says only what the code does;
the commands are in [the tool reference](tools.md#cardspy).

## Where a card lives

`<folder>/_Audit/cards/<id>.json` (or the directory `--out` names), UTF-8 JSON. `<id>` is the document's manifest
entry id, its content hash, so a card follows its document through renames and moves and serves every copy of it.
A document that has a card is not carded again unless its id is listed for `--redo`.

## What a card holds

The engine writes fourteen fields, as [`card-instructions.md`](../tools/templates/card-instructions.md) asks and the
output schema in `tools/schemas/` requires:

| Field | Type | What it holds |
| --- | --- | --- |
| `id` | text | copied from the input item; the tool then replaces it with the entry id |
| `doc_type` | text | a short English type in Title Case, such as Bank Statement or Tenancy Agreement; `Unknown` when unclear |
| `party` | text | the main person or organisation the document is about or addressed to, by the canonical name the rulebook gives; `Unknown` if none |
| `parties` | list of text | up to five other people or organisations involved |
| `doc_date` | text | the document's own date as `YYYY-MM-DD`, `YYYY-MM` or `YYYY`; empty when there is none, never invented |
| `title` | text | a descriptive title of at most 12 words |
| `summary` | text | two or three sentences, at most 70 words: what the document is, what matters in it, why it is in the folder |
| `key_facts` | object | `dates`, `amounts` and `reference_numbers`, each a list of labelled text; reference numbers as the identifier rule below says |
| `category` | text | exactly one of the rulebook's `card_categories` |
| `language` | text | `en`, `zh`, `fr`, `mixed`, `none`, or another two-letter code |
| `sensitive` | true or false | true for identity numbers, medical or immigration detail, police or legal matters, or credentials |
| `confidence` | text | `high`, `medium` or `low` (low when there was no text or it was garbled) |
| `look` | text | empty, or one sentence when a person should decide something: misfiled, credentials in plain text, blank or corrupt, a duplicate under another name |
| `proposed_name` | text | only for a generic file name: `<Party> - <Doc Type> <YYYY-MM-DD> <Detail>.<ext>`; otherwise empty |

The tool adds:

| Field | What it holds |
| --- | --- |
| `category_raw` | the engine's category, when it was not one of `card_categories`; the card's `category` is then `Other` |
| `card_meta` | `model` (the `--model` given, or `cli-default`), `via` (the engine), `batch` and `created_at`; `refs.py --apply` appends to its `fixes` |

A password or an activation code is never written on a card, under any identifier policy.

## What the engine is given

One prompt per call, in three parts:

1. **A no-tools preamble** (`engines.NO_TOOLS`): the session has no tools, and everything needed is in the
   message.
2. **The card instructions**, [`card-instructions.md`](../tools/templates/card-instructions.md) filled from the
   folder's `rulebook.json`: its `folder_description`; its `people`, each as the canonical name, every other name
   it appears under and who it is; its `card_categories`; and the identifier rule for its `identifiers` policy:
   `stated`, reference numbers written in full exactly as in the document; `last-four`, their last four
   characters only; `home-only`, in full only on the document's own home page and elsewhere the last four.
3. **The input items**, a JSON array, one per document:

| Key | What it holds |
| --- | --- |
| `id` | a short id the call issues: `d1`, `d2` and so on |
| `path` | the document's path in the folder, from its extract record |
| `class` | its manifest class |
| `page_count` | its page count |
| `read` | how its text was obtained: `text_layer`, `local_ocr`, `vision`, `mixed`, `sectioned` or `none` |
| `text` | every page's text, each after a `[page N]` marker; pages read only as a photo are left out |

`read` comes from the tiers of the record's pages, blank pages aside: `none` when nothing else was read (only
photo, unread or unrendered pages), the one tier when there is only one (a zip listing counts as `text_layer`),
`mixed` otherwise, and `sectioned` for a long document read in sections (below).

The engine is also given the card's output schema: every field required, and for `codex` a strict schema that
allows no other field (`schemas/card.json` and `schemas/card_codex.json`).

## How the bulk engine writes it

### Batches

`cards.py build` plans batches as files in `<work>/batches/<bucket>_<seq>.json`, each
`{"bucket", "mode", "items": [{"id", "chars"}]}`, from the extract records whose status is final (`ok`, `partial`,
`blank`, `photo`, `listed`, `no_reader` or `failed`). A record still `needs_vision` waits, and is counted as
waiting; a document already carded or already in a batch is left out, so `build` can be run again as extraction
finishes. Documents are bucketed by their text: under 20 characters (bucket 1), otherwise by pages, up to 20
(bucket 0), up to 100 (bucket 2) or more (bucket 3). Within a bucket, in id order:

| Mode | Which documents | Per call |
| --- | --- | --- |
| `group` | text up to `--small-chars` (default 60,000 characters) | up to `--batch-items` documents (default 30; `--textless-batch`, default 60, in bucket 1), and up to `--batch-chars` in all (default 180,000) |
| `single` | text over `--small-chars`, up to `--single-max` (default 600,000) | one document |
| `sections` | text over `--single-max` | one document, read in sections first |

### Calls

`cards.py work` takes every Nth batch file (`--worker k/N`), and for each the documents in it that have no card:

- **`group` and `single`** send the documents' full text in one call.
- **`sections`**, and a `single` whose estimated tokens exceed `--single-tokens` when that is set, read the
  document in sections first. Its pages are packed in order into sections of at most `--section-tokens` estimated
  tokens (or `--section-chars` characters when that is not set): a page goes whole into the section in progress when
  it fits there, and starts the next when it does not. A page over the budget by itself is split inside, because a
  text, Word, rtf or csv extraction is one page however long it is: at paragraph breaks, a paragraph still too long
  at line breaks, a line still too long at any character, so that every call fits (with `agy`, under its byte
  limit). Each section gets its own call asking for notes of at most 200 words, from the light engine
  (`--light-model` at low effort for `codex`, otherwise the same engine), cached in `<work>/sections/`, each file named
  by a hash of the section's own text, the budget, the model and effort that wrote the notes and the prompt, so a
  rerun does not pay for them again and a changed budget, model or prompt never reuses old notes. A cached file that
  is empty, or lacks its `[section k of n]` header, is a miss. To force a re-read, delete the document's files in
  `<work>/sections/` (they start with the first 16 characters of its id). A section budget under 1,000 (characters
  or estimated tokens) is refused. A section that fails three times, returns no notes, or is over `agy`'s byte limit
  (four-byte characters can still be, at 60,000 characters) is not read, and then **no card is written**: a card
  made from notes with a hole in them would claim a read it lacks. `<work>/state/card_err_<id>.txt` names each
  section not read (and is removed once the document's card is written), and the sections that were read stay
  cached, so a rerun reads only the rest. When every section
  is read, the card is written from the notes and the document's first 20,000 characters, with `read` set to
  `sectioned`.
- **A token estimate** is ASCII characters divided by 3.8, plus other characters times 1.1, rounded up, so that a
  short line is never free and a section's estimate is never below what its pieces add to.
- **A quota message** stops the batch: the cards it has joined are written, and the worker sleeps for the reset
  time the message gives (10 minutes for `agy` and 30 for `codex` when it gives none), plus 90 seconds, and at
  most five hours, then goes on with what is left.
- **`--redo <file>`** re-cards the ids listed in the file, one per call, even though their cards exist, each sent as
  a first run would send it (its size decides: a long document is read in sections, reusing the cached notes, so
  only a section that failed is read again); an id is
  added to `<work>/state/redo_done_<k>.txt`, the ones done so far, only once its card is written.

Each call goes through [`engines.py`](tools.md#enginespy): a fresh empty working directory, the prompt on standard
input, tools refused, typed outcomes.

## The whole-chunk join

The rule is the framework's ([the determinism boundary](../../../ARCHITECTURE.md#the-determinism-boundary)): answers
are matched by an identifier the engine was given, the returned set must equal the requested set, and a chunk that
fails is retried halved, never applied in part. `cards.py` holds it so:

1. Each document sent is given a short id the call issues, `d1` to `dN`, never its path or its name.
2. The reply's first JSON object or array is read (a code fence or prose around it is tolerated); its `items`, or
   the array itself, must be a list.
3. **Ids.** The ids returned must be exactly the ids sent, in the order sent. This catches a missing, extra,
   repeated or unknown id, and two ids swapped while their cards stay in place; a correct reply in another order is
   refused too (the instructions ask for the order sent), at the cost of a retry.
4. **Schema.** Every card must meet the card schema (`schemas/card.json`): every field present and of its type. A
   category outside `card_categories` then becomes `Other`, with the engine's in `category_raw`.
5. **Sibling identifiers.** In a chunk of two or more documents, no card may carry an identifier that another
   document's source (its path and text) holds and its own does not. An identifier is a run of five or more digits
   once the spaces, hyphens and slashes inside it are removed, that is not an amount (a decimal point or a
   thousands comma) and not shaped like a year or a date; a part of five or more digits inside a longer run counts
   on its own too. Identifiers are compared as digit strings, `key_facts` count through the identifiers in them, and
   `look`, which is asked to name other files, is not checked. This catches two cards whose contents were crossed
   while their ids and order stayed right, when either carries such a number (an account, invoice, policy or
   passport number); it cannot catch a crossing told apart only by names, addresses, dates, amounts or short
   numbers, and a chunk of one document has no siblings to check against.
6. Only then does each card take its document's entry id, and the chunk's cards are kept together.
7. Any other failure (a reply with no list, an engine error, an empty answer, a tool use) retries the whole chunk,
   three attempts in all; a crossing (step 5) would cross again, so it is halved at once. A halved chunk's halves go
   through the same, halving again at most six times, down to one document. Every document of a chunk that still
   fails is left without a card, its last error in `<work>/state/card_err_<id>.txt`. No part of a failed chunk is
   ever written. A quota message, a credential file or a setup problem is not a failure of the chunk: the first
   waits, the others stop the run.

## Checked against the isolation list

### The terms file

The operator supplies it at run time (`--terms <file>`): never committed, never inside the folder, never shown to a
model. It lists every name that must not reach a model working on the folder, the operator's own identifiers from
other use of the engines included ([the skill](../SKILL.md#before-you-start)). One term per line, optionally
followed by markers, `Term|marker|marker`: shorter forms whose presence in a
document's own text shows the term is genuine content of that document. Blank lines and lines starting with `#`
are ignored. A missing or empty file is refused. `cards.py work` needs `--terms`, or `--no-isolation-terms` to
state, in its log, that there is genuinely nothing to list; the skill's step 5 says what that leaves unverified.

### Before any call

`isolation.py scan` checks every file a model will be shown for the terms, and `isolation.py canary` asks each
engine to list every name in its context ([the tool reference](tools.md#isolationpy)). `cards.py` does not read the
canary's result (only `readiness.py` does, at hand-off); running it first is the operator's step.

### Every card, before it is written

The contamination guard. A term the card names (anywhere in its JSON, ignoring case) is contamination unless the
card's own source, the full text of its extract record, carries the term or one of its markers (ignoring case; a
marker made only of letters, digits, spaces, `.`, `&` and `-` must stand as a whole word, any other may appear
anywhere). Every card of a batch is checked before any is written: the first contaminated card writes
`<work>/state/ALERT`, naming the card and how many terms, no card of that batch is written, and its worker stops
(exit 2); every `cards.py work` worker and the vision lane then stop at their next batch while the file is there
(exit 3). Cards written by earlier batches stay; find where the term came from before removing the file.

### At hand-off

`readiness.py --terms <file>` runs the same guard over the card of every live document `extract.py` reads (its
`card_meta` aside) and reports how many are contaminated, a count above zero being one finding; without `--terms`
it reports the check as not verified ([`records`](tools.md#readinesspy)).

## Repair from the card's own source

`refs.py` restores reference numbers an engine cut short, from the card's own document, with no model call. It
runs only under the identifier policy `stated`, and refuses under any other.

- **What it looks for.** A tail of two to four letters or digits (at least one a digit) after `…` anywhere in the
  card, and, in `key_facts.reference_numbers`, also after `...`, `**`, `xxx`, or the words *ending*, *ends in* or
  *last 4*.
- **What it never restores.** A tail the card's own source also shows masked (after mask characters such as `*`,
  `xx`, `•`, `·` or `…`, with or without separators: `****1234`, `xxxx-xxxx-1234`), whatever full numbers the source
  also holds: a tail cannot show whether the engine truncated the number or the source masks it, and a masked
  source value stays an unresolved suffix
  ([identifiers](../../wiki-maintenance/SKILL.md#identifiers-series-and-derived-views)).
- **What it restores.** Otherwise, the number in the document's extracted text that ends with that tail and is
  longer than it, compared on letters and digits alone, when exactly one distinct number does. A tail masked in
  the source, ambiguous or not found is left as it is, and the card is listed for re-carding.
- **What it reports.** Counts: cards with a truncation, forms restored, forms masked in the source, forms ambiguous,
  forms not found, cards fully restored, cards to re-card. With `--apply` it writes the restored cards (adding
  `refs_restored_from_source <time>` to `card_meta.fixes`) and the ids to re-card, one per line, to
  `<work>/state/redo_refs.txt`, which is the file `cards.py work --redo` takes.

## Who reads a card

- `wiki.py profile`: `category`, `doc_date`, `party` and `parties`, aliases folded to the rulebook's canonical
  names.
- `wiki.py bundles`: `title`, `doc_type`, `party`, `parties`, `doc_date`, `category`, `language` and `sensitive`
  for every routed document, and `summary` and `key_facts` unless the document is listed compact.
- `wiki.py review-prompts`: the dates, amounts and reference numbers in `key_facts`, for the sample of facts the
  professional's review checks against the sources.
- `readiness.py`: that each live document has a card, that its category is allowed, and the contamination guard.
