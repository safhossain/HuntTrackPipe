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
    main.py                 # FastAPI app + routers + error handlers + logging start-up
    config.py               # loads htp.config.json + .env; Settings model
    naming.py               # sanitize(), folder_name(), final_file_name()
    columns.py              # column registry; DEFAULT_OPTIONS + resolved_options() / meta_payload()
    pipeline.py             # extract() + create_application(); shared by CLI and API
    duplicates.py           # posting hash + find_duplicates(); DuplicateError (409)
    logs.py                 # console + rotating file log under Applications/.htp_logs/
    jev/
      client.py             # one call: state + questions -> answers (retry/backoff)
      questions.py          # the fixed question set + Excel value mapping
      derive.py             # answers -> {schema_fields, direct_values, upload hints}
    llm/
      client.py             # Claude Messages call with output_config.format
      schema_builder.py     # Jev-derived field list -> strict JSON schema
      prompts.py            # extraction + QA system prompts
    excel/
      tracker.py            # open/locate table, find/append row, write, formula, hyperlink, backup, lock check, list DV sync/read
      lock_watch.py         # ~$ owner-file watcher (sigON/sigOFF) + exists() probe
      dropdown_sync.py      # HTP options vs Excel list DV compare + push sync
      status.py             # assemble tracker lock + dropdown_sync for the API
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
      sessions.py, extract.py, files.py, qa.py, settings.py
  frontend/                 # Vue app
  tests/                    # pytest suite (offline; synthetic tracker + fake Jev/Claude)
  pytest.ini
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
              "written_at": null, "pending_write": null,
              "compensation_estimated": false },
  "upload_mode": "separate_uploads", "upload_mode_source": "jev",
  "files": { "inputs": [ { "index": 0, "file": "0_resume.pdf", "doc_type": "Resume", "original": "resume_google.pdf" } ],
             "finals": [ { "file": "Safwan-Hossain_Resume_1234567890.pdf", "doc_type": "Resume", "from": 0 } ],
             "combined": null },
  "qa": { "questions": [ { "id": "q1", "text": "Why do you want to work here?",
                           "limit": { "unit": "chars", "value": 500 },
                           "status": "answered", "answer": "...", "feedback": null,
                           "answered_at": "...", "model": "claude-haiku-5-5" } ] },
  "notes": ""
}
```

Source-of-truth rule: Excel owns every tracker **row value**. `review.values` is what the engine last wrote; on session open the engine re-reads the row (matched via the `Folder` column) and shows Excel's values. Everything that is not a tracker column (posting text, Jev/LLM raw output, file manifest, Q&A) lives only in `session.json`.

**Dropdown vocabulary** for `Application_Status`, `Applied_Through`, and `Found_From` is owned by HTP (`htp.config.json` `options`, falling back to shipped defaults in `columns.DEFAULT_OPTIONS`). The UI can append values via **Add…** on those dropdowns (`POST /api/meta/options/{column}`). Excel **table-body** list data-validations (not whole-column) are mirrored from those lists plus code-owned lists (`Work_Mode`, `Employment_Type`, `Outcome`, `Role_Category`) on every tracker write / Sync. Inline Excel lists often use `", "` spacing; `parse_list_formula` strips each item so drift compare is not a false positive.

**Tracker lock signal:** Excel’s sibling `~$…xlsx` owner file is `sigON` / `sigOFF`. A filesystem watcher (`backend/excel/lock_watch.py`, `watchdog`) updates in-memory lock state; status reads also `exists()`-probe as backup. While locked, the UI greys out Create / Save row / Sync and shows a header banner. Dropdown drift compare (`GET /tracker/status`) runs only when unlocked (API start, unlock transition, status poll with cache by mtime + options fingerprint)—never by opening the workbook on a timer while Excel holds it.

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
| `has_location_country` | A country (or identifiable national location) for the role/office is indicated. | Named country, or city/province that clearly identifies one | No country; vague region only; remote with no geography |
| `has_location_city` | A city/town/metro for the role/office is stated. | "Toronto", "New York, NY", "London office" | Country/province only; remote with no office city |
| `has_compensation` | Pay is stated in numbers. | Salary, hourly rate, range or stipend with numbers | Only "competitive" or nothing |
| `has_deadline` | An application closing date is stated. | "Apply by", "closes on", a date | "Open until filled" or nothing |
| `has_recruiter_name` | A named contact person (recruiter / hiring manager) appears. | A person's name given as contact | No person named |
| `has_recruiter_contact` | Contact details for a person appear. | Email, phone or LinkedIn of a contact | Only a generic careers address or nothing |
| `has_subrole_categories` | Fine-grained technical sub-areas can be inferred. | Stack / responsibilities make specific areas clear | Too generic |
| `has_position_level` | Seniority level is stated or clearly inferable. | "Junior", "Senior", "Intern", "3+ years" | Nothing about level |

Choices (direct-to-Excel candidates):

- `work_mode`: `in_person`, `hybrid`, `remote`, `travel`, `tbd`, `unknown`. `tbd` = posting says it is to be determined / discussed; `unknown` = not mentioned.
- `employment_type`: `full_time` → Permanent Full-time, `part_time` → Permanent Part-time, `contract`, `contract_full_time`, `contract_part_time`, `internship` → Internship Full-time, `internship_part_time` → Internship Part-time, `co_op` → Co-op Full-time, `co_op_part_time` → Co-op Part-time, `temporary`, `freelance`, `unknown`.
- `upload_mode`: `single_document` (resume only), `separate_uploads` (several documents, separate fields), `single_combined_file` (several documents merged into one file), `not_stated`. When Jev returns `not_stated` or no usable answer, the session's upload mode is `separate_uploads`.

Document nouls (pre-fill the Files tab): `requires_cover_letter`, `requires_transcript`, `requires_portfolio`, `requires_references`.

Gate noul: `is_job_posting`.

Thresholds (config, defaults): `noul_include_threshold = 0.35` (a field with noul >= 0.35 goes into the LLM schema; bias toward inclusion since an extra field just returns `null`), `choice_direct_confidence = 0.7` (choice written straight to Excel at or above this; below it the column is added to the LLM schema as an enum), document nouls >= 0.5 pre-tick a document type.

Choices also include `role_category` (17 fixed buckets → Excel `Role_Category`, incl. Applied AI), classified in a **second** Jev call after subroles are known (state: posting + `subrole_categories`). Unlike Work_Mode / Employment_Type, `Role_Category` is **never left blank**: a valid Jev choice is kept even below `choice_direct_confidence`; missing/unknown choice falls back to `Other tech`.

Not sent to Jev or the LLM (manual): `Applied_Date`, `Posting_URL`, `Application_Status`, `Outcome`, `Applied_Through`, `Found_From` (`HiringCafe`, `LinkedIn`, `Indeed`, `GCJobs`, `CRA`, `Other`), `Days_Since_Applied` (formula), `Folder` (engine).

## 7. LLM extraction (Claude Haiku 5.5)

Request: Messages API, `model: claude-haiku-5-5`, `max_tokens: 2048`, `output_config: { format: { type: "json_schema", schema }, effort: "low" }`. No `temperature` / `top_p` / `top_k` (400 on this model). One retry on transport error or schema-validation failure. Usage is stored in `session.json`.

Schema builder: starts from the ordered candidate list below, keeps only fields whose Jev gate passed (plus low-confidence choice columns), marks every property required and nullable, `additionalProperties: false`.

| property | type | notes |
|---|---|---|
| `requisition_id` | string / null | verbatim |
| `organization` | string / null | hiring company, not the job board |
| `position_title` | string / null | verbatim title |
| `location_country` | string / null | common English country name; may be inferred from unambiguous city/province |
| `location_city` | string / null | city / metro as written; null if remote with no office city |
| `compensation` | string / null | verbatim incl. currency and period, e.g. "CAD 80,000-95,000 / year" |
| `deadline` | string / null | `YYYY-MM-DD` if a date is given; else a short phrase like "Open until filled" |
| `recruiter_name` | string / null | |
| `recruiter_contact` | string / null | email / phone / URL |
| `subrole_categories` | array of string | 1-3 fine-grained labels → Excel `Subrole_Categories`; **cap enforced in prompt and truncated to 3 in code** |
| *(Jev choice, not LLM)* `role_category` | enum of 17 | → Excel `Role_Category` (Frontend, Backend, …, Applied AI, Other tech, Non-tech) |
| `position_level` | string / null | free text, one value (Intern, Junior, Senior, ...) |
| `work_mode` | enum (Excel values) / null | only when Jev confidence < 0.7 |
| `employment_type` | enum (Excel values) / null | only when Jev confidence < 0.7 |

System prompt rules: extract only what the text supports; `null` when absent; never invent compensation, deadlines or cities; country may be inferred from an unambiguous city/province; at most 3 subrole labels, one position level; plain ASCII punctuation. Post-processing: trim strings, parse `deadline` to a date when it matches ISO, join `subrole_categories` with `, ` for Excel.

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
- Lock: before saving, open the file for `r+b`; on `PermissionError` return HTTP 423, keep the payload in `session.review.pending_write` as `{values, force_columns}` (so the retry overwrites the same columns the user meant to overwrite), UI shows "Close Excel and retry" with a Retry button. Also refuses to run while `~$job_application_tracker.xlsx` exists.
- Read-back: opening a session reads the row and shows Excel's current values (Excel wins).

## 10. Files, conversions, CombinationEngine

Conversions (also exposed as a standalone tool in the UI):
- docx -> pdf: `soffice --headless --convert-to pdf --outdir <tmp>`.
- pdf -> docx: `pdf2docx` (lossy; UI says so).
- pdf -> png/jpg: PyMuPDF, one image per page `{stem}_p{n}.png` at configurable DPI (default 150).
- png/jpg -> pdf: `img2pdf`.

Combine (output is always PDF): every input is converted to PDF into `.converted/` inside the folder if needed (cache reused while newer than the source), merged with `pypdf` in display order, saved as `{Candidate_Name}_{X}.pdf` (re-combining overwrites it). Inputs stay in place. The Files tab shows first-page thumbnails (PyMuPDF, cached in `.thumbs/`; Office files go through the PDF cache), drag-reorder or ▲/▼ (files are renumbered on disk with a two-phase rename; finals' `from` and the combined file's `from_indices` are remapped), doc-type dropdown per file (pre-guessed from the file name: resume/cv, cover, transcript, portfolio, reference), per-file convert buttons `→` + format logo (`pdf` / `docx` / `png` / `jpg` from `frontend/src/img/`; result appended as a new input with the same doc type), **Convert all → PDF** (arrow + `pdf_logo.png`; every non-PDF input → PDF appended as new inputs; `POST .../files/convert-all-pdf`), "Make final" (copy + rename per section 8; re-making replaces the earlier final from the same input), "Make finals" for every typed input, and "Combine → PDF". Files the user drops into the folder by hand are listed as *untracked* and can be adopted as inputs; manifest entries whose file disappeared are flagged as *missing*.

Implementation: `backend/files/convert.py` (conversions, `to_pdf`, `thumbnail`, tool detection), `combine.py` (pypdf merge), `manager.py` (`FileManager`: manifest + disk in sync, `x_for()` = {X} from Excel's row when readable). LibreOffice runs headless with a persistent private profile in `%TEMP%/htp_lo_profile` (first call ~15 s, then ~3 s per document). File names from the API are validated to be plain names inside the folder.

Upload mode (from Jev, user can override; override is remembered as `upload_mode_source = user`): `single_document` / `separate_uploads` -> "Make finals" highlighted; `single_combined_file` -> Combine button highlighted.

## 11. Application questions (Q&A)

Inputs per call: `candidate_context.txt` (read fresh every time; path in config), `posting.txt`, organization + title, previously answered questions (read-only, for consistency), pending questions each with optional `{unit: chars|words, value}` limit.

One Claude call (`qa_model`, default `claude-haiku-5-5`, configurable) with structured output `{ answers: [{ id, answer }] }` (`id` constrained to the pending ids via enum). System prompt (`QA_SYSTEM`): write in first person as the candidate; use only facts in the context and posting, never invent, no placeholders; aim for 70-95 % of each limit; no em/en dashes, no markdown. Engine (`backend/qa/answer.py`): strips quotes and converts dashes in code, verifies limits (`chars` = `len`, `words` = whitespace split) and re-asks once for the offenders with the previous answer and an explicit "at most N" instruction; if still over, keeps the shorter answer and sets `question.note`. Usage accumulates in `qa.usage`.

Operations: add one or several questions (one per line) with optional limit; edit text/limit (editing an answered question keeps the answer and adds a note); type or edit an answer by hand (`model = "manual"`); reorder; delete; Answer pending (all in one call) or Answer one; Regenerate one with optional feedback (previous answer + feedback go into the prompt; previously answered questions are included read-only for consistency); Copy. `answers.md` is regenerated after every change and is downloadable through the files endpoint. Missing or empty `candidate_context.txt` -> HTTP 412 with the expected path; the UI shows a banner with the path and disables the Answer buttons. Token guard as in section 7.

## 12. UI screens

**Chrome (all pages):** header status icons from `frontend/src/img/` (Excel green/red = tracker found/missing; Jev green/red = TYPESAFE key; Claude orange/grey = Anthropic key; locked tracker dims the Excel icon). Amber banner when the tracker is open in Excel.

**Sync dock** (`SyncDock.vue`, right column beside main content): sticky panel for the three editable dropdown columns only. Minimized = colored chrome only (refresh arrows + green Excel logo | min/max); maximized grows left into the flex row and shows per-column diffs (only-in-HTP / only-in-Excel / order / missing DV). Button tone: blue = in sync (still clickable), yellow = differs, grey = locked. Sync pushes HTP → Excel (`POST /meta/options/sync`). Distinct from the Dashboard list-refresh control (refresh icon only, no Excel logo).

1. **Dashboard** - list of application folders with status/outcome read from Excel; icon-only **Refresh** reloads `GET /sessions` (does not sync dropdowns); "New application". Deadline is not a column here. Row color follows Outcome when it is terminal (Withdrawn grey, Rejected red, Offer and Accepted light green). While Outcome is Pending or blank, Application_Status sets the color (Not Applied yellow, Applied the default white, Recruiter-Screening light blue, Technical Interview orange, Final Round light purple). Metrics at the bottom (`DashboardMetrics.vue`).
2. **New application** - paste posting + URL -> Run -> three panels: Jev results (chips with probability/confidence), extracted fields (editable form; Compensation has a compact **Estimated.** toggle stored only in `session.json`), manual fields (Applied_Date, Posting_URL, Application_Status, Outcome, Applied_Through, Found_From). Dropdowns for Status / Applied Through / Found From include **Add…** to permanently grow the list (config + Excel DV). A "Possible duplicate" banner lists matching sessions (section 15); "Create" makes the folder and writes the row, asking for confirmation when a duplicate was flagged (disabled while tracker locked).
3. **Session** - tabs: Overview (Excel read-back, edit manual fields, write; Compensation **Estimated.** flag via `PUT /flags`; **Duplicate…** opens a panel to edit identifying fields — especially `Requisition_ID` — then creates a new folder dated today with the same posting/Jev/LLM and empty files/Q&A; **Re-extract** card runs Jev/LLM again on the stored posting and shows a per-column diff against the row with checkboxes; "Apply" writes the chosen columns with `force_columns`), Files (section 10), Questions (section 11; unsaved answer drafts in other boxes are preserved when saving/answering/regenerating one question), Notes (plain textarea; auto-saves to `session.notes`), Log (raw Jev/LLM payloads of the latest run, usage). Save / Retry / Apply / Duplicate disabled while tracker locked.
4. **Convert** - standalone converter (section 10); nothing is stored. Multi-file drop + **→ PDF** (`POST /files/convert-all-pdf`) downloads one PDF or a zip; already-PDF uploads are passed through.
5. **Settings** - edits `htp.config.json` through `PUT /settings` (partial, deep-merged, validated; `settings()` cache cleared; retargets lock watch); shows key / tracker / candidate-context presence with paths on their own wrapping lines, and a tail of the log file. Dropdown sync UX lives in the Sync dock, not on this page.

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
  "backups_keep": 10,
  "options": {
    "Application_Status": ["Not Applied", "Applied", "Recruiter-Screening", "Technical Interview", "Final Round"],
    "Applied_Through": ["Org-Portal", "Indeed", "LinkedIn", "Email", "Workday", "Greenhouse", "AshbyHQ", "UltiPro", "Other"],
    "Found_From": ["HiringCafe", "LinkedIn", "Indeed", "GCJobs", "CRA", "Other"]
  }
}
```

`options` is optional; absent keys use the shipped defaults. The first successful `POST /meta/options/{column}` seeds all three editable lists into the config file.

## 14. API (FastAPI, prefix `/api`)

| Method + path | Purpose |
|---|---|
| `GET /health` | cold-start poll |
| `GET /meta` / `GET /settings` | column lists + resolved dropdown options (+ `editable_option_columns`); key presence, paths; settings also includes `tracker_status` |
| `POST /meta/options/{column}` `{value}` | append to an editable dropdown list (`Application_Status` / `Applied_Through` / `Found_From`); persists to config; syncs Excel list DV (options still saved if Excel is locked — `excel_synced: false`) |
| `POST /meta/options/sync` | push HTP editable option lists into Excel list DVs; 423 if locked |
| `GET /tracker/status?force=` | lock state (`~$` watch + probe) + dropdown DV compare vs HTP (`in_sync` / `mismatched` / `locked` / …); `suggest_sync` when unlocked and mismatched |
| `GET /sessions` / `GET /sessions/{folder}` | list / load (includes Excel read-back and unmanaged folders) |
| `POST /extract` | posting -> Jev answers + derived + LLM values in one call (`use_jev` / `use_llm` toggles); also returns `duplicates: [{folder, reason}]` |
| `POST /sessions` | create folder + session.json + Excel row (extraction + manual values + row overrides); 409 `DuplicateError` (with `duplicates`) unless `allow_duplicate: true` |
| `POST /sessions/{folder}/duplicate` | clone into a new folder dated today (`{values}` overrides applied before naming); copies posting + Jev/LLM; files/Q&A empty; always allows same posting hash |
| `PUT /sessions/{folder}/flags` | UI-only session flags (not Excel), currently `{compensation_estimated}` |
| `PUT /sessions/{folder}/notes` | free-text Notes tab body (`{notes}`); session.json only |
| `PUT /sessions/{folder}/row` | write edited fields; body `{values, force_columns}` — `force_columns` overwrite, others fill-only-empty |
| `POST /sessions/{folder}/row/retry` | flush `review.pending_write` (`{values, force_columns}`) after Excel is closed |
| `POST /sessions/{folder}/reextract` `{use_jev, use_llm}` | run extraction again on the stored posting; returns `{extraction, row, diff:[{column, current, proposed, changed}]}` over the extracted columns; writes nothing to Excel, replaces `jev`/`llm` in session.json |
| `GET|POST /sessions/{folder}/files` | manifest view (`FilesView`: files, upload mode, required docs, untracked, missing, `x`, tools) / multipart upload (`files[]`) |
| `PUT .../files/order` `{order}` · `PUT .../files/{idx}` `{doc_type}` · `DELETE .../files/{idx}` | reorder (renumbers on disk), set doc type, delete input |
| `POST .../files/{idx}/convert` `{target}` | convert one input; result appended as new input(s) |
| `POST .../files/convert-all-pdf` | convert every non-PDF input to PDF; results appended as new inputs |
| `POST .../files/final` `{indices?}` · `POST .../files/combine` `{indices?}` · `DELETE .../files/output/{name}` | make finals (default: all typed) / combine (default: all) / delete a final or the combined PDF |
| `POST .../files/adopt` `{name}` · `PUT .../files/upload-mode` `{upload_mode}` | adopt an untracked file / override upload mode |
| `GET .../files/thumb/{name}?width=` · `GET .../files/download/{name}?inline=` | first-page PNG / file download or inline open |
| `GET /files/tools` · `POST /files/convert` (multipart `file` + `target`) · `POST /files/convert-all-pdf` (multipart `files`) | tool availability / standalone converter / multi-file → PDF (zip when >1; PDFs passed through) |
| `GET /sessions/{folder}/qa` | `QAView`: questions, usage, context-file presence + path, `answers.md` presence, org/title |
| `POST .../qa/questions` `{questions:[{text, limit?}]}` · `PUT .../qa/questions/order` `{order}` · `PUT .../qa/questions/{qid}` `{text?, limit?, clear_limit?, answer?}` · `DELETE .../qa/questions/{qid}` | manage questions; `answer` = manual answer |
| `POST .../qa/answer` `{ids?}` · `POST .../qa/regenerate/{qid}` `{feedback?}` | answer pending (or given ids) in one call / redo one with feedback |
| `GET/PUT /settings` | config view / partial update `{config}` written to `htp.config.json` (400 with field names on validation error) |
| `GET /logs?lines=` | tail of `Applications/.htp_logs/htp.log` (1-2000 lines) |

LLM/Jev failures return HTTP 502 with the provider message (as in Resumate); Excel lock returns 423; duplicate posting 409 (`type: "DuplicateError"`); conversion failures and invalid file operations 400; missing files 404; uploads over 50 MB 413; missing candidate context 412.

### Logging

`logs.setup_logging(cfg)` attaches a console handler and a `RotatingFileHandler` (2 MB x 5) at `<applications_dir>/.htp_logs/htp.log` to the `htp` logger; modules log under `htp.jev`, `htp.llm`, `htp.tracker`, `htp.pipeline`, `htp.files`, `htp.qa`, `htp.api`. Every Jev/Claude call (model, tokens, duration, attempts), every tracker write (row, written/skipped/forced columns), lock refusals, duplicate refusals, file operations and Q&A runs are logged at INFO; provider failures at WARNING/ERROR. The CLI logs to the same file with a quiet console. The API never logs posting text, candidate context or answers.

## 15. Edge cases

- Posting pasted twice: `duplicates.find_duplicates()` compares the normalised posting hash (`posting.hash` in session.json; computed on the fly for older sessions) and the extracted Requisition_ID (+ Organization when both have one) against every session. `POST /extract` reports hits; `POST /sessions` refuses with 409 unless `allow_duplicate`; the UI shows a banner and asks for confirmation. The CLI has `--allow-duplicate`.
- Same role, different requisition (intentional second application): use Session **Duplicate…**, change `Requisition_ID` (and any other fields) in the panel, then Create. Folder name uses the new values + today's date; the original session is untouched. `POST /sessions/{folder}/duplicate` always sets `allow_duplicate`.
- Re-extraction: `POST /sessions/{f}/reextract` never writes; the diff is computed against the Excel row (falls back to `review.values` when the workbook is unreadable) and applied by the user through `PUT /row` with `force_columns`.
- Jev 429/529: SDK backoff; surface after 3 attempts.
- LLM returns a value for a field Jev gated out: impossible by construction (field not in schema).
- Role categories > 3 or empty: truncate / `null`.
- Deadline not ISO: stored as text; `Days_Since_Applied` unaffected.
- Folder exists but no `session.json` (manual folder): listed as "unmanaged", can be adopted.
- Tracker headers changed: writer fails fast with the missing header name.
- Excel list DV uses spaces after commas: stripped on read so HTP vs Excel compare is not a false mismatch.
- Orphan `~$…xlsx` after an Excel crash keeps the UI in locked state until the lock file is removed.

## 16. Implementation order

1. ✅ **Core, no UI**: config, naming, session store, Jev client + questions, schema builder, Claude client, Excel writer; a small CLI (`python -m backend.run --posting file.txt`) to validate end to end.
2. ✅ **Webapp**: Dashboard, New application, Session Overview (tracker-row editor, pending-write banner + retry, posting text, Jev/LLM log). Files and Questions tabs are placeholders.
3. ✅ **Files**: conversions, combine, thumbnails, reorder UI, standalone `/convert` page.
4. ✅ **Q&A**.
5. ✅ **Hardening**: committed `tests/` (pytest, offline), re-extract diff, duplicate detection, logs, Settings page. Backups and the lock flow were already in place from step 1-2.

## 17. Tests

`python -m pytest` from the repo root (venv active). `tests/conftest.py` points `HTP_CONFIG` at a scratch config before `backend` is imported and gives every test a fresh Applications dir, a synthetic tracker (19 headers, table `Applications`, seed row with the formula) and a candidate-context file under `tmp_path`. Jev and Claude are never called: `test_jev_schema.py` feeds synthetic answers to `derive()`, `test_qa.py` uses a scripted fake client, and `test_api.py` monkeypatches `extract` / `ClaudeClient` in the routers and drives the whole API through `TestClient`. LibreOffice is not required (PDF/PNG only).
