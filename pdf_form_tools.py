#!/usr/bin/env python3
"""Helpers for building and verifying AcroForm fillable PDFs.

Deps:  pip install "pymupdf>=1.24" "pypdf>=4"
Note:  PyMuPDF is AGPL-3.0. This skill is MIT, but your use of PyMuPDF is not.

Build with PyMuPDF, verify with pypdf — a different library is what catches
malformed structure (see SKILL.md).

CLI:
    python pdf_form_tools.py probe   form.pdf          # what fields exist, if any
    python pdf_form_tools.py geom    form.pdf 0        # words + rules on page 0, to place fields
    python pdf_form_tools.py render  form.pdf out      # render every page to out_pN.png
    python pdf_form_tools.py verify  form.pdf          # second-library structural check
"""
import sys, re

try:
    import pymupdf as fitz          # preferred: the `fitz` alias collides with an
except ImportError:                  # unrelated PyPI package named `fitz`
    import fitz

TINT = (0.898, 0.937, 1.0)  # light blue: users must be able to SEE the blanks


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------
def text_field(doc, pi, name, rect, fs=10, multiline=False, tip=None,
               align=0, maxlen=0, fill=TINT, allow_autosize=False):
    """A text field. Pass an explicit font size.

    fs=0 (auto-size) is refused by default. It is not merely ugly (a single
    digit balloons to fill a tall cell) — with text mixing CJK and Latin,
    PyMuPDF emits a degenerate text matrix and the field renders COMPLETELY
    BLANK, single-line and multiline alike. Pass allow_autosize=True only for
    a field you know will never receive CJK.
    """
    if fs == 0 and not allow_autosize:
        raise ValueError(
            "auto-size (fs=0) renders BLANK for mixed CJK+Latin text and balloons "
            "in tall cells; pass an explicit fs, or allow_autosize=True if this "
            "field can never receive CJK")
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_name = name
    w.rect = fitz.Rect(*rect)
    w.text_font, w.text_fontsize = "Helv", fs
    w.fill_color, w.border_width = fill, 0
    w.text_align = align
    if maxlen:
        w.text_maxlen = maxlen
    if multiline:
        w.field_flags = fitz.PDF_TX_FIELD_IS_MULTILINE
    if tip:
        w.field_label = tip          # encodes UTF-16BE properly; safe for CJK
    return doc[pi].add_widget(w).xref


def checkbox(doc, pi, name, rect, tip=None, fill=TINT):
    w = fitz.Widget()
    w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.field_name = name
    w.rect = fitz.Rect(*rect)
    w.fill_color, w.border_width, w.field_value = fill, 0, False
    if tip:
        w.field_label = tip
    return doc[pi].add_widget(w).xref


def box(x0, y0, size=7.9):
    """Widget rect for a printed checkbox glyph at (x0, y0) from geom()'s words.

    Size the rect to the GLYPH, not the row. A rect as tall as the table row
    looks fine empty, then the selected dot is drawn centred in that rect and
    lands on top of the neighbouring label text.
    """
    return (x0 - 0.4, y0 + 0.4, x0 + size, y0 + size + 0.8)


def radio_group(doc, pi, name, options, tip=None, fill=TINT):
    """A REAL radio group: picking one clears the others. Returns parent xref.

    options: [("Yes", rect), ("No", rect), ...]   — build rects with box()

    PyMuPDF cannot do this itself. Giving two widgets the same field_name
    produces two top-level fields that BOTH use on-state /Yes, so they toggle
    together. The fix is the PDF-spec shape: one parent field holding /Kids,
    each kid with its own on-state, and the kids stripped of field-level keys
    so they are pure widgets.

    Export values are PDF names and the machine-readable answer, so they are
    limited to ASCII letters, digits and _ . - ; put the human label (CJK
    included) in the printed text or the tooltip.
    """
    kids, tmp = [], doc.xref_length()
    for i, (export, rect) in enumerate(options):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", export):
            raise ValueError(f"radio export {export!r}: use only ASCII letters, digits "
                             f"and _ . - (it becomes a PDF name)")
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
        w.field_name = f"__rg{tmp}_{i}"   # temporary and ASCII-only, stripped below
        w.rect = fitz.Rect(*rect)
        w.fill_color, w.border_width, w.field_value = fill, 0, False
        kids.append((doc[pi].add_widget(w).xref, export))

    for xref, export in kids:
        # PyMuPDF <2 names the on-state /Yes; 2.0 names it after field_value
        # (/False here). Every kid gets the SAME one either way, so find it.
        on = on_states(doc, xref)
        if len(on) != 1:
            raise RuntimeError(f"radio kid {xref}: expected one on-state, got {on}")
        if on[0] != export:
            doc.xref_set_key(xref, f"AP/N/{export}", doc.xref_get_key(xref, f"AP/N/{on[0]}")[1])
            # Same trap as /T below: this writes `/Yes null`, it does NOT remove
            # the key. A stale on-state left in /AP/N breaks exclusivity and
            # fools any code that substring-matches the dict. Strip it for real.
            doc.xref_set_key(xref, f"AP/N/{on[0]}", "null")
            o = doc.xref_object(xref, compressed=True)
            doc.update_object(xref, re.sub(rf"/{on[0]}\s+null", "", o))
        doc.xref_set_key(xref, "AS", "/Off")

    # Build the parent with xref_set_key rather than string interpolation:
    # a name or tooltip containing "(", ")" or non-ASCII would otherwise corrupt
    # the object (mojibake) or break the PDF syntax outright.
    parent = doc.get_new_xref()
    doc.update_object(parent, "<</FT/Btn/Ff 49152/V/Off/DA(0 0 0 rg /ZaDb 0 Tf)>>")
    doc.xref_set_key(parent, "T", pdf_text_string(name))
    if tip:
        doc.xref_set_key(parent, "TU", pdf_text_string(tip))
    doc.xref_set_key(parent, "Kids", "[" + " ".join(f"{x} 0 R" for x, _ in kids) + "]")

    for xref, _ in kids:
        doc.xref_set_key(xref, "Parent", f"{parent} 0 R")
        # xref_set_key(..., "null") writes `/T null`, it does NOT remove the
        # key — a null /T makes the kid a broken field. Rewrite the object.
        # /V is written by PyMuPDF as the STRING (Off), not a name, so the
        # name-only pattern misses it and a field-level /V shadows the parent's.
        o = doc.xref_object(xref, compressed=True)
        o = re.sub(r"/T\s*\([^)]*\)", "", o)
        o = re.sub(r"/V\s*(/\w+|\([^)]*\))", "", o)
        o = re.sub(r"/Ff\s*\d+", "", o)
        o = re.sub(r"/DA\s*\([^)]*\)", "", o)
        doc.update_object(xref, o)
    return parent


def on_states(doc, xref):
    """A button widget's on-state names: the keys of /AP/N other than /Off.
    Parses real names (substring-matching the dict is fooled by a stale
    `/Yes null`) and follows an indirect /AP/N."""
    ap = doc.xref_get_key(xref, "AP/N")
    if ap[0] == "xref":
        ap = ("dict", doc.xref_object(int(ap[1].split()[0]), compressed=True))
    if ap[0] != "dict":
        return []
    return [s for s in re.findall(r"/([^\s/<>\[\]()%{}]+)\s*\d+ 0 R", ap[1]) if s != "Off"]


def pdf_text_string(s):
    """A PDF text string literal: ASCII stays literal, anything else becomes
    UTF-16BE hex. Needed because raw non-ASCII interpolated into object source
    is read back as mojibake."""
    if all(ord(c) < 128 for c in s):
        return "(" + s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)") + ")"
    return "<FEFF" + s.encode("utf-16-be").hex().upper() + ">"


def finalize_acroform(doc, field_xrefs):
    """Wire up the AcroForm dict. NeedAppearances tells the VIEWER to
    regenerate appearance streams from /DA + /DR — which is what lets a user
    type CJK into a Helvetica field and actually see it.

    Consequence worth knowing: a conforming viewer then DISCARDS the appearance
    streams PyMuPDF generated. Anything you see in a locally-rendered PNG is
    PyMuPDF's rendering, not the viewer's. See SKILL.md 'What the render can
    and cannot prove'.

    Note: this REPLACES any existing /AcroForm, orphaning pre-existing fields.
    Fine for a flat PDF; don't call it blindly on a form that already has one.
    """
    helv = doc.get_new_xref()
    doc.update_object(helv, "<</Type/Font/Subtype/Type1/BaseFont/Helvetica"
                            "/Encoding/WinAnsiEncoding>>")
    zadb = doc.get_new_xref()
    doc.update_object(zadb, "<</Type/Font/Subtype/Type1/BaseFont/ZapfDingbats>>")
    acro = doc.get_new_xref()
    doc.update_object(acro,
        "<</Fields[%s]/NeedAppearances true/DA(/Helv 0 Tf 0 g)"
        "/DR<</Font<</Helv %i 0 R/ZaDb %i 0 R>>>>>>"
        % (" ".join(f"{x} 0 R" for x in field_xrefs), helv, zadb))
    doc.xref_set_key(doc.pdf_catalog(), "AcroForm", f"{acro} 0 R")
    return acro


# --------------------------------------------------------------------------
# Inspecting / verifying
# --------------------------------------------------------------------------
def probe(path):
    """Field inventory. 0 fields = flat PDF, everything must be built."""
    from pypdf import PdfReader
    r = PdfReader(path)
    f = r.get_fields() or {}
    print(f"{path}\n  pages={len(r.pages)}  fields={len(f)}")
    for k, v in f.items():
        st = v.get("/_States_")
        print(f"  [{v.get('/FT')}] {k}" + (f" states={st}" if st else ""))
    return f


def geom(path, pi):
    """Word bboxes + vector rules — the grid to place fields against.

    These are PDF points, the same space as fitz.Rect, so a word bbox can be
    used directly to position a field. (render() output is NOT: see its note.)

    CJK line bboxes are inflated by ascent/descent and overlap their
    neighbours, which is why this prints WORD boxes.
    """
    d = fitz.open(path)
    p = d[pi]
    print(f"--- page {pi+1} {p.rect} words ---")
    for w in p.get_text("words"):
        print(f"  ({w[0]:6.1f},{w[1]:6.1f})-({w[2]:6.1f},{w[3]:6.1f}) {w[4]}")
    print("--- rules / boxes ---")
    for dr in p.get_drawings():
        r = dr["rect"]
        if r.width < 3 and r.height < 3:
            continue
        print(f"  {dr['type']} ({r.x0:6.1f},{r.y0:6.1f})-({r.x1:6.1f},{r.y1:6.1f})")


def render(path, prefix, pages=None, dpi=72):
    """Render pages to PNG. dpi=72 means 1px == 1pt, so pixel coordinates you
    measure in the image are directly usable as field rects. At any other dpi
    multiply by 72/dpi first — mixing the two silently misplaces every field."""
    d = fitz.open(path)
    out = []
    for i in (pages if pages is not None else range(len(d))):
        fn = f"{prefix}_p{i+1}.png"
        d[i].get_pixmap(dpi=dpi).save(fn)
        out.append(fn)
    scale = dpi / 72
    print("\n".join(out) + f"\n  (dpi={dpi}, {scale:g}px per pt"
          + ("" if scale == 1 else f"; multiply pixel coords by {72/dpi:.4g} for points)"))
    return out


def fill_and_render(path, values, radios, prefix, dpi=72):
    """Fill with realistic data — long strings and CJK if the form is bilingual
    — then LOOK at every page. Catches misplaced fields, ballooned type,
    overflow and clipping.

    values: {field_name: str or True}   radios: {group_name: export_value}
    e.g.   fill_and_render("f.pdf", {"name": "陳大文 CHAN Tai Man",
                                     "agree": True}, {"married": "Yes"}, "out")

    Read the limits in SKILL.md before trusting a clean result: this renders
    PyMuPDF's appearance streams, and a viewer honouring NeedAppearances builds
    its own. It proves geometry, not font behaviour.
    """
    d = fitz.open(path)
    for pg in d:
        for w in pg.widgets():
            if w.field_name in values:
                w.field_value = values[w.field_name]
                w.update()
    for name, val in radios.items():
        for pg in d:
            for w in pg.widgets():
                par = d.xref_get_key(w.xref, "Parent")
                if par[0] != "xref":
                    continue
                px = int(par[1].split()[0])
                if d.xref_get_key(px, "T")[1].strip("()") != name:
                    continue
                d.xref_set_key(px, "V", "/" + val)
                d.xref_set_key(w.xref, "AS",
                               "/" + val if val in on_states(d, w.xref) else "/Off")
    tmp = f"{prefix}_filled.pdf"
    d.save(tmp, garbage=3, deflate=True)
    return render(tmp, prefix, dpi=dpi)


def verify(path):
    """Structural check with the OTHER library, plus a widget-level walk.

    Never raises on a malformed or flat input — the files you most need to
    inspect are the broken ones.
    """
    from pypdf import PdfReader
    problems, f = [], {}
    r = PdfReader(path)
    acro = r.trailer["/Root"].get("/AcroForm")
    if acro is None:
        print(f"{path}\n  no /AcroForm — this is a FLAT pdf, there is nothing to verify")
        return ["no /AcroForm (flat pdf)"]
    try:
        f = r.get_fields() or {}
    except Exception as e:
        # A crash here is itself a finding: malformed field structure, e.g. a
        # `/T null` left by a failed key deletion. Keep going — the widget walk
        # below runs on the raw objects and will localise it.
        problems.append(f"pypdf could not parse the field tree: {type(e).__name__}: {e}")
    if not f and not problems:
        problems.append("/AcroForm present but no fields")
    if not acro.get("/NeedAppearances"):
        problems.append("NeedAppearances not set (CJK input may render blank)")
    fonts = list((acro.get("/DR") or {}).get("/Font", {}).keys())
    for need in ("/Helv", "/ZaDb"):
        if need not in fonts:
            problems.append(f"{need} missing from /DR fonts")

    # Widget-level walk. pypdf's field view CANNOT see these: malformed radio
    # widgets and duplicate names collapse into one field entry, so the
    # headline footguns are invisible at field level.
    doc = fitz.open(path)
    toplevel, names, radio_on = {}, {}, {}
    for pg in doc:
        for w in pg.widgets():
            src = doc.xref_object(w.xref, compressed=True)
            ap = doc.xref_get_key(w.xref, "AP/N")
            if ap[0] != "null" and "null" in ap[1]:
                problems.append(f"{w.field_name or '<kid>'}: stale null in /AP/N {ap[1]}")
            # NOTE: xref_get_key returns ('null','null') for an ABSENT key, which
            # is the correct state for a radio kid. Only the object source can
            # distinguish that from a literal `/T null` left by a failed deletion.
            if re.search(r"/T\s+null", src):
                problems.append(f"widget {w.xref}: /T is null — a failed key deletion, "
                                f"not a removal (see SKILL.md)")
            has_parent = doc.xref_get_key(w.xref, "Parent")[0] == "xref"
            if has_parent and re.search(r"/V\s*(/\w+|\([^)]*\))", src):
                problems.append(f"widget {w.xref}: kid carries its own /V, which shadows "
                                f"the parent's value")
            # /DA is inheritable: PyMuPDF writes it on the field dict (the
            # widget's /Parent), so read the widget first, then the parent.
            da = doc.xref_get_key(w.xref, "DA")
            if da[0] == "null":
                da = doc.xref_get_key(w.xref, "Parent/DA")
            # Only a TEXT field. `0 Tf` on a checkbox/radio is the normal
            # convention — the ZapfDingbats mark scales to the box.
            # (?<![\d.]) so a decimal size like "20.0 Tf" is not read as auto.
            if (w.field_type_string == "Text"
                    and da[0] != "null" and re.search(r"(?<![\d.])0\s+Tf", da[1])):
                problems.append(f"{w.field_name or w.xref}: auto-size (0 Tf) — renders blank "
                                f"for mixed CJK+Latin, balloons in tall cells")
            ff = doc.xref_get_key(w.xref, "Ff")   # may be an indirect ref
            is_radio = ff[0] == "int" and (int(ff[1]) & 32768)
            t = doc.xref_get_key(w.xref, "T")
            pff = doc.xref_get_key(w.xref, "Parent/Ff")
            pff = int(pff[1]) if pff[0] == "int" else 0
            eff = int(ff[1]) if ff[0] == "int" else pff   # /Ff is inheritable
            if has_parent and pff & 32768 and eff & 32768:
                px = doc.xref_get_key(w.xref, "Parent")[1]
                if t[0] != "null":
                    problems.append(f"widget {w.xref}: radio kid of {w.field_name} carries its "
                                    f"own /T — it becomes a separate field, not an option")
                # RadiosInUnison (bit 26): kids sharing an on-state is intended.
                g = radio_on.setdefault(px, [w.field_name, pff & (1 << 25), []])
                g[2].append(on_states(doc, w.xref))
            if not has_parent and t[0] != "null":
                names.setdefault(t[1], []).append(w.xref)
            if is_radio and not has_parent:
                toplevel.setdefault(t[1], []).append(w.xref)
    for name, xrefs in toplevel.items():
        if len(xrefs) > 1:
            problems.append(
                f"{name.strip('()')}: {len(xrefs)} radio widgets share a field name at TOP level "
                f"(no /Kids parent) — they will toggle together. Use radio_group().")
    for name, unison, ons in radio_on.values():
        flat = [s for o in ons for s in o]
        if any(len(o) != 1 for o in ons) or (not unison and len(set(flat)) < len(flat)):
            problems.append(f"{name}: radio kids' on-states are {ons} — each needs exactly one, "
                            f"all different, or the options toggle together")
    for name, xrefs in names.items():
        if len(xrefs) > 1 and name not in toplevel:
            problems.append(f"{name.strip('()')}: {len(xrefs)} top-level widgets share this "
                            f"field name — they will mirror each other's values")

    print(f"{path}\n  fields={len(f)}  DR fonts={fonts}")
    print("  PROBLEMS:\n    " + "\n    ".join(problems) if problems
          else "  no structural problems")
    return problems


def _usage():
    print(__doc__)
    sys.exit(2)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        _usage()
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "probe":
        probe(path)
    elif cmd == "geom":
        geom(path, int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    elif cmd == "render":
        if len(sys.argv) < 4:
            _usage()
        render(path, sys.argv[3])
    elif cmd == "verify":
        verify(path)
    else:
        _usage()
