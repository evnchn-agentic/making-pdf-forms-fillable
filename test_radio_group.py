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

# ...and must stay quiet on valid forms other tools build.
def quiet(fn, *words):
    probs = t.verify(fn)
    assert not [p for p in probs if any(w in p for w in words)], (fn, probs)

fn = build("p", ["a-b", "c.d"])                          # punctuated exports
quiet(fn, "")
t.fill_and_render(fn, {}, {"p": "c.d"}, fn[:-4])
d = fitz.open(fn[:-4] + "_filled.pdf")
assert [d.xref_get_key(w.xref, "AS")[1] for w in d[0].widgets()] == ["/Off", "/c.d"]

d = fitz.open(build("ind", ["A", "B"]))                 # indirect /AP/N
for w in d[0].widgets():
    n = d.get_new_xref()
    d.update_object(n, d.xref_get_key(w.xref, "AP/N")[1])
    d.xref_set_key(w.xref, "AP/N", f"{n} 0 R")
d.save(fn + ".ind.pdf")
quiet(fn + ".ind.pdf", "")

d = fitz.open(build("u", ["A", "B"]))                   # RadiosInUnison
k1, k2 = [w.xref for w in d[0].widgets()]
d.update_object(k2, d.xref_object(k2, compressed=True).replace("/B ", "/A "))
d.xref_set_key(int(d.xref_get_key(k1, "Parent")[1].split()[0]), "Ff", str(49152 | 1 << 25))
d.save(fn + ".unison.pdf")
quiet(fn + ".unison.pdf", "toggle together")

d = fitz.open(); d.new_page()                           # section0.q / section1.q
groups = [t.radio_group(d, 0, "q", [(e, t.box(50 + 40 * i, 50 + 40 * j)) for i, e in enumerate("AB")])
          for j in range(2)]
secs = []
for j, g in enumerate(groups):
    s_ = d.get_new_xref()
    d.update_object(s_, f"<</T(section{j})/Kids[{g} 0 R]>>")
    d.xref_set_key(g, "Parent", f"{s_} 0 R")
    secs.append(s_)
t.finalize_acroform(d, secs)
d.save(fn + ".sections.pdf")
quiet(fn + ".sections.pdf", "toggle together")

d = fitz.open(); d.new_page()                           # checkbox fields under a Btn parent
cbs = [t.checkbox(d, 0, f"check{i}", t.box(50 + 40 * i, 50)) for i in range(2)]
par = d.get_new_xref()
d.update_object(par, "<</T(q)/FT/Btn/Ff 49152/Kids[%s]>>" % " ".join(f"{x} 0 R" for x in cbs))
for x in cbs:
    d.xref_set_key(x, "Parent", f"{par} 0 R")
    d.xref_set_key(x, "Ff", "0")
t.finalize_acroform(d, [par])
d.save(fn + ".nested.pdf")
quiet(fn + ".nested.pdf", "radio kid", "toggle together")

for bad in ("Not sure", "男"):
    try:
        build("x", ["Yes", bad])
        raise AssertionError(f"export {bad!r} accepted")
    except ValueError:
        pass

print(f"OK  pymupdf {fitz.__version__}")
