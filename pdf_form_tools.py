#!/usr/bin/env python3
"""Helpers for building and verifying AcroForm fillable PDFs.

Deps:  uv pip install pymupdf pypdf
Build with PyMuPDF, verify with pypdf — a different library is what catches
malformed structure (see SKILL.md footgun 1).

CLI:
    python pdf_form_tools.py probe   form.pdf          # what fields exist, if any
    python pdf_form_tools.py geom    form.pdf 0        # words + rules on page 0, to place fields
    python pdf_form_tools.py render  form.pdf out      # render every page to out_pN.png
    python pdf_form_tools.py verify  form.pdf          # second-library structural check
"""
import sys, re
import fitz  # PyMuPDF

TINT = (0.898, 0.937, 1.0)  # light blue: users must be able to SEE the blanks


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------
def text_field(doc, pi, name, rect, fs=10, multiline=False, tip=None,
               align=0, maxlen=0, fill=TINT):
    """A text field.

    fs=0 (auto-size) is a TRAP: it renders BLANK for multiline+CJK and balloons
    in tall cells. Pass an explicit size. Match the form's printed type
    (~9pt table cells, 10-11pt normal fields).
    """
    if multiline and fs == 0:
        raise ValueError("auto-size on a multiline field renders blank with CJK; pass fs>0")
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
        w.field_label = tip
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


def radio_group(doc, pi, name, options, tip=None, fill=TINT):
    """A REAL radio group: picking one clears the others. Returns parent xref.

    options: [("Yes", rect), ("No", rect), ...]

    PyMuPDF cannot do this itself. Giving two widgets the same field_name
    produces two top-level fields that BOTH use on-state /Yes, so they toggle
    together and some parsers reject the file. The fix is the PDF-spec shape:
    one parent field holding /Kids, each kid with its own on-state, and the
    kids stripped of field-level keys so they are pure widgets.
    """
    kids = []
    for export, rect in options:
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_RADIOBUTTON
        w.field_name = f"{name}__{export}"   # temporary, stripped below
        w.rect = fitz.Rect(*rect)
        w.fill_color, w.border_width, w.field_value = fill, 0, False
        kids.append((doc[pi].add_widget(w).xref, export))

    for xref, export in kids:
        on = doc.xref_get_key(xref, "AP/N/Yes")   # PyMuPDF always names it /Yes
        if on[0] != "null" and export != "Yes":
            doc.xref_set_key(xref, f"AP/N/{export}", on[1])
            # Same trap as /T below: this writes `/Yes null`, it does NOT remove
            # the key. A stale on-state left in /AP/N breaks exclusivity and
            # fools any code that substring-matches the dict. Strip it for real.
            doc.xref_set_key(xref, "AP/N/Yes", "null")
            o = doc.xref_object(xref, compressed=True)
            doc.update_object(xref, re.sub(r"/Yes\s+null", "", o))
        doc.xref_set_key(xref, "AS", "/Off")

    parent = doc.get_new_xref()
    doc.update_object(parent,
        "<</FT/Btn/Ff 49152/T(%s)%s/V/Off/DA(0 0 0 rg /ZaDb 0 Tf)/Kids[%s]>>"
        % (name,
           f"/TU({tip})" if tip else "",
           " ".join(f"{x} 0 R" for x, _ in kids)))

    for xref, _ in kids:
        doc.xref_set_key(xref, "Parent", f"{parent} 0 R")
        # xref_set_key(..., "null") writes `/T null`, it does NOT remove the
        # key — a null /T makes the kid a broken field. Rewrite the object.
        o = doc.xref_object(xref, compressed=True)
        o = re.sub(r"/T\s*\([^)]*\)", "", o)
        o = re.sub(r"/V\s*/\w+", "", o)
        o = re.sub(r"/Ff\s*\d+", "", o)
        o = re.sub(r"/DA\s*\([^)]*\)", "", o)
        doc.update_object(xref, o)
    return parent


def finalize_acroform(doc, field_xrefs):
    """Wire up the AcroForm dict. NeedAppearances + /DR fonts are what let a
    viewer render text the DA font has no glyphs for — i.e. CJK input."""
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

    CJK line bboxes are inflated by ascent/descent and overlap their
    neighbours, so use these WORD boxes, then confirm against render().
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


def render(path, prefix, pages=None, dpi=110):
    d = fitz.open(path)
    out = []
    for i in (pages if pages is not None else range(len(d))):
        fn = f"{prefix}_p{i+1}.png"
        d[i].get_pixmap(dpi=dpi).save(fn)
        out.append(fn)
    print("\n".join(out))
    return out


def fill_and_render(path, values, radios, prefix, dpi=110):
    """THE verification step. Fill with realistic data — long strings and CJK
    if the form is bilingual — then LOOK at every page. Blank fields,
    ballooned type and misplaced boxes are only visible here.

    values: {field_name: str or True}   radios: {group_name: export_value}
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
                # Parse real on-state NAMES. Substring-matching the /AP/N dict
                # silently matches a stale `/Yes null` and marks the wrong kid.
                states = re.findall(r"/(\w+)\s+\d+ 0 R",
                                    d.xref_get_key(w.xref, "AP/N")[1])
                d.xref_set_key(w.xref, "AS",
                               "/" + val if val in states else "/Off")
    tmp = f"{prefix}_filled.pdf"
    d.save(tmp, garbage=3, deflate=True)
    return render(tmp, prefix, dpi=dpi)


def verify(path):
    """Structural check with the OTHER library. Catches what the builder missed."""
    from pypdf import PdfReader
    r = PdfReader(path)
    f = r.get_fields() or {}
    acro = r.trailer["/Root"]["/AcroForm"]
    problems = []
    if not f:
        problems.append("no fields at all")
    if not acro.get("/NeedAppearances"):
        problems.append("NeedAppearances not set (CJK input may render blank)")
    fonts = list(acro.get("/DR", {}).get("/Font", {}).keys())
    for need in ("/Helv", "/ZaDb"):
        if need not in fonts:
            problems.append(f"{need} missing from /DR fonts")
    for k, v in f.items():
        if v.get("/FT") == "/Btn":
            st = [s for s in (v.get("/_States_") or []) if s != "/Off"]
            if len(st) > 1 and len(set(st)) != len(st):
                problems.append(f"{k}: duplicate on-states {st}")
    # stale `/Yes null` left in a widget's /AP/N by a failed key deletion
    doc = fitz.open(path)
    for pg in doc:
        for w in pg.widgets():
            ap = doc.xref_get_key(w.xref, "AP/N")
            if ap[0] != "null" and "null" in ap[1]:
                problems.append(f"{w.field_name or '<kid>'}: stale null in /AP/N {ap[1]}")
    print(f"{path}\n  fields={len(f)}  DR fonts={fonts}")
    print("  PROBLEMS:\n    " + "\n    ".join(problems) if problems else "  no structural problems")
    return problems


if __name__ == "__main__":
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "probe":
        probe(path)
    elif cmd == "geom":
        geom(path, int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    elif cmd == "render":
        render(path, sys.argv[3])
    elif cmd == "verify":
        verify(path)
    else:
        sys.exit(__doc__)
