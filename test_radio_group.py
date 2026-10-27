"""Self-check for radio_group() + verify().  Run:  python test_radio_group.py

Needs the same deps as pdf_form_tools.py. Run it against every PyMuPDF major
you support: 2.0 changed how radio on-states are named.
"""
import os, tempfile
import pymupdf as fitz
from pypdf import PdfReader
import pdf_form_tools as t

tmp = tempfile.mkdtemp()


def build(name, exports):
    doc = fitz.open()
    doc.new_page()
    p = t.radio_group(doc, 0, name, [(e, t.box(50 + 40 * i, 50)) for i, e in enumerate(exports)],
                      tip=name)
    t.finalize_acroform(doc, [p])
    fn = os.path.join(tmp, f"{len(os.listdir(tmp))}.pdf")
    doc.save(fn)
    return fn


for name, exports in [("married", ["Yes", "No"]), ("婚姻狀況", ["single", "married", "other"])]:
    fn = build(name, exports)
    fields = PdfReader(fn).get_fields()
    assert list(fields) == [name], f"{name}: pypdf sees {list(fields)}, want one field"
    assert sorted(fields[name]["/_States_"]) == sorted("/" + e for e in exports), fields
    assert t.verify(fn) == [], name

    # Picking one option must leave exactly that kid on.
    t.fill_and_render(fn, {}, {name: exports[1]}, fn[:-4])
    d = fitz.open(fn[:-4] + "_filled.pdf")
    on = [d.xref_get_key(w.xref, "AS")[1] for w in d[0].widgets()]
    assert on == ["/Off", "/" + exports[1]] + ["/Off"] * (len(exports) - 2), on

# verify() must catch kids that share an on-state (the toggle-together bug).
fn = build("q", ["A", "B"])
d = fitz.open(fn)
k1, k2 = [w.xref for w in d[0].widgets()]
d.update_object(k2, d.xref_object(k2, compressed=True).replace("/B ", "/A "))
d.save(fn + ".bad.pdf")
assert any("toggle together" in p for p in t.verify(fn + ".bad.pdf"))

for bad in ("Not sure", "男"):
    try:
        build("x", ["Yes", bad])
        raise AssertionError(f"export {bad!r} accepted")
    except ValueError:
        pass

print(f"OK  pymupdf {fitz.__version__}")
