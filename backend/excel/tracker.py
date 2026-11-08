"""Excel tracker writer (DESIGN.md section 9).

* Columns are located by header name inside the ``Applications`` table.
* A row is matched by the ``Folder`` column; otherwise the first empty data row
  is used; otherwise a row is appended and the table range extended.
* Fill-only-empty by default: non-empty cells that differ are reported, not overwritten.
* Save = backup copy -> write temp file -> ``os.replace``.
* Refuses to write while Excel holds the file (``~$`` owner file or PermissionError).
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, quote_sheetname, range_boundaries
from openpyxl.workbook import Workbook
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table
from openpyxl.worksheet.worksheet import Worksheet

TABLE_NAME = "Applications"
FOLDER_COL = "Folder"
FORMULA_COLS: dict[str, str] = {
    "Days_Since_Applied": (
        '=IF(Applications[[#This Row],[Applied_Date]]="","",'
        "TODAY()-Applications[[#This Row],[Applied_Date]])"
    ),
}
DATE_COLS = {"Applied_Date", "Deadline"}
NEW_ROW_DEFAULTS = {"Application_Status": "Not Applied", "Outcome": "Pending"}
DATE_FORMAT = "yyyy-mm-dd"
BACKUP_DIR = ".htp_backup"
# Excel inline list formula1 (contents inside the quotes) max length.
EXCEL_LIST_MAX = 255
_ROLE_LIST_COLUMN = "Role_Category"
_ROLE_LIST_SHEET = "_HTP_Lists"
_ROLE_LIST_NAME = "HTP_Role_Category_Options"
log = logging.getLogger("htp.tracker")


def _dv_covers_column(dv: DataValidation, col_idx: int) -> bool:
    """True if any sqref part includes ``col_idx`` (single-col or multi-col span)."""
    for part in str(dv.sqref or "").replace(",", " ").split():
        try:
            min_c, _min_r, max_c, _max_r = range_boundaries(part)
        except ValueError:
            continue
        if min_c <= col_idx <= max_c:
            return True
    return False


def _managed_role_list(wb: Workbook) -> tuple[Worksheet, int] | None:
    """Identify our workbook-scoped range before reading or updating it."""
    definition = wb.defined_names.get(_ROLE_LIST_NAME)
    if definition is None or _ROLE_LIST_SHEET not in wb.sheetnames:
        return None
    sheet = wb[_ROLE_LIST_SHEET]
    sheet_ref, separator, cells = definition.attr_text.partition("!")
    if sheet.sheet_state != "veryHidden" or not separator or sheet_ref not in (
        _ROLE_LIST_SHEET, quote_sheetname(_ROLE_LIST_SHEET),
    ):
        return None
    try:
        first_col, first_row, last_col, last_row = range_boundaries(cells)
    except ValueError:
        return None
    if first_col == last_col == first_row == 1 and last_row is not None and last_row >= 1:
        return sheet, last_row
    return None


def _write_role_list(ws: Worksheet, values: list[str]) -> str:
    wb = ws.parent
    folded_name = _ROLE_LIST_NAME.casefold()
    if any(name.casefold() == folded_name for name in ws.defined_names):
        raise TrackerError(f"Cannot use a workbook range named {_ROLE_LIST_NAME!r}: the sheet already defines that name.")
    managed = _managed_role_list(wb)
    if managed is None:
        if any(name.casefold() == _ROLE_LIST_SHEET.casefold() for name in wb.sheetnames) or any(
            name.casefold() == folded_name for name in wb.defined_names
        ):
            raise TrackerError(f"Reserved Excel sheet {_ROLE_LIST_SHEET!r} or range {_ROLE_LIST_NAME!r} is already in use.")
        sheet = wb.create_sheet(_ROLE_LIST_SHEET)
        sheet.sheet_state = "veryHidden"
        old_length = 0
    else:
        sheet, old_length = managed

    for row, value in enumerate(values, start=1):
        cell = sheet.cell(row, 1, value)
        cell.data_type = "s"
    for row in range(len(values) + 1, old_length + 1):
        sheet.cell(row, 1).value = None
    wb.defined_names.add(DefinedName(
        _ROLE_LIST_NAME,
        attr_text=f"{quote_sheetname(sheet.title)}!$A$1:$A${len(values)}",
    ))
    return _ROLE_LIST_NAME


def _list_formula(ws: Worksheet, column: str, values: list[str]) -> str:
    if any("," in v for v in values):
        raise TrackerError("Dropdown values cannot contain commas (Excel list delimiter).")
    joined = ",".join(values)
    if len(joined) > EXCEL_LIST_MAX:
        if column == _ROLE_LIST_COLUMN:
            return _write_role_list(ws, values)
        raise TrackerError(
            f"Dropdown list is too long for Excel inline validation "
            f"({len(joined)} > {EXCEL_LIST_MAX} characters)."
        )
    return f'"{joined}"'


def _apply_list_validations(
    ws: Worksheet,
    headers: dict[str, int],
    options_by_header: dict[str, list[str]],
    *,
    body_first_row: int,
    body_last_row: int,
) -> list[str]:
    """Replace list validations for the given headers over the table body only.

    ``body_first_row`` / ``body_last_row`` are 1-based sheet rows (header excluded).
    """
    if body_last_row < body_first_row:
        return []
    touched: list[str] = []
    dvs = ws.data_validations.dataValidation
    for name, values in options_by_header.items():
        if name not in headers:
            continue
        col = headers[name]
        formula = _list_formula(ws, name, values)
        remaining = [dv for dv in dvs if not _dv_covers_column(dv, col)]
        dvs[:] = remaining
        letter = get_column_letter(col)
        dv = DataValidation(type="list", formula1=formula, allow_blank=True)
        dv.add(f"{letter}{body_first_row}:{letter}{body_last_row}")
        ws.add_data_validation(dv)
        touched.append(name)
    return touched


class TrackerError(RuntimeError):
    pass


class TrackerLocked(TrackerError):
    """The workbook is open in Excel (or otherwise not writable)."""


@dataclass
class WriteReport:
    row: int
    created: bool
    written: dict[str, Any] = field(default_factory=dict)
    skipped: dict[str, tuple[Any, Any]] = field(default_factory=dict)  # column -> (existing, attempted)


def _is_empty(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v.strip() == "")


def _norm(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return v.strip()
    return v


def owner_file_for(tracker_path: Path) -> Path:
    """Excel's lock/owner file next to the workbook (``~$name.xlsx``)."""
    p = Path(tracker_path)
    return p.with_name(f"~${p.name}")


def parse_list_formula(formula1: str | None) -> list[str] | None:
    """Parse an inline Excel list ``formula1`` (``\"a,b,c\"``) into values.

    Excel often stores ``\"a, b, c\"`` (space after commas). Each item is
    stripped so those match HTP's unspaced option lists.

    Returns ``None`` when the formula is missing or not an inline comma list
    (e.g. a named range / sheet reference).
    """
    if formula1 is None:
        return None
    s = str(formula1).strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    if not s:
        return []
    # Named ranges / sheet refs are not comparable to HTP option lists here.
    if s.startswith("=") or "!" in s or s.startswith("$"):
        return None
    return [part.strip() for part in s.split(",")]



class Tracker:
    def __init__(self, path: Path, backups_keep: int = 10):
        self.path = Path(path)
        self.backups_keep = backups_keep

    @property
    def owner_file(self) -> Path:
        return owner_file_for(self.path)

    # ------------------------------------------------------------------ io
    def check_writable(self) -> None:
        if not self.path.exists():
            raise TrackerError(f"Tracker not found: {self.path}")
        owner = self.owner_file
        if owner.exists():
            log.warning("tracker locked: %s present", owner.name)
            raise TrackerLocked(f"{self.path.name} appears to be open in Excel (found {owner.name}). Close it and retry.")
        try:
            with open(self.path, "r+b"):
                pass
        except PermissionError as exc:
            log.warning("tracker locked: PermissionError on r+b")
            raise TrackerLocked(f"{self.path.name} is locked by another program. Close it and retry.") from exc

    def read_list_options(self, columns: list[str] | tuple[str, ...]) -> dict[str, list[str] | None]:
        """Return inline or HTP-managed list choices per header, if readable."""
        wb, ws, table = self._open()
        headers = self._headers(ws, table)
        out: dict[str, list[str] | None] = {}
        for name in columns:
            if name not in headers:
                out[name] = None
                continue
            col = headers[name]
            found: list[str] | None = None
            for dv in ws.data_validations.dataValidation:
                if dv.type == "list" and _dv_covers_column(dv, col):
                    formula = (dv.formula1 or "").strip()
                    if name == _ROLE_LIST_COLUMN and formula.removeprefix("=").casefold() == _ROLE_LIST_NAME.casefold():
                        managed = _managed_role_list(wb)
                        if managed is not None:
                            sheet, length = managed
                            values = [sheet.cell(row, 1).value for row in range(1, length + 1)]
                            if all(isinstance(value, str) for value in values):
                                found = [value.strip() for value in values]
                    else:
                        found = parse_list_formula(dv.formula1)
                    break
            out[name] = found
        return out

    def _open(self):
        wb = load_workbook(self.path)
        for ws in wb.worksheets:
            if TABLE_NAME in ws.tables:
                return wb, ws, ws.tables[TABLE_NAME]
        raise TrackerError(f"Table '{TABLE_NAME}' not found in {self.path.name}")

    @staticmethod
    def _bounds(table: Table) -> tuple[int, int, int, int]:
        min_col, min_row, max_col, max_row = range_boundaries(table.ref)
        return min_col, min_row, max_col, max_row

    def _headers(self, ws: Worksheet, table: Table) -> dict[str, int]:
        min_col, min_row, max_col, _ = self._bounds(table)
        headers: dict[str, int] = {}
        for c in range(min_col, max_col + 1):
            v = ws.cell(min_row, c).value
            if v is not None:
                headers[str(v).strip()] = c
        return headers

    def _backup(self) -> None:
        bdir = self.path.parent / BACKUP_DIR
        bdir.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        shutil.copy2(self.path, bdir / f"{self.path.stem}.{stamp}{self.path.suffix}")
        backups = sorted(bdir.glob(f"{self.path.stem}.*{self.path.suffix}"))
        for old in backups[: max(0, len(backups) - self.backups_keep)]:
            old.unlink(missing_ok=True)

    def _save(self, wb) -> None:
        self._backup()
        tmp = self.path.with_name(f".{self.path.stem}.tmp{self.path.suffix}")
        wb.save(tmp)
        os.replace(tmp, self.path)

    # ---------------------------------------------------------------- read
    def headers(self) -> list[str]:
        _, ws, table = self._open()
        return list(self._headers(ws, table))

    def find_row(self, folder: str) -> int | None:
        _, ws, table = self._open()
        return self._find_row(ws, table, folder)

    def _find_row(self, ws: Worksheet, table: Table, folder: str) -> int | None:
        headers = self._headers(ws, table)
        if FOLDER_COL not in headers:
            raise TrackerError(f"Column '{FOLDER_COL}' missing from table '{TABLE_NAME}'")
        _, min_row, _, max_row = self._bounds(table)
        col = headers[FOLDER_COL]
        for r in range(min_row + 1, max_row + 1):
            if _norm(ws.cell(r, col).value) == folder:
                return r
        return None

    def read_row(self, folder: str) -> dict[str, Any] | None:
        _, ws, table = self._open()
        r = self._find_row(ws, table, folder)
        if r is None:
            return None
        return {name: _norm(ws.cell(r, c).value) for name, c in self._headers(ws, table).items()}

    def read_all(self) -> list[dict[str, Any]]:
        _, ws, table = self._open()
        headers = self._headers(ws, table)
        _, min_row, _, max_row = self._bounds(table)
        rows = []
        for r in range(min_row + 1, max_row + 1):
            row = {name: _norm(ws.cell(r, c).value) for name, c in headers.items()}
            if any(not _is_empty(v) for k, v in row.items() if k not in FORMULA_COLS):
                rows.append(row)
        return rows

    # --------------------------------------------------------------- write
    def _first_empty_row(self, ws: Worksheet, table: Table, headers: dict[str, int]) -> int | None:
        _, min_row, _, max_row = self._bounds(table)
        data_cols = [c for name, c in headers.items() if name not in FORMULA_COLS]
        for r in range(min_row + 1, max_row + 1):
            if all(_is_empty(ws.cell(r, c).value) for c in data_cols):
                return r
        return None

    def _extend_table(self, table: Table, new_max_row: int) -> None:
        min_col, min_row, max_col, _ = self._bounds(table)
        ref = f"{get_column_letter(min_col)}{min_row}:{get_column_letter(max_col)}{new_max_row}"
        table.ref = ref
        if table.autoFilter is not None:
            table.autoFilter.ref = ref

    def ensure_columns(self, names: list[str]) -> list[str]:
        """Append any missing header names to the right edge of the Applications table.

        Returns the names that were newly added (empty when already present).
        """
        wanted = [n for n in names if n and n.strip()]
        if not wanted:
            return []
        self.check_writable()
        wb, ws, table = self._open()
        headers = self._headers(ws, table)
        missing = [n for n in wanted if n not in headers]
        if not missing:
            return []
        min_col, min_row, max_col, max_row = self._bounds(table)
        col = max_col
        for name in missing:
            col += 1
            ws.cell(min_row, col).value = name
        ref = f"{get_column_letter(min_col)}{min_row}:{get_column_letter(col)}{max_row}"
        table.ref = ref
        if table.autoFilter is not None:
            table.autoFilter.ref = ref
        self._save(wb)
        log.info("added tracker columns: %s (table now %s)", missing, ref)
        return missing

    def sync_list_validations(self, options_by_header: dict[str, list[str]]) -> list[str]:
        """Rewrite table-body list data-validations for ``options_by_header`` (by header name).

        Returns the column names that were updated. Raises ``TrackerLocked`` when
        Excel has the file open.
        """
        if not options_by_header:
            return []
        self.check_writable()
        wb, ws, table = self._open()
        headers = self._headers(ws, table)
        _min_c, min_row, _max_c, max_row = self._bounds(table)
        touched = _apply_list_validations(
            ws, headers, options_by_header, body_first_row=min_row + 1, body_last_row=max_row,
        )
        if touched:
            self._save(wb)
            log.info("synced list validations (table body rows %d-%d): %s", min_row + 1, max_row, touched)
        return touched

    def clear_column_body(self, column: str) -> int:
        """Set every table-body cell in ``column`` to empty. Returns cleared count."""
        if not column:
            return 0
        self.check_writable()
        wb, ws, table = self._open()
        headers = self._headers(ws, table)
        if column not in headers:
            raise TrackerError(f"Unknown tracker column: {column}. Headers: {list(headers)}")
        _min_c, min_row, _max_c, max_row = self._bounds(table)
        col = headers[column]
        cleared = 0
        for r in range(min_row + 1, max_row + 1):
            cell = ws.cell(r, col)
            if not _is_empty(cell.value):
                cleared += 1
            cell.value = None
        self._save(wb)
        log.info("cleared column %s body cells: %d non-empty of %d rows", column, cleared, max_row - min_row)
        return cleared

    def delete_columns(self, names: list[str]) -> list[str]:
        """Delete named header columns from the Applications table (rightmost first).

        Returns the names that were removed. Callers should re-sync list DVs afterwards.
        """
        wanted = [n for n in names if n and n.strip()]
        if not wanted:
            return []
        self.check_writable()
        wb, ws, table = self._open()
        headers = self._headers(ws, table)
        present = [n for n in wanted if n in headers]
        if not present:
            return []
        min_col, min_row, max_col, max_row = self._bounds(table)
        cols = sorted({headers[n] for n in present}, reverse=True)
        for col in cols:
            ws.delete_cols(col, 1)
        new_max_col = max_col - len(cols)
        if new_max_col < min_col:
            raise TrackerError("Cannot delete the last remaining table column")
        ref = f"{get_column_letter(min_col)}{min_row}:{get_column_letter(new_max_col)}{max_row}"
        table.ref = ref
        if table.autoFilter is not None:
            table.autoFilter.ref = ref
        # Drop any list DV that still points at removed columns (best-effort cleanup).
        dvs = ws.data_validations.dataValidation
        keep = []
        for dv in dvs:
            if any(_dv_covers_column(dv, c) for c in cols):
                continue
            keep.append(dv)
        dvs[:] = keep
        # openpyxl delete_cols leaves hyperlink refs at absolute cells; rebuild Folder links.
        if hasattr(ws, "_hyperlinks"):
            ws._hyperlinks.clear()
        headers_after = self._headers(ws, table)
        if FOLDER_COL in headers_after:
            fcol = headers_after[FOLDER_COL]
            for r in range(min_row + 1, max_row + 1):
                cell = ws.cell(r, fcol)
                if cell.hyperlink is not None:
                    cell.hyperlink = None
                name = cell.value
                if name:
                    cell.value = str(name).rstrip("/")
                    cell.hyperlink = f"{cell.value}/"
        self._save(wb)
        log.info("deleted tracker columns: %s (table now %s)", present, ref)
        return present

    def write_row(
        self,
        folder: str,
        values: dict[str, Any],
        *,
        fill_only_empty: bool = True,
        force_columns: set[str] | frozenset[str] = frozenset(),
        list_options: dict[str, list[str]] | None = None,
    ) -> WriteReport:
        """Write ``values`` ({column: value}) to the row for ``folder``.

        When ``list_options`` is set, table-body list validations for those
        headers are refreshed in the same save (heals a prior locked eager sync).

        Returns what was written and what was skipped. Raises ``TrackerLocked``
        when Excel has the file open, ``TrackerError`` for unknown columns.
        """
        self.check_writable()
        wb, ws, table = self._open()
        headers = self._headers(ws, table)
        unknown = [c for c in values if c not in headers]
        if unknown:
            raise TrackerError(f"Unknown tracker column(s): {unknown}. Headers: {list(headers)}")

        row = self._find_row(ws, table, folder)
        created = row is None
        if created:
            row = self._first_empty_row(ws, table, headers)
            if row is None:
                _, _, _, max_row = self._bounds(table)
                row = max_row + 1
                self._extend_table(table, row)

        report = WriteReport(row=row, created=created)
        payload = dict(values)
        payload[FOLDER_COL] = folder
        if created:
            for col, default in NEW_ROW_DEFAULTS.items():
                payload.setdefault(col, default)

        for column, value in payload.items():
            if value is None:
                continue
            cell = ws.cell(row, headers[column])
            existing = cell.value
            if not _is_empty(existing) and fill_only_empty and column not in force_columns:
                if _norm(existing) != _norm(value):
                    report.skipped[column] = (_norm(existing), value)
                continue
            if column == FOLDER_COL:
                cell.value = folder
                cell.hyperlink = f"{folder}/"
            elif column in DATE_COLS and isinstance(value, (date, datetime)):
                cell.value = value if isinstance(value, datetime) else datetime(value.year, value.month, value.day)
                cell.number_format = DATE_FORMAT
            else:
                cell.value = value
            report.written[column] = value

        for column, formula in FORMULA_COLS.items():
            if column in headers and _is_empty(ws.cell(row, headers[column]).value):
                ws.cell(row, headers[column]).value = formula

        if list_options:
            _min_c, min_row, _max_c, max_row = self._bounds(table)
            _apply_list_validations(
                ws, headers, list_options, body_first_row=min_row + 1, body_last_row=max_row,
            )

        self._save(wb)
        log.info(
            "row %d %s folder=%s written=%s skipped=%s forced=%s",
            row, "created" if created else "updated", folder, sorted(report.written), sorted(report.skipped), sorted(force_columns),
        )
        return report
