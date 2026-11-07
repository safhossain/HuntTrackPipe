# HuntTrackPipe

Core pipeline, CLI, webapp, files, Q&A, and hardening are implemented. Active development continues on the application workflow and dashboard.

## Issue to solve
Logging every job application by hand (copying fields into a spreadsheet, making folders, renaming and merging documents, answering portal questions) is slow and error-prone.

## Proposed solution
A local pipeline that takes a pasted job posting and:
1. Asks **Jev** (TypeSafe) typed pre-LLM questions: which fields exist, work mode, employment type, how documents must be uploaded.
2. Builds a JSON schema from Jev's answers and has **Claude Haiku 5.5** extract only those fields.
3. Creates a per-application folder and writes one row to `job_application_tracker.xlsx` (source of truth for tracker fields; other application state lives in `session.json`; no database).
4. Renames, converts and combines application files into one PDF.
5. Answers application text-field questions from your own candidate context file.

Complementary to [Resumate](../resumate) but deliberately decoupled: the two share files, not code.

Full design: [`docs/DESIGN.md`](docs/DESIGN.md).

## How to Run

From the repo root. `npm run dev` and `npm run api` use the shared venv’s Python, so you do not need to activate it for the web app. Activate it for the CLI and tests:

> & "C:\Users\saf\Documents\coding\Python\Virtual_Environments\resumate_env\Scripts\Activate.ps1"

Install once:

> python -m pip install -r requirements.txt
> npm install
> npm --prefix frontend install

Start the API and the UI together:

> npm run dev

UI:  http://localhost:5180
API: http://127.0.0.1:8010

Open the UI. The page at `:5180` proxies `/api` to `:8010`, so the browser only talks to 5180. If 5180 is already taken, Vite exits (`strictPort`) instead of switching ports. Resumate uses `:8000` and `:5173`, so both apps can run at the same time.

Start them in two terminals instead:

> npm run api

> npm run ui

`npm run api` is uvicorn on **8010**. `npm run ui` is Vite on **5180**. Health check: http://127.0.0.1:8010/api/health

CLI (no server; venv active, repo root):

> python -m backend.run --posting posting.txt --dry-run
> python -m backend.run --posting posting.txt --url https://... --applied-date 2026-10-11 --status Applied --applied-through LinkedIn --found-from HiringCafe -y

| Flag | Effect |
|---|---|
| `--posting -` | read the posting from stdin |
| `--no-jev` | skip Jev; the LLM extracts every field |
| `--no-llm` | skip the LLM; only Jev's direct values (Work_Mode, Employment_Type) are used |
| `--json` | machine-readable output |
| `--found-from` | Found_From (`HiringCafe`, `LinkedIn`, `Indeed`, `GCJobs`, `CRA`, `Other`) |
| `--allow-duplicate` | create even if the posting matches an existing application (otherwise exit code 5) |
| `-y` / `--yes` | skip the confirmation prompt |

Tests (venv active, repo root; never touches `JobHunting/`):

```powershell
python -m pytest
npm --prefix frontend run test:colors
npm --prefix frontend run build
```

The frontend build runs TypeScript checks and produces the production bundle. `test:colors` checks color priority, row/chart agreement, split-outcome counts, and legacy outcome labels without starting the API.

### Prereqs
- Python 3.11+ (developed on 3.14 in the shared `resumate_env` venv)
- Node 22.18+ (the color tests use Node's built-in TypeScript support)
- LibreOffice (for Office → PDF; auto-detected in `C:\Program Files\LibreOffice`, or set `files.soffice_path` in `htp.config.json`)
- API keys in `.env` at the repo root: `TYPESAFE_API_KEY` and `ANTHROPIC_API_KEY`. Get the Jev key from `console.typesafe.ai` only; third-party "Jev" resellers exist.

### Configure
Edit `htp.config.json` (non-secret settings: paths, candidate name, Jev thresholds, model IDs, optional `options` for Application_Status / Applied_Through / Found_From).
Set `HTP_CONFIG=<path>` to use a different config file, e.g. to point at a scratch copy of the tracker. Dropdown **Add…** in the UI also seeds/updates `options` and can sync Excel data validation (close the workbook first, or use the Sync dock after closing).

Outcome choices are code-owned: **Pending, Early interest, Withdrawn, Rejected, Offer, Accepted**. HTP mirrors them into Excel data validation on tracker writes and dropdown sync. Legacy `Some interest` values still display as `Early interest`; a display alias alone does not rename stored workbook or session values.

For the Questions tab, write `JobHunting/candidate_context.txt` (git-ignored): a plain-text dump of your background, education, jobs and projects with concrete results, skills and tools, and what you are looking for. Answers are written only from facts in this file plus the posting, so the more specific it is the better. It is read fresh on every call; edit it any time.

The tracker must contain a table named `Applications` with these headers (order does not matter):
`Requisition_ID, Organization, Position_Title, Compensation, Work_Mode, Employment_Type, Deadline, Applied_Date, Posting_URL, Application_Status, Recruiter_Name, Recruiter_Contact, Outcome, Role_Category, Subrole_Categories, Position_Level, Days_Since_Applied, Applied_Through, Folder, Found_From, Location_Country, Location_City`

**Close the workbook in Excel before running.** The engine refuses to write while Excel holds the file.

### Screens
- **Header (all pages):** HuntTrackPipe logo links to the dashboard; the browser tab uses a PNG icon with ICO fallback. Small status icons (Excel / Jev / Claude) show tracker found|missing and API-key presence; an amber banner appears when the tracker is open in Excel. **Sync dock** sits beside New application on the Dashboard (expands left/down without narrowing the table; floats at the top right on scroll only when differences exist). It starts minimized and expands when differences are detected. Scrolling back returns the yellow panel beside New application; blue panels scroll away normally. Other pages retain the sticky right column. It shows differences for the three editable lists (`Application_Status`, `Applied_Through`, `Found_From`); sync also refreshes code-owned lists such as Outcome. Blue = in sync, yellow = differs, grey = locked.
- **Dashboard** (`/`): every managed session with its row read back from Excel (status, outcome, applied date, days since), unmanaged folders, metrics. Row colors and the Outcome pie chart share the same priority rules. Icon-only **Refresh** reloads the session list only (not dropdown sync).
- **New application** (`/new`): paste the posting, run Jev + Claude (either can be toggled off), review Jev's answers and the extracted fields, fill the manual fields (Applied_Date, Posting_URL, status, outcome, Applied_Through, Found_From). Status / Applied Through / Found From dropdowns have **Add…** to grow the list in config + Excel. If the posting text or requisition ID matches an existing application a **Possible duplicate** banner links to it and Create asks for confirmation.
- **Session** (`/sessions/{folder}`): Overview tab edits the tracker row (edited fields overwrite Excel, untouched fields never do); if Excel has the workbook open the write is kept as a pending write and a Retry button flushes it later. **Re-extract** runs Jev/Claude again on the stored posting and shows only the columns that differ from the tracker; tick the ones you want and Apply. **Duplicate…** creates a new application dated today after you review identifying fields such as Requisition_ID. It copies posting/extraction records, notes, and the compensation estimate flag; files and Q&A start empty. Log shows raw Jev/LLM output of the latest run.
- **Posting URL and Compensation fields**: Posting URL has **Open** and **Copy link** controls. Compensation has a compact **Estimated.** toggle beside the text field in both creation and session review; the flag is saved in `session.json`.
- **Files tab**: drop files in (saved as `{count}_<name>.<ext>`), thumbnails, drag or ▲/▼ to reorder (renumbers on disk), pick a document type per file (guessed from the name), then click a **→ format-logo** button to convert to any supported target. Conversion results are appended as new inputs. **Make final** → `{Candidate_Name}_{DocType}_{X}.<ext>`; **Combine → PDF** → `{Candidate_Name}_{X}.pdf` (non-PDF inputs are converted first, merged in display order). Files you drop into the folder by hand show up as *untracked* and can be adopted. Jev's upload-mode hint highlights the relevant button; you can override it.
- **Questions tab**: paste application questions (one or several, each with an optional character/word limit), **Answer pending** answers them all in one Claude Haiku call written in first person from your candidate context + the posting; limits are checked in code and over-long answers are re-asked once. Edit answers by hand, **Regenerate…** one with feedback, Copy, reorder. Saving, answering, or regenerating one question preserves unsaved drafts in other boxes. Drafts are local to the mounted Questions panel until saved; `answers.md` contains saved answers.
- **Notes tab**: a plain textbox that auto-saves to `session.notes` after a 500 ms typing pause and on blur.
- **Convert** (`/convert`): standalone converter, nothing is stored. PDF → PNG/JPG gives one image per page (zipped).
- **Settings** (`/settings`): edit `htp.config.json` (paths, candidate name, Jev thresholds, models, DPI, backups, optional `options` lists) without restarting; shows whether the API keys, tracker and candidate context are present, and a live tail of the log.

Logs go to `JobHunting/Applications/.htp_logs/htp.log` (rotating, 2 MB x 5): every Jev/Claude call with token counts and timing, every tracker write with the columns written/skipped, lock and duplicate refusals, file operations. Posting text, candidate context and answers are never logged.

### Dashboard colors and Outcome chart

[`frontend/src/applicationColors.ts`](frontend/src/applicationColors.ts) is the shared source for row colors and priority rules. Withdrawn, Rejected, Offer, and Accepted override status. Early interest overrides only Applied; otherwise it follows status, as do Pending and blank outcomes. Unrecognized outcomes retain the default white background.

The Outcome pie groups applications by **outcome and resolved row background**. If one outcome has several colors, its slices include status labels, such as `Early interest — Applied` and `Early interest — Technical Interview`. Every application is counted once; Offer and Accepted remain separate categories even though they share a color. Updating the shared resolver updates the table, pie, and legend together. Badges and other metrics keep their independent palettes.

See [the complete priority table and maintenance notes](docs/DESIGN.md#121-dashboard-row-colors-and-outcome-chart). After changing the resolver, run `npm --prefix frontend run test:colors` and `npm --prefix frontend run build`.

### Dashboard metrics cards

The compact navbar scrolls with the page by default. Its top-right pin keeps it fixed across pages; unpinning while scrolled slides it upward until you return to the top. Pin state lasts while the app is open and resets on reload. A bottom-left arrow appears when scrolled and smoothly returns to the top (hover: “Scroll to top”). Reduced-motion preferences disable these animations.

The dashboard has 11 cards, computed from managed sessions and their Excel rows. On large screens:

| Row | Cards |
|---|---|
| 1 | Total applications · Outcome · Work mode |
| 2 | Location country · Location city · Role category |
| 3 | Subrole categories · Applied through · Employment type |
| 4 | Status (two columns wide) |
| 5 | Created by month (full width) |

Outcome, Work mode, both locations, Role category, Subrole categories, and Employment type use pies. Applied through, Status, and Created by month use horizontal bars. Location and role cards also show distinct-label counts, excluding `Not set`.

Location lists are split for counting (commas are preserved); subroles split on commas. Duplicate labels within an application count once, so a multi-location/subrole application can contribute to several slices. Excel values are unchanged. Other missing values appear as `Not set`.

Status includes average applications per day, the busiest apply date and count, and the top three organizations. These statistics use rows with an Applied_Date, regardless of status. The average covers the inclusive first-to-last apply-date span, including days with zero applications. Created by month instead uses session creation timestamps. Refresh reloads the data for all cards.

See [metrics calculations and counting rules](docs/DESIGN.md#123-dashboard-metrics-cards) for details.

## What it creates
```
JobHunting/Applications/
  job_application_tracker.xlsx
  .htp_backup/                                     # last 10 tracker copies, one per write
  .htp_logs/htp.log                                # rotating log
  R-204817_Shopify_Junior-Software-Engineer_2026-10-11/
    session.json                                   # engine state, file manifest, Q&A, notes, estimate flag
    posting.txt
    0_resume.pdf  1_cover-letter.docx              # inputs, in display order
    Safwan-Hossain_Resume_R-204817.pdf             # final (renamed copy)
    Safwan-Hossain_R-204817.pdf                    # combined PDF
    answers.md                                     # application questions + answers
    .converted/  .thumbs/                          # caches (safe to delete)
```
Folder name: `{Requisition_ID}_{Organization}_{Position_Title}_{Date_Created}`. Missing parts become `null`; collisions get `_2`, `_3`, ...

## Roadmap
1. ✅ Core: config, naming, Jev, schema builder, Claude, Excel writer, CLI
2. ✅ Webapp: dashboard, new-application flow, session overview (incl. Excel-locked pending write + retry)
3. ✅ Files: conversions, combine to PDF, thumbnails, reorder UI, standalone converter
4. ✅ Application questions (Q&A)
5. ✅ Hardening: committed tests, re-extract diff, duplicate detection, logs, Settings page
