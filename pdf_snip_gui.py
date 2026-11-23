"""
Graphical interface for the PDF Pages Snipping Tool.

Usage:
    python pdf_snip_gui.py
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pypdf import PdfReader

from pdf_snip import PdfSnipError, snip_pdf, validate_pdf


class PdfSnipApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("חיתוך עמודים מ-PDF")
        self.resizable(False, False)

        self.input_var = tk.StringVar()
        self.pages_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.info_var = tk.StringVar(value="לא נבחר קובץ")

        frm = ttk.Frame(self, padding=15)
        frm.grid(sticky="nsew")

        # --- Input file ---
        ttk.Label(frm, text=":קובץ PDF").grid(row=0, column=2, sticky="e", pady=4)
        ttk.Entry(frm, textvariable=self.input_var, width=50, state="readonly").grid(
            row=0, column=1, padx=5
        )
        ttk.Button(frm, text="...בחר קובץ", command=self.choose_input).grid(row=0, column=0)

        ttk.Label(frm, textvariable=self.info_var, foreground="gray").grid(
            row=1, column=1, sticky="e"
        )

        # --- Page range ---
        ttk.Label(frm, text=":טווח עמודים").grid(row=2, column=2, sticky="e", pady=4)
        ttk.Entry(frm, textvariable=self.pages_var, width=50, justify="right").grid(
            row=2, column=1, padx=5
        )
        ttk.Label(frm, text="1,3,5-8 או 3-7 :לדוגמה", foreground="gray").grid(
            row=3, column=1, sticky="e"
        )

        # --- Output file (optional) ---
        ttk.Label(frm, text=":קובץ פלט").grid(row=4, column=2, sticky="e", pady=4)
        ttk.Entry(frm, textvariable=self.output_var, width=50).grid(row=4, column=1, padx=5)
        ttk.Button(frm, text="...שמור בשם", command=self.choose_output).grid(row=4, column=0)
        ttk.Label(
            frm, text="(אופציונלי - ברירת מחדל: טווח_שם-הקובץ.pdf)", foreground="gray"
        ).grid(row=5, column=1, sticky="e")

        # --- Action ---
        ttk.Button(frm, text="צור PDF", command=self.run).grid(
            row=6, column=0, columnspan=3, pady=(12, 0), ipadx=20
        )

    def choose_input(self) -> None:
        path = filedialog.askopenfilename(
            title="בחר קובץ PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            validate_pdf(Path(path))
            total = len(PdfReader(path).pages)
        except PdfSnipError as e:
            messagebox.showerror("שגיאה", str(e))
            return
        except Exception as e:  # unreadable/corrupt PDF
            messagebox.showerror("שגיאה", f"שגיאה: לא ניתן לקרוא את קובץ ה-PDF ({e}).")
            return
        self.input_var.set(path)
        self.info_var.set(f"מספר עמודים בקובץ: {total}")
        self.output_var.set("")

    def choose_output(self) -> None:
        initial = Path(self.input_var.get()) if self.input_var.get() else None
        path = filedialog.asksaveasfilename(
            title="שמור קובץ PDF",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialdir=str(initial.parent) if initial else None,
        )
        if path:
            self.output_var.set(path)

    def run(self) -> None:
        if not self.input_var.get():
            messagebox.showerror("שגיאה", "שגיאה: יש לבחור קובץ PDF.")
            return
        if not self.pages_var.get().strip():
            messagebox.showerror("שגיאה", "שגיאה: יש להזין טווח עמודים.")
            return
        output = self.output_var.get().strip()
        try:
            out = snip_pdf(
                Path(self.input_var.get()),
                self.pages_var.get(),
                Path(output) if output else None,
            )
        except PdfSnipError as e:
            messagebox.showerror("שגיאה", str(e))
            return
        except Exception as e:
            messagebox.showerror("שגיאה", f"שגיאה לא צפויה: {e}")
            return
        messagebox.showinfo("הצלחה", f"הקובץ נוצר בהצלחה:\n{out}")


def main() -> None:
    PdfSnipApp().mainloop()


if __name__ == "__main__":
    main()
