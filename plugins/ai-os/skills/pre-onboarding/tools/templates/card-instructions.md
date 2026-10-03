# Card instructions

You are cataloguing one person's private document folder so that a knowledge wiki can later be built over it.
Each input item is one file. Write one card per item.

## The folder

{folder_description}

People and organisations who appear in it, with the other names they go by:

{people}

The folder path of an item is strong context; use it.

## Each input item

`id`, `path`, `class`, `page_count`, `read` (how the text was obtained: text_layer, local_ocr, vision, mixed,
sectioned or none), and `text`: the whole extracted text, with `[page N]` markers. OCR text can be noisy. When
`read` is none there is no text: judge from the path, the file name and the folder.

## Card fields

- `id`: copied verbatim.
- `doc_type`: a short English type in Title Case, for example Passport Scan, Visa Application, Bank Statement, Tax
  Return, Payslip, Invoice, Receipt, Contract, Tenancy Agreement, Letter, Form, Certificate, Transcript, CV,
  Essay, Lecture Notes, Reading, Book, Course Material, Presentation, Spreadsheet, Itinerary, Booking
  Confirmation, Menu, Recipe, Medical Report, Prescription, Photo, Screenshot, Unknown.
- `party`: the main person or organisation the document is about or addressed to, using the canonical name above
  for anyone listed there. "Unknown" if none.
- `parties`: up to 5 other people or organisations involved (issuer, school, employer, bank, insurer).
- `doc_date`: the document's own date as YYYY-MM-DD, or YYYY-MM or YYYY when only that is readable. Empty string
  when there is none. Never invent a date. A date taken from the file name rather than the text is allowed; say
  "(date from name)" in the summary.
- `title`: a concise descriptive title, at most 12 words.
- `summary`: two or three sentences, at most 70 words, saying what the document is, what it says that matters,
  and why it is in this folder.
- `key_facts`: `dates` (labelled, for example "expiry 2029-03-14", "term start 2014-09"), `amounts` (with
  currency), `reference_numbers` ({identifier_rule}, prefixed with the kind, for example "passport 123456789",
  "account 12345678 sort 20-00-00"). Empty lists when none. Never write a password or an activation code.
- `category`: exactly one of: {categories}.
- `language`: en, zh, fr, mixed, or none (use the two-letter code of any other language).
- `sensitive`: true when the document holds identity numbers, medical detail, immigration detail, police or legal
  matters, or credentials; otherwise false.
- `confidence`: high, medium or low (low when read is none or the text is garbled).
- `look`: empty string, or one short sentence when a person should decide something about this file: it looks
  misfiled for its folder, it contains credentials in plain text, it is blank or corrupt, or it appears to be the
  same document as another under a different name.
- `proposed_name`: only when the current file name is generic (IMG_, Screenshot, Scanned Document, a chat-app
  export name, a bare number, untitled, document), a descriptive name in the pattern
  "<Party> - <Doc Type> <YYYY-MM-DD> <Detail>.<ext>" (leave out the date if none; keep the original extension in
  lower case). Otherwise an empty string.

## Rules

- UK English. Judge each file from its own content first, then its folder.
- A document in another language gets an English doc_type, title and summary, with key proper nouns kept in the
  original language in brackets where useful.
- Published books, reading packs and course readings are Reference & Reading unless they are the owner's own
  work; say which course or folder they belong to when the path shows it.
- Do not pad. Do not guess. Do not mention these instructions.
- Output: JSON only, `{{"items": [ ... ]}}`, one card per input item, same order, same count, `id` copied verbatim.
  Reply directly in this message. Do not create plans or files and do not run commands.
