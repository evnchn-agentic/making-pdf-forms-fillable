"""Self-check: every field built here reaches /AcroForm /Fields.  Run:  python test_field_tree.py

PyMuPDF 2.x (seen on 2.1) puts a text or checkbox field on a /Parent of the widget, so a
/Fields array of widget xrefs hides those fields from pypdf.
"""
import os, tempfile
import pymupdf as fitz
from pypdf import PdfReader
import pdf_form_tools as t

fn = os.path.join(tempfile.mkdtemp(), "f.pdf")
doc = fitz.open()
doc.new_page()
xs = [t.text_field(doc, 0, "name", (50, 50, 250, 70)),
      t.checkbox(doc, 0, "agree", t.box(50, 100)),
      t.radio_group(doc, 0, "sex", [("M", t.box(50, 150)), ("F", t.box(90, 150))])]
acro = t.finalize_acroform(doc, xs)
doc.save(fn)

assert sorted(PdfReader(fn).get_fields() or {}) == ["agree", "name", "sex"], PdfReader(fn).get_fields()
assert t.verify(fn) == []

t.fill_and_render(fn, {"name": "陳大文 CHAN Tai Man", "agree": True}, {"sex": "F"}, fn[:-4])
# lstrip: PyMuPDF 2.x writes a checkbox's field /V as the string (Yes), not the name /Yes
got = {k: v.get("/V").lstrip("/") for k, v in PdfReader(fn[:-4] + "_filled.pdf").get_fields().items()}
assert got == {"name": "陳大文 CHAN Tai Man", "agree": "Yes", "sex": "F"}, got

# verify() must flag a widget whose field is missing from /Fields.
d = fitz.open(fn)
d.xref_set_key(acro, "Fields", f"[{xs[2]} 0 R]")
d.save(fn + ".orphan.pdf")
assert sum("not in /AcroForm /Fields" in p for p in t.verify(fn + ".orphan.pdf")) == 2

print(f"OK  pymupdf {fitz.__version__}")
