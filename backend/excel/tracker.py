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
from openpyxl.utils import get_column_letter, range_boundaries
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
log = logging.getLogger("htp.tracker")


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


class Tracker:
    def __init__(self, path: Path, backups_keep: int = 10):
        self.path = Path(path)
        self.backups_keep = backups_keep

    # ------------------------------------------------------------------ io
    def check_writable(self) -> None:
        if not self.path.exists():
            raise TrackerError(f"Tracker not found: {self.path}")
        owner = self.path.with_name(f"~${self.path.name}")
        if owner.exists():
            log.warning("tracker locked: %s present", owner.name)
            raise TrackerLocked(f"{self.path.name} appears to be open in Excel (found {owner.name}). Close it and retry.")
        try:
            with open(self.path, "r+b"):
                pass
        except PermissionError as exc:
            log.warning("tracker locked: PermissionError on r+b")
            raise TrackerLocked(f"{self.path.name} is locked by another program. Close it and retry.") from exc

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

    def write_row(
        self,
        folder: str,
        values: dict[str, Any],
        *,
        fill_only_empty: bool = True,
        force_columns: set[str] | frozenset[str] = frozenset(),
    ) -> WriteReport:
        """Write ``values`` ({column: value}) to the row for ``folder``.

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

        self._save(wb)
        log.info(
            "row %d %s folder=%s written=%s skipped=%s forced=%s",
            row, "created" if created else "updated", folder, sorted(report.written), sorted(report.skipped), sorted(force_columns),
        )
        return report
