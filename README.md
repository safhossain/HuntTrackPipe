# HuntTrackPipe

# 🚧 UNDER CONSTRUCTION 🚧
# STATUS: Step 1 of 5 done (core pipeline + CLI)

## Issue to solve
Logging every job application by hand (copying fields into a spreadsheet, making folders, renaming and merging documents, answering portal questions) is slow and error-prone.

## Proposed solution
A local pipeline that takes a pasted job posting and:
1. Asks **Jev** (TypeSafe) typed pre-LLM questions: which fields exist, work mode, employment type, how documents must be uploaded.
2. Builds a JSON schema from Jev's answers and has **Claude Haiku 5.5** extract only those fields.
3. Creates a per-application folder and writes one row to `job_application_tracker.xlsx` (the only source of truth; no database).
4. *(planned)* Renames, converts and combines application files into one PDF.
5. *(planned)* Answers application text-field questions from your own candidate context file.

Complementary to [Resumate](../resumate) but deliberately decoupled: the two share files, not code.

Full design: [`docs/DESIGN.md`](docs/DESIGN.md).

## How to Run

### Prereqs
- Python 3.11+ (developed on 3.14 in the shared `resumate_env` venv)
- LibreOffice on PATH (needed from step 3, docx -> pdf)
- API keys in `.env` at the repo root:
  ```
  TYPESAFE_API_KEY=...
  ANTHROPIC_API_KEY=...
  ```
  Get the Jev key from `console.typesafe.ai` only; third-party "Jev" resellers exist.

### Install
Activate the venv, then from the repo root:
> python -m pip install -r requirements.txt

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

### Webapp (step 2, not built yet)
Will run on **API :8010** and **UI :5180**, so it can run alongside Resumate (`:8000` / `:5173`).

## What it creates
```
JobHunting/Applications/
  job_application_tracker.xlsx
  .htp_backup/                                     # last 10 tracker copies, one per write
  R-204817_Shopify_Junior-Software-Engineer_2026-10-11/
    session.json                                   # engine state (Jev/LLM output, files, Q&A)
    posting.txt
```
Folder name: `{Requisition_ID}_{Organization}_{Position_Title}_{Date_Created}`. Missing parts become `null`; collisions get `_2`, `_3`, ...

## Roadmap
1. ✅ Core: config, naming, Jev, schema builder, Claude, Excel writer, CLI
2. Webapp: dashboard, new-application flow, session overview
3. Files: conversions, combine to PDF, thumbnails, reorder UI
4. Application questions (Q&A)
5. Hardening: lock-retry flow, re-extract diff, duplicate detection, logs
