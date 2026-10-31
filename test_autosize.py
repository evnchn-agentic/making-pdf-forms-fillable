"""Self-check for verify()'s auto-size (0 Tf) check.  Run:  python test_autosize.py

PyMuPDF keeps /DA on the field dict (the widget's /Parent), not on the widget,
so a check that reads only the widget never sees auto-size.
"""
import os, tempfile
import pymupdf as fitz
import pdf_form_tools as t

tmp = tempfile.mkdtemp()


def build(name, fs, autosize=False, field_da=None):
    doc = fitz.open()
    doc.new_page()
    w = t.text_field(doc, 0, name, (50, 50, 300, 80), fs=fs, allow_autosize=autosize)
    if field_da is not None:
        parent = int(doc.xref_get_key(w, "Parent")[1].split()[0])
        doc.xref_set_key(parent, "DA", field_da)
    fn = os.path.join(tmp, f"{name}.pdf")
    doc.save(fn)
    return fn


def autosize_flags(fn):
    return [p for p in t.verify(fn) if "auto-size" in p]


# Auto-size inherited from the field dict must be flagged.
fn = build("auto", 0, autosize=True)
assert autosize_flags(fn), "fs=0 field: auto-size not flagged"

# Fixed sizes must stay clean, including a decimal one ("20.0 Tf" ends in "0 Tf").
assert not autosize_flags(build("fixed10", 10)), "fs=10 flagged as auto-size"
assert not autosize_flags(build("fixed20", 20)), "fs=20 flagged as auto-size"
fn = build("dec20", 20, field_da="(0 0 0 rg /Helv 20.0 Tf)")
assert not autosize_flags(fn), "fs=20.0 flagged as auto-size"

# A decimal zero is still auto-size ("0.0 Tf", ".0 Tf").
assert autosize_flags(build("dec0", 0, autosize=True, field_da="(0 0 0 rg /Helv 0.0 Tf)")), \
    "fs=0.0 not flagged as auto-size"
assert autosize_flags(build("dotzero", 0, autosize=True, field_da="(0 0 0 rg /Helv .0 Tf)")), \
    "fs=.0 not flagged as auto-size"

print("test_autosize: all passed")
