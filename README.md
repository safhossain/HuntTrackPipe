# HuntTrackPipe

# 🚧 UNDER CONSTRUCTION 🚧
# STATUS: Step 3 of 5 done (core pipeline + CLI + webapp + files)

## Issue to solve
Logging every job application by hand (copying fields into a spreadsheet, making folders, renaming and merging documents, answering portal questions) is slow and error-prone.

## Proposed solution
A local pipeline that takes a pasted job posting and:
1. Asks **Jev** (TypeSafe) typed pre-LLM questions: which fields exist, work mode, employment type, how documents must be uploaded.
2. Builds a JSON schema from Jev's answers and has **Claude Haiku 5.5** extract only those fields.
3. Creates a per-application folder and writes one row to `job_application_tracker.xlsx` (the only source of truth; no database).
4. Renames, converts and combines application files into one PDF.
5. *(planned)* Answers application text-field questions from your own candidate context file.

Complementary to [Resumate](../resumate) but deliberately decoupled: the two share files, not code.

Full design: [`docs/DESIGN.md`](docs/DESIGN.md).

## How to Run

### Prereqs
- Python 3.11+ (developed on 3.14 in the shared `resumate_env` venv)
- LibreOffice (for Office -> PDF; auto-detected in `C:\Program Files\LibreOffice`, or set `files.soffice_path` in `htp.config.json`)
- API keys in `.env` at the repo root:
  ```
  TYPESAFE_API_KEY=...
  ANTHROPIC_API_KEY=...
  ```
  Get the Jev key from `console.typesafe.ai` only; third-party "Jev" resellers exist.

### Install
Activate the venv, then from the repo root:
> python -m pip install -r requirements.txt

For the webapp (Node 20+):
> npm install && npm --prefix frontend install

### Configure
Edit `htp.config.json` (non-secret settings: paths, candidate name, Jev thresholds, model IDs).
Set `HTP_CONFIG=<path>` to use a different config file, e.g. to point at a scratch copy of the tracker.

The tracker must contain a table named `Applications` with these headers (order does not matter):
`Requisition_ID, Organization, Position_Title, Compensation, Work_Mode, Employment_Type, Deadline, Applied_Date, Posting_URL, Application_Status, Recruiter_Name, Recruiter_Contact, Outcome, Role_Categories, Position_Level, Days_Since_Applied, Applied_Through, Confirmation_#, Folder`

**Close the workbook in Excel before running.** The engine refuses to write while Excel holds the file.

### CLI
Extract only (no folder, no Excel write):
> python -m backend.run --posting posting.txt --dry-run

Create folder + row (asks for confirmation; `-y` skips it):
> python -m backend.run --posting posting.txt --url https://... --applied-date 2026-10-11 --status Applied --applied-through LinkedIn

Other flags:
| Flag | Effect |
|---|---|
| `--posting -` | read the posting from stdin |
| `--no-jev` | skip Jev; the LLM extracts every field |
| `--no-llm` | skip the LLM; only Jev's direct values (Work_Mode, Employment_Type) are used |
| `--json` | machine-readable output |
| `--confirmation` | Confirmation_# |

### Webapp
With the venv active, from the repo root:
> npm run dev

Starts the FastAPI backend on **http://127.0.0.1:8010** and the Vue UI on **http://localhost:5180** (`strictPort`; `/api` is proxied). Both ports differ from Resumate (`:8000` / `:5173`) so the two can run together. `npm run api` / `npm run ui` start them separately.

Screens:
- **Dashboard** (`/`): every managed session with its row read back from Excel (status, outcome, applied date, days since, deadline), plus a list of unmanaged folders.
- **New application** (`/new`): paste the posting, run Jev + Claude (either can be toggled off), review Jev's answers and the extracted fields, fill the manual fields (Applied_Date, Posting_URL, status, outcome, Applied_Through, Confirmation_#), then create the folder + row.
- **Session** (`/sessions/{folder}`): Overview tab edits the tracker row (edited fields overwrite Excel, untouched fields never do); if Excel has the workbook open the write is kept as a pending write and a Retry button flushes it later. Files tab (below). Log tab shows raw Jev/LLM output. Questions tab arrives in step 4.
- **Files tab**: drop files in (saved as `{count}_<name>.<ext>`), thumbnails, drag or ▲/▼ to reorder (renumbers on disk), pick a document type per file (guessed from the name), convert a file in place (PDF ⇄ DOCX, PDF → PNG/JPG, anything → PDF; the result is added as a new input), **Make final** → `{Candidate_Name}_{DocType}_{X}.<ext>`, **Combine → PDF** → `{Candidate_Name}_{X}.pdf` (non-PDF inputs are converted first, merged in display order). Files you drop into the folder by hand show up as *untracked* and can be adopted. Jev's upload-mode hint highlights the relevant button; you can override it.
- **Convert** (`/convert`): standalone converter, nothing is stored. PDF → PNG/JPG gives one image per page (zipped).

## What it creates
```
JobHunting/Applications/
  job_application_tracker.xlsx
  .htp_backup/                                     # last 10 tracker copies, one per write
  R-204817_Shopify_Junior-Software-Engineer_2026-10-11/
    session.json                                   # engine state (Jev/LLM output, file manifest, Q&A)
    posting.txt
    0_resume.pdf  1_cover-letter.docx              # inputs, in display order
    Safwan-Hossain_Resume_R-204817.pdf             # final (renamed copy)
    Safwan-Hossain_R-204817.pdf                    # combined PDF
    .converted/  .thumbs/                          # caches (safe to delete)
```
Folder name: `{Requisition_ID}_{Organization}_{Position_Title}_{Date_Created}`. Missing parts become `null`; collisions get `_2`, `_3`, ...

## Roadmap
1. ✅ Core: config, naming, Jev, schema builder, Claude, Excel writer, CLI
2. ✅ Webapp: dashboard, new-application flow, session overview (incl. Excel-locked pending write + retry)
3. ✅ Files: conversions, combine to PDF, thumbnails, reorder UI, standalone converter
4. Application questions (Q&A)
5. Hardening: committed tests, re-extract diff, duplicate detection, logs
