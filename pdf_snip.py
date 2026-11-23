"""
PDF Pages Snipping Tool
-----------------------
Extracts a range of pages from a PDF file into a new PDF file.

Usage:
    python pdf_snip.py input.pdf 3-7
    python pdf_snip.py input.pdf 1,3,5-8 -o output.pdf
"""

import argparse
import sys
import threading
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject

# Some PDFs have deeply nested internal structures (long chains of links,
# bookmarks, annotations) that exceed Python's default recursion limit of 1000
# while pypdf copies them. We do the work in a thread with a large stack and
# a high recursion limit to handle them.
_RECURSION_LIMIT = 50_000
_THREAD_STACK_SIZE = 256 * 1024 * 1024 - 1024 * 1024  # just under Windows' 256 MB max


class PdfSnipError(Exception):
    """Error with a user-friendly message."""


def validate_pdf(path: Path) -> None:
    """Make sure the file exists and is really a PDF (by extension and by content)."""
    if not path.exists():
        raise PdfSnipError(f"שגיאה: הקובץ '{path}' לא נמצא.")
    if not path.is_file():
        raise PdfSnipError(f"שגיאה: '{path}' אינו קובץ.")
    if path.suffix.lower() != ".pdf":
        raise PdfSnipError(f"שגיאה: הקובץ '{path.name}' אינו קובץ PDF (סיומת לא תקינה).")
    # Check the PDF "magic bytes" - every PDF file starts with %PDF-
    with path.open("rb") as f:
        header = f.read(1024)
    if b"%PDF-" not in header:
        raise PdfSnipError(f"שגיאה: הקובץ '{path.name}' אינו קובץ PDF תקין (תוכן הקובץ אינו PDF).")


def parse_page_range(range_str: str, total_pages: int) -> list[int]:
    """
    Parse a page range string such as "3-7" or "1,3,5-8" (1-based, inclusive).
    Returns a list of 0-based page indexes, in the order given.
    """
    pages: list[int] = []
    for part in range_str.replace(" ", "").split(","):
        if not part:
            continue
        try:
            if "-" in part:
                start_s, end_s = part.split("-", 1)
                start = int(start_s) if start_s else 1
                end = int(end_s) if end_s else total_pages
            else:
                start = end = int(part)
        except ValueError:
            raise PdfSnipError(f"שגיאה: טווח עמודים לא תקין: '{part}'.")

        if start < 1 or end < 1:
            raise PdfSnipError("שגיאה: מספרי עמודים חייבים להיות 1 ומעלה.")
        if start > end:
            raise PdfSnipError(f"שגיאה: בטווח '{part}' עמוד ההתחלה גדול מעמוד הסיום.")
        if end > total_pages:
            raise PdfSnipError(
                f"שגיאה: הטווח '{part}' חורג ממספר העמודים בקובץ ({total_pages})."
            )
        pages.extend(range(start - 1, end))

    if not pages:
        raise PdfSnipError("שגיאה: לא צוין אף עמוד.")
    return pages


def _run_with_big_stack(func, *args):
    """Run func(*args) in a thread with a large stack and high recursion limit."""
    result: dict = {}

    def target():
        try:
            result["value"] = func(*args)
        except BaseException as e:  # re-raised in the calling thread
            result["error"] = e

    old_limit = sys.getrecursionlimit()
    old_stack = threading.stack_size()
    try:
        sys.setrecursionlimit(max(old_limit, _RECURSION_LIMIT))
        threading.stack_size(_THREAD_STACK_SIZE)
        t = threading.Thread(target=target)
        t.start()
        t.join()
    finally:
        threading.stack_size(old_stack)
        sys.setrecursionlimit(old_limit)

    if "error" in result:
        raise result["error"]
    return result.get("value")


def _write_pages(reader: PdfReader, pages: list[int], output_path: Path, strip_annots: bool) -> None:
    writer = PdfWriter()
    for idx in pages:
        page = reader.pages[idx]
        if strip_annots and "/Annots" in page:
            del page[NameObject("/Annots")]
        writer.add_page(page)
    with output_path.open("wb") as f:
        writer.write(f)


def snip_pdf(input_path: Path, page_range: str, output_path: Path | None = None) -> Path:
    """Extract the selected pages from input_path and save them to output_path."""
    return _run_with_big_stack(_snip_pdf, input_path, page_range, output_path)


def _snip_pdf(input_path: Path, page_range: str, output_path: Path | None = None) -> Path:
    validate_pdf(input_path)

    try:
        reader = PdfReader(input_path)
        if reader.is_encrypted:
            # Try opening with an empty password (common for "restricted" PDFs)
            if not reader.decrypt(""):
                raise PdfSnipError("שגיאה: הקובץ מוגן בסיסמה.")
        total = len(reader.pages)
    except PdfReadError as e:
        raise PdfSnipError(f"שגיאה: לא ניתן לקרוא את קובץ ה-PDF ({e}).")

    pages = parse_page_range(page_range, total)

    if output_path is None:
        safe_range = page_range.replace(",", "_").replace(" ", "")
        output_path = input_path.with_name(f"{safe_range}_{input_path.name}")
    elif output_path.suffix.lower() != ".pdf":
        output_path = output_path.with_suffix(".pdf")

    if output_path.resolve() == input_path.resolve():
        raise PdfSnipError("שגיאה: קובץ הפלט לא יכול להיות זהה לקובץ הקלט.")

    try:
        _write_pages(reader, pages, output_path, strip_annots=False)
    except RecursionError:
        # Fallback: the deep structure usually comes from annotations (links,
        # comments). Retry without them - the page content itself is kept.
        try:
            reader = PdfReader(input_path)
            if reader.is_encrypted:
                reader.decrypt("")
            _write_pages(reader, pages, output_path, strip_annots=True)
        except RecursionError:
            output_path.unlink(missing_ok=True)
            raise PdfSnipError("שגיאה: מבנה הקובץ מורכב מדי ולא ניתן לחתוך אותו.")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="חיתוך עמודים מקובץ PDF לקובץ PDF חדש",
    )
    parser.add_argument("input", nargs="?", help="נתיב לקובץ ה-PDF")
    parser.add_argument("pages", nargs="?", help='טווח עמודים, למשל "3-7" או "1,3,5-8"')
    parser.add_argument("-o", "--output", help="נתיב לקובץ הפלט (אופציונלי)")
    args = parser.parse_args()

    # No arguments at all -> open the graphical interface
    if not args.input and not args.pages:
        from pdf_snip_gui import main as gui_main
        gui_main()
        return 0

    # Partial arguments -> ask for the missing ones in the terminal
    input_str = args.input or input("הכנס נתיב לקובץ PDF: ").strip().strip('"')
    pages_str = args.pages or input('הכנס טווח עמודים (למשל 3-7 או 1,3,5-8): ').strip()

    try:
        out = snip_pdf(
            Path(input_str),
            pages_str,
            Path(args.output) if args.output else None,
        )
    except PdfSnipError as e:
        print(e, file=sys.stderr)
        return 1

    print(f"הקובץ נוצר בהצלחה: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
