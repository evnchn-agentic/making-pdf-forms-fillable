"""Self-check for verify()'s auto-size (0 Tf) check.  Run:  python test_autosize.py

PyMuPDF keeps /DA on the field dict (the widget's /Parent), not on the widget,
so a check that reads only the widget never sees auto-size.
"""
import os, re, tempfile
import pymupdf as fitz
import pdf_form_tools as t

tmp = tempfile.mkdtemp()


def build(name, fs, autosize=False, field_da=None):
    doc = fitz.open()
    doc.new_page()
    w = t.text_field(doc, 0, name, (50, 50, 300, 80), fs=fs, allow_autosize=autosize)
    if field_da is not None:
        target = w  # PyMuPDF 1.24 has no parent field for a text widget
        if doc.xref_get_key(w, "Parent")[0] == "xref":
            target = int(doc.xref_get_key(w, "Parent")[1].split()[0])
        doc.xref_set_key(target, "DA", field_da)
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

# /DA is inheritable: a field with none of its own takes its nearest ancestor's,
# else the AcroForm default. Auto-size reached that way is the same blank-CJK
# footgun, so it must be flagged too.
def build_inherit(name, acro_da, section_da=None, strip=True, depth=1,
                  dangling=False, indirect_da=None, near_da=None, acro_indirect=False):
    doc = fitz.open()
    doc.new_page()
    w = t.text_field(doc, 0, name, (50, 50, 300, 80), fs=10)
    field = w  # PyMuPDF 1.24 makes a text widget its own field; 2.x adds a parent
    if doc.xref_get_key(w, "Parent")[0] == "xref":
        field = int(doc.xref_get_key(w, "Parent")[1].split()[0])
    if strip:  # drop the DA PyMuPDF wrote, so only an ancestor or the AcroForm can supply one
        for x in (w, field):
            doc.update_object(x, re.sub(r"/DA\s*\([^)]*\)", "", doc.xref_object(x, compressed=True)))
    if indirect_da is not None:  # the widget's own DA, stored as an indirect string
        ind = doc.get_new_xref()
        doc.update_object(ind, indirect_da)
        doc.xref_set_key(w, "DA", f"{ind} 0 R")
    top = field
    if section_da is not None:  # `depth` non-terminal ancestors; the DA sits on the topmost
        for i in range(depth):
            node = doc.get_new_xref()
            doc.update_object(node, f"<</T(section{i})/Kids[{top} 0 R]>>")
            doc.xref_set_key(top, "Parent", f"{node} 0 R")
            if i == 0 and near_da is not None:  # a DA on the ancestor nearest the field
                doc.xref_set_key(node, "DA", near_da)
            top = node
        doc.xref_set_key(top, "DA", section_da)
    if dangling:  # the field's /Parent names an object that does not exist
        doc.xref_set_key(field, "Parent", "9999 0 R")
    t.finalize_acroform(doc, [top])
    acro = int(doc.xref_get_key(doc.pdf_catalog(), "AcroForm")[1].split()[0])
    if acro_indirect:  # the AcroForm default stored as an indirect string
        ind = doc.get_new_xref()
        doc.update_object(ind, acro_da)
        doc.xref_set_key(acro, "DA", f"{ind} 0 R")
    else:
        doc.xref_set_key(acro, "DA", acro_da)
        # Guard the harness itself: a quiet "not flagged" is only meaningful if the
        # AcroForm default really is the one we asked for.
        assert doc.xref_get_key(acro, "DA")[1] == acro_da.strip("()"), "harness did not set AcroForm /DA"
    fn = os.path.join(tmp, f"{name}.pdf")
    doc.save(fn)
    return fn


# Auto-size inherited from the AcroForm default must be flagged.
assert autosize_flags(build_inherit("inh_acro", "(/Helv 0 Tf 0 g)")), \
    "auto-size inherited from the AcroForm /DA not flagged"

# Auto-size inherited from a section two levels up must be flagged.
assert autosize_flags(build_inherit("inh_sect", "(/Helv 10 Tf 0 g)", section_da="(0 0 0 rg /Helv 0 Tf)")), \
    "auto-size inherited from an ancestor /DA not flagged"

# A fixed size reached by inheritance must stay clean.
assert not autosize_flags(build_inherit("inh_fixed", "(/Helv 10 Tf 0 g)")), \
    "fixed size inherited from the AcroForm flagged as auto-size"

# A field's own fixed DA overrides an auto-size AcroForm default.
assert not autosize_flags(build_inherit("own_fixed", "(/Helv 0 Tf 0 g)", strip=False)), \
    "field's own fixed DA overridden by an auto-size AcroForm default"

# A dangling /Parent must not make verify() raise; the AcroForm default then applies.
assert autosize_flags(build_inherit("dangle", "(/Helv 0 Tf 0 g)", dangling=True)), \
    "dangling /Parent: verify() raised or auto-size not flagged"

# An indirect /DA is dereferenced, so an auto-size string stored as an object is flagged.
assert autosize_flags(build_inherit("indir", "(/Helv 10 Tf 0 g)", indirect_da="(0 0 0 rg /Helv 0 Tf)")), \
    "indirect /DA auto-size not flagged"

# A fixed size 40 ancestors up is the effective DA; the walk must not stop short and fall back.
assert not autosize_flags(build_inherit("deep", "(/Helv 0 Tf 0 g)", section_da="(0 0 0 rg /Helv 10 Tf)", depth=40)), \
    "fixed size 40 ancestors up flagged: walk stopped before the real DA"

# An indirect AcroForm default is dereferenced: an auto-size string stored as an object is flagged.
assert autosize_flags(build_inherit("acro_ind", "(/Helv 0 Tf 0 g)", acro_indirect=True)), \
    "indirect AcroForm /DA auto-size not flagged"

# The nearest ancestor's DA wins over a farther one: an auto-size nearest DA over a fixed top must flag...
assert autosize_flags(build_inherit("near_auto", "(/Helv 10 Tf 0 g)", section_da="(0 0 0 rg /Helv 10 Tf)",
                                    depth=2, near_da="(0 0 0 rg /Helv 0 Tf)")), \
    "nearest auto-size DA overridden by a farther fixed DA"

# ...and a fixed nearest DA over an auto-size top must stay clean.
assert not autosize_flags(build_inherit("near_fixed", "(/Helv 0 Tf 0 g)", section_da="(0 0 0 rg /Helv 0 Tf)",
                                        depth=2, near_da="(0 0 0 rg /Helv 10 Tf)")), \
    "nearest fixed DA overridden by a farther auto-size DA"

# The helper itself, on in-memory documents: PyMuPDF raises on a saved /Parent cycle before this
# code runs, so the cycle and the null-parent cases are exercised directly here.
def helper_doc():
    doc = fitz.open()
    doc.new_page()
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm", "<</DA(/Helv 0 Tf 0 g)>>")
    return doc

doc = helper_doc()  # a /Parent cycle ends the walk and falls through to the AcroForm default
a, b = doc.get_new_xref(), doc.get_new_xref()
doc.update_object(a, f"<</Parent {b} 0 R>>")
doc.update_object(b, f"<</Parent {a} 0 R>>")
assert "0 Tf" in str(t._effective_da(doc, a)), "parent cycle: helper did not fall through to the AcroForm"

doc = helper_doc()  # a /Parent that resolves to a null object must not raise
n = doc.get_new_xref()
doc.update_object(n, "null")
w = doc.get_new_xref()
doc.update_object(w, f"<</Parent {n} 0 R>>")
assert "0 Tf" in str(t._effective_da(doc, w)), "null parent: helper raised or skipped the AcroForm default"

# A widget's own auto-size DA wins over a fixed AcroForm default: the nearest /DA is the one that counts.
tmp = tempfile.mkdtemp()
doc = fitz.open()
doc.new_page()
w = t.text_field(doc, 0, "own_auto", (50, 50, 300, 80), fs=10, allow_autosize=True)
doc.xref_set_key(w, "DA", "(0 0 0 rg /Helv 0 Tf)")
t.finalize_acroform(doc, [w])
acro = int(doc.xref_get_key(doc.pdf_catalog(), "AcroForm")[1].split()[0])
doc.xref_set_key(acro, "DA", "(/Helv 10 Tf 0 g)")
fn = os.path.join(tmp, "own_auto.pdf")
doc.save(fn)
assert autosize_flags(fn), "widget's own auto-size DA overridden by a fixed AcroForm default"

print("test_autosize: all passed")
