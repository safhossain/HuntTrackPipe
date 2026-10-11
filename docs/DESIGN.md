# HuntTrackPipe - Design Spec (v1)

Status: for review, nothing implemented yet. Decisions below reflect the Q&A rounds of 2026-10-11.

## 1. Goal and scope

HuntTrackPipe is a local, single-user job-application pipeline. Per application it:

1. Takes a pasted job posting.
2. Asks Jev (TypeSafe) typed pre-LLM questions about the posting.
3. Builds a JSON schema from Jev's answers and has Claude Haiku 5.5 extract the fields.
4. Lets the user review/edit, then creates the application folder and writes one row to `job_application_tracker.xlsx`.
5. Manages application files (rename, convert, combine into one PDF).
6. Answers application text-field questions from a user-maintained candidate context file.

Non-goals (v1): no database, no code bridge to Resumate, no browser automation of job portals, no multi-user.

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Pydantic | Same stack as Resumate; all needed libs are Python |
| Frontend | Vue 3 + Vite + Pinia + Tailwind | Same as Resumate; drag-reorder and PDF previews are easy in a browser |
| Excel | `openpyxl` | Preserves the table, dropdowns and formula; file is never open elsewhere while the engine runs |
| Jev | `typesafe-sdk` (official), `https://api.typesafe.ai/v1/systemone`, model pinned `jev-1.13.0` | Pin a version; log the `model` field of every response |
| LLM | `anthropic` SDK, model `claude-haiku-5-5` | User choice. Structured outputs via `output_config.format` |
| PDF | `pypdf` (merge), `PyMuPDF` (thumbnails, pdf->png/jpg), `img2pdf` (png/jpg->pdf), `pdf2docx` (pdf->docx), LibreOffice `soffice --headless` (docx->pdf) | LibreOffice already installed for Resumate |

Run: `npm run dev` at repo root -> uvicorn on `:8010` + Vite on `:5180` (`strictPort: true`, `/api` proxied to `127.0.0.1:8010`). Ports differ from Resumate (`:8000` / `:5173`) so both apps can run at the same time. Keys live in `.env` (`TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY`); both SDKs read them by default.

## 3. Repo layout

```
HuntTrackPipe/
  backend/
    main.py                 # FastAPI app + routers
    config.py               # loads htp.config.json + .env; Settings model
    naming.py               # sanitize(), folder_name(), final_file_name()
    jev/
      client.py             # one call: state + questions -> answers (retry/backoff)
      questions.py          # the fixed question set + Excel value mapping
      derive.py             # answers -> {schema_fields, direct_values, upload hints}
    llm/
      client.py             # Claude Messages call with output_config.format
      schema_builder.py     # Jev-derived field list -> strict JSON schema
      prompts.py            # extraction + QA system prompts
    excel/
      tracker.py            # open/locate table, find/append row, write, formula, hyperlink, backup, lock check
    sessions/
      models.py             # Pydantic models for session.json
      store.py              # create/load/save session.json per application folder
    files/
      convert.py            # docx<->pdf, pdf<->png/jpg
      combine.py            # ordered inputs -> single PDF
      thumbnails.py         # PyMuPDF page images for the UI
    qa/
      answer.py             # pending questions -> one Claude call -> answers.md
    api/routers/
      sessions.py, extract.py, excel.py, files.py, qa.py, settings.py
  frontend/                 # Vue app
  docs/DESIGN.md
  htp.config.json           # non-secret settings (see section 13)
  JobHunting/
    candidate_context.txt   # user-maintained; add to .gitignore
    Applications/           # git-ignored data: tracker + per-application folders
```

## 4. Per-application folder and session file

```
Applications/
  job_application_tracker.xlsx
  .htp_backup/                                  # last 10 tracker copies
  1234567890_Google_Software-Engineer_2026-10-11/
    session.json                                # engine state for this application
    posting.txt                                 # raw pasted posting
    0_resume.pdf                                # inputs: {count}_<original-name>.<ext>
    1_transcript.pdf
    Safwan-Hossain_Resume_1234567890.pdf        # final separate file(s): {Name}_{DocType}_{X}
    Safwan-Hossain_1234567890.pdf               # combined file (if any): {Name}_{X}
    answers.md                                  # rendered Q&A
```

`session.json` (schema_version 1):

```json
{
  "schema_version": 1,
  "session_id": "uuid4",
  "created_at": "2026-10-11T08:30:00Z",
  "folder": "1234567890_Google_Software-Engineer_2026-10-11",
  "posting": { "text": "...", "url": null },
  "jev": { "model": "jev-1.13.0", "at": "...", "answers": { "...raw response answers..." },
           "derived": { "schema_fields": ["requisition_id", "..."],
                        "direct_values": { "Work_Mode": "Hybrid" },
                        "low_confidence_choices": ["Employment_Type"],
                        "upload_mode": "separate_uploads",
                        "required_docs": ["CoverLetter"] } },
  "llm": { "model": "claude-haiku-5-5", "at": "...", "schema": {}, "output": {}, "usage": {} },
  "review": { "values": { "Requisition_ID": "1234567890", "...": "..." },
              "written_at": null, "pending_write": null },
  "upload_mode": "separate_uploads", "upload_mode_source": "jev",
  "files": { "inputs": [ { "index": 0, "file": "0_resume.pdf", "doc_type": "Resume", "original": "resume_google.pdf" } ],
             "finals": [ { "file": "Safwan-Hossain_Resume_1234567890.pdf", "doc_type": "Resume", "from": 0 } ],
             "combined": null },
  "qa": { "questions": [ { "id": "q1", "text": "Why do you want to work here?",
                           "limit": { "unit": "chars", "value": 500 },
                           "status": "answered", "answer": "...", "feedback": null,
                           "answered_at": "...", "model": "claude-haiku-5-5" } ] }
}
```

Source-of-truth rule: Excel owns every tracker column. `review.values` is what the engine last wrote; on session open the engine re-reads the row (matched via the `Folder` column) and shows Excel's values. Everything that is not a tracker column (posting text, Jev/LLM raw output, file manifest, Q&A) lives only in `session.json`.

## 5. Pipeline per new application

```
paste posting (+ optional URL)
  -> Jev call (one request, all questions)
  -> derive: schema fields, direct values, upload hints
  -> schema builder -> Claude extraction call
  -> review screen: extracted values (editable) + manual fields
  -> Create: folder name -> mkdir + posting.txt + session.json -> Excel row written
```

Guard: if `is_job_posting` noul < 0.5 the UI warns before continuing (still allowed).
Posting text over ~30k tokens (chars / 3.5 estimate) is truncated for Jev with a warning; Jev's cap is 32k for state + longest question.

## 6. Jev request

`state` is sent as an object: `{ "posting": "<text>" }` (docs prefer named fields over a bare blob). Question keys are internal; they are mapped to Excel columns/values in `questions.py`.

Existence nouls (gate LLM schema fields). Each carries `criteria.true` / `criteria.false` to avoid literal misreads:

| key | instructions | true | false |
|---|---|---|---|
| `has_requisition_id` | The posting states an explicit requisition / job / reference ID. | e.g. "Req ID 12345", "R-98765", "JR0012", "Job ID: 4567" | No such ID; salaries, years of experience or phone numbers do not count |
| `has_organization` | The hiring organization's name can be identified. | Company named anywhere, e.g. "About Shopify", "X is hiring" | Anonymous / agency hides client / no name |
| `has_position_title` | A job title for this role is stated. | A title such as "Software Engineer II" | Only a department or vague description |
| `has_compensation` | Pay is stated in numbers. | Salary, hourly rate, range or stipend with numbers | Only "competitive" or nothing |
| `has_deadline` | An application closing date is stated. | "Apply by", "closes on", a date | "Open until filled" or nothing |
| `has_recruiter_name` | A named contact person (recruiter / hiring manager) appears. | A person's name given as contact | No person named |
| `has_recruiter_contact` | Contact details for a person appear. | Email, phone or LinkedIn of a contact | Only a generic careers address or nothing |
| `has_role_categories` | Role categories (backend, frontend, devops, data, ...) can be inferred. | Tech stack / responsibilities make the area clear | Too generic to tell |
| `has_position_level` | Seniority level is stated or clearly inferable. | "Junior", "Senior", "Intern", "3+ years" | Nothing about level |

Choices (direct-to-Excel candidates):

- `work_mode`: `in_person`, `hybrid`, `remote`, `travel`, `tbd`, `unknown`. `tbd` = posting says it is to be determined / discussed; `unknown` = not mentioned.
- `employment_type`: `full_time`, `part_time`, `contract`, `contract_full_time`, `contract_part_time`, `internship`, `co_op`, `temporary`, `freelance`, `unknown`.
- `upload_mode`: `single_document` (resume only), `separate_uploads` (several documents, separate fields), `single_combined_file` (several documents merged into one file), `not_stated`.

Document nouls (pre-fill the Files tab): `requires_cover_letter`, `requires_transcript`, `requires_portfolio`, `requires_references`.

Gate noul: `is_job_posting`.

Thresholds (config, defaults): `noul_include_threshold = 0.35` (a field with noul >= 0.35 goes into the LLM schema; bias toward inclusion since an extra field just returns `null`), `choice_direct_confidence = 0.7` (choice written straight to Excel at or above this; below it the column is added to the LLM schema as an enum), document nouls >= 0.5 pre-tick a document type.

Not sent to Jev or the LLM (manual): `Applied_Date`, `Posting_URL`, `Application_Status`, `Outcome`, `Applied_Through`, `Confirmation_#`, `Days_Since_Applied` (formula), `Folder` (engine).

## 7. LLM extraction (Claude Haiku 5.5)

Request: Messages API, `model: claude-haiku-5-5`, `max_tokens: 2048`, `output_config: { format: { type: "json_schema", schema }, effort: "low" }`. No `temperature` / `top_p` / `top_k` (400 on this model). One retry on transport error or schema-validation failure. Usage is stored in `session.json`.

Schema builder: starts from the ordered candidate list below, keeps only fields whose Jev gate passed (plus low-confidence choice columns), marks every property required and nullable, `additionalProperties: false`.

| property | type | notes |
|---|---|---|
| `requisition_id` | string / null | verbatim |
| `organization` | string / null | hiring company, not the job board |
| `position_title` | string / null | verbatim title |
| `compensation` | string / null | verbatim incl. currency and period, e.g. "CAD 80,000-95,000 / year" |
| `deadline` | string / null | `YYYY-MM-DD` if a date is given; else a short phrase like "Open until filled" |
| `recruiter_name` | string / null | |
| `recruiter_contact` | string / null | email / phone / URL |
| `role_categories` | array of string | 1-3 short labels; **cap enforced in prompt and truncated to 3 in code** (Claude structured outputs reject `maxItems`) |
| `position_level` | string / null | free text, one value (Intern, Junior, Senior, ...) |
| `work_mode` | enum (Excel values) / null | only when Jev confidence < 0.7 |
| `employment_type` | enum (Excel values) / null | only when Jev confidence < 0.7 |

System prompt rules: extract only what the text supports; `null` when absent; never invent compensation or deadlines; at most 3 role categories, one position level; plain ASCII punctuation. Post-processing: trim strings, parse `deadline` to a date when it matches ISO, join `role_categories` with `, ` for Excel.

Cost note: ~3k input + ~300 output tokens per posting is well under a cent. The engine warns if any request exceeds ~80k tokens (Haiku's price rises 5x above 100k).

## 8. Naming rules

`sanitize(s)`: Unicode NFKC, trim, spaces -> `-`, drop `<>:"/\|?*` and control chars, collapse repeated `-`, strip trailing `.`/`-`, cap at 60 chars per component. Full path is kept under 200 chars by trimming the title component first.

Folder: `{Requisition_ID}_{Organization}_{Position_Title}_{Date_Created}` (date is the session creation date, `YYYY-MM-DD`; the folder is never renamed). Missing components become `null`. If all three leading components are missing: `null_null_null_{Date_Created}_{unix_ts}`. Any other collision gets `_2`, `_3`, ...

`{X}` for final files, first available: Requisition_ID; `{Organization}_{Position_Title}`; Organization; Position_Title; Date_Created.

Files:
- Inputs: `{count}_<original-name>.<ext>`, count from 0 in display order; renumbered on reorder.
- Separate finals: `{Candidate_Name}_{DocType}_{X}.<ext>`, DocType in `Resume | CoverLetter | Transcript | Portfolio | References | Other`.
- Combined: `{Candidate_Name}_{X}.pdf`.
- `Candidate_Name` from config, spaces -> `-` (e.g. `Safwan-Hossain`).

## 9. Excel writer (`excel/tracker.py`)

- Opens the workbook with `openpyxl`, finds table `Applications`, maps columns **by header name** (tolerates reordering).
- Row lookup: match `Folder` column to the session folder; else first empty data row inside the table (row 2 at the start); else append and extend `table.ref`.
- Writes: strings as-is; `Applied_Date` / parsed `Deadline` as real dates with `yyyy-mm-dd` format; `Days_Since_Applied` formula `=IF(Applications[[#This Row],[Applied_Date]]="","",TODAY()-Applications[[#This Row],[Applied_Date]])`; `Folder` as a relative hyperlink to the subfolder with the folder name as text.
- New-row defaults: `Application_Status = Not Applied`, `Outcome = Pending`.
- Fill-only-empty: a non-empty cell whose value differs is skipped and reported. "Re-extract" shows a per-cell diff and writes only approved cells.
- Save: write to a temp file in the same directory, then `os.replace`. Before every save, copy the current file to `.htp_backup/` (keep last 10).
- Lock: before saving, open the file for `r+b`; on `PermissionError` return HTTP 423, keep the payload in `session.pending_write`, UI shows "Close Excel and retry". Also refuses to run while `~$job_application_tracker.xlsx` exists.
- Read-back: opening a session reads the row and shows Excel's current values (Excel wins).

## 10. Files, conversions, CombinationEngine

Conversions (also exposed as a standalone tool in the UI):
- docx -> pdf: `soffice --headless --convert-to pdf --outdir <tmp>`.
- pdf -> docx: `pdf2docx` (lossy; UI says so).
- pdf -> png/jpg: PyMuPDF, one image per page `{stem}_p{n}.png` at configurable DPI (default 150).
- png/jpg -> pdf: `img2pdf`.

Combine (output is always PDF): every input is converted to PDF into `.converted/` inside the folder if needed, merged with `pypdf` in display order, saved as `{Candidate_Name}_{X}.pdf`. Inputs stay in place. The Files tab shows first-page thumbnails (PyMuPDF), drag-reorder, doc-type dropdown per file, "Make final" (copy + rename per section 8) and "Combine".

Upload mode (from Jev, user can override): `single_document` / `separate_uploads` -> "Make final" per file; `single_combined_file` -> Combine button highlighted.

## 11. Application questions (Q&A)

Inputs per call: `candidate_context.txt` (read fresh every time; path in config), `posting.txt`, organization + title, previously answered questions (read-only, for consistency), pending questions each with optional `{unit: chars|words, value}` limit.

One Claude call (`qa_model`, default `claude-haiku-5-5`, configurable) with structured output `{ answers: [{ id, answer }] }`. System prompt: write in first person as the candidate; use only facts in the context; respect each limit; no em/en dashes; plain text. Engine verifies limits in code and re-asks once for the offending answers.

Operations: add / edit / delete question (any time, before or after extraction), Answer pending, Regenerate one (with optional feedback text), Copy answer. `answers.md` is regenerated after every change. Token guard as in section 7.

## 12. UI screens

1. **Dashboard** - list of application folders with status/outcome read from Excel; "New application".
2. **New application** - paste posting + URL -> Run -> three panels: Jev results (chips with probability/confidence), extracted fields (editable form), manual fields (Applied_Date, Posting_URL, Application_Status, Applied_Through, Confirmation_#). "Create" makes the folder and writes the row.
3. **Session** - tabs: Overview (Excel read-back, edit manual fields, write), Files (section 10), Questions (section 11), Log (raw Jev/LLM payloads, usage, timings).
4. **Settings** - edits `htp.config.json`; shows key presence (never the keys).

## 13. Config (`htp.config.json`)

```json
{
  "applications_dir": "JobHunting/Applications",
  "tracker_path": "JobHunting/Applications/job_application_tracker.xlsx",
  "candidate_name": "Safwan Hossain",
  "candidate_context_path": "JobHunting/candidate_context.txt",
  "jev": { "model": "jev-1.13.0", "noul_include_threshold": 0.35, "choice_direct_confidence": 0.7, "doc_noul_threshold": 0.5 },
  "llm": { "extract_model": "claude-haiku-5-5", "qa_model": "claude-haiku-5-5", "effort": "low", "max_tokens": 2048, "token_warn": 80000 },
  "files": { "image_dpi": 150, "soffice_path": null },
  "backups_keep": 10
}
```

## 14. API (FastAPI, prefix `/api`)

| Method + path | Purpose |
|---|---|
| `GET /health` | cold-start poll |
| `GET /sessions` / `GET /sessions/{id}` | list / load (includes Excel read-back) |
| `POST /extract/jev` | posting -> Jev answers + derived |
| `POST /extract/llm` | derived + posting -> extracted values |
| `POST /sessions` | create folder + session.json + Excel row |
| `PUT /sessions/{id}/row` | write manual/edited fields (fill-only-empty; `?force=diff` for re-extract) |
| `POST /sessions/{id}/files` / `PUT .../order` / `PUT .../{idx}` | upload, reorder, set doc type |
| `POST /sessions/{id}/files/final` / `POST .../combine` / `POST /files/convert` | naming + combination + conversions |
| `GET /sessions/{id}/files/{idx}/thumb` | thumbnail |
| `POST/PUT/DELETE /sessions/{id}/qa/questions` ; `POST /sessions/{id}/qa/answer` ; `POST .../regenerate/{qid}` | Q&A |
| `GET/PUT /settings` | config |

LLM/Jev failures return HTTP 502 with the provider message (as in Resumate); Excel lock returns 423.

## 15. Edge cases

- Posting pasted twice: warn when `posting.txt` hash matches an existing session.
- Jev 429/529: SDK backoff; surface after 3 attempts.
- LLM returns a value for a field Jev gated out: impossible by construction (field not in schema).
- Role categories > 3 or empty: truncate / `null`.
- Deadline not ISO: stored as text; `Days_Since_Applied` unaffected.
- Folder exists but no `session.json` (manual folder): listed as "unmanaged", can be adopted.
- Tracker headers changed: writer fails fast with the missing header name.

## 16. Implementation order

1. **Core, no UI**: config, naming, session store, Jev client + questions, schema builder, Claude client, Excel writer; a small CLI (`python -m backend.run --posting file.txt`) to validate end to end.
2. **Webapp**: Dashboard, New application, Session Overview.
3. **Files**: conversions, combine, thumbnails, reorder UI.
4. **Q&A**.
5. **Hardening**: backups, lock flow, re-extract diff, duplicate detection, logs.
