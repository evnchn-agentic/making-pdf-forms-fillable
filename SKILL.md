---
name: making-pdf-forms-fillable
description: Use when a PDF needs form fields — adding AcroForm text/checkbox/radio fields to a flat non-fillable PDF, auditing whether an existing PDF's fields are any good, fixing fields that print blank or clipped, or answering "is this PDF editable / can I type into it". Triggers on proposal forms, application forms, insurance/government/bank forms, scanned-looking PDFs, bilingual or CJK forms, "make this fillable", "add form fields", pypdf/PyMuPDF/fitz AcroForm work.
---

# Making PDF Forms Fillable

## Overview

Building an AcroForm is easy. Building one that is not **silently broken** is not.

**Core principle: the failure modes here are silent.** The library saves without error, the field count looks right, and the form looks correct — until someone types Chinese into it, or prints it, or clicks "Yes" and watches "No" light up too.

So you need two checks that catch different things, and neither is optional:

1. **`verify()`** — structural defects (malformed radio groups, duplicate names, auto-size). Invisible in a render.
2. **Fill every field with realistic data and LOOK at the rendered pages** — geometry and layout (misplaced fields, overflow, clipping, ballooned type). Invisible to `verify()`.

A cold agent that stopped at `verify()`'s "no structural problems" shipped a form with two visible defects; the render caught both. A different form passed the render while carrying a structural defect. **Run both.**

## When to Use

- A PDF has **zero** form fields and someone wants to type into it
- A PDF *has* fields but they're invisible, clip text, print blank, or don't cover every blank
- Any bilingual / CJK form (highest risk — see footguns 2 and 7)
- Someone asks "does this have good editable fields?"

**Not for:** filling out an already-good form (just set values), cryptographic signing (needs a certificate — but a *text* field for a typed name and date is in scope, and a printed signature line stays a plain line), or OCR of a scanned raster page with no text layer.

## The Loop

1. **Probe.** `probe()` — `fields=0` means flat: everything must be built.
2. **Map the geometry.** `geom()` gives word bboxes and vector rules **in PDF points, the same space as `fitz.Rect`** — use those numbers directly. Then `render()` the page and look, because the drawing list lies about what a section visually occupies (footgun 6).
3. **Build.** `text_field` / `checkbox` / `radio_group`.
4. **`verify()`** — it parses with pypdf *and* walks the raw widgets. Structural defects only.
5. **`fill_and_render()`** with realistic data — long strings, and CJK if the form is bilingual — then **look at every page image**.
6. Iterate 3–5 until the form looks like one a human filled in.

**Coordinates:** `render()` defaults to `dpi=72`, where 1px == 1pt, so pixel positions measured in the PNG are directly usable as field rects. At any other dpi, multiply by `72/dpi` first — mixing the two silently misplaces every field.

## Footguns

All observed in practice. Numbers 2 and 7 share one root cause: **PyMuPDF's appearance generator mishandles text that mixes CJK with Latin.**

| # | Footgun | Symptom | Fix |
|---|---|---|---|
| 1 | **PyMuPDF radio groups are malformed.** Two widgets sharing a `field_name` become two *top-level* fields both with on-state `Yes` | Clicking Yes also selects No | `radio_group()` — builds the parent `/Kids` structure the spec requires |
| 2 | **Auto font size (`0 Tf`) + text mixing CJK and Latin → renders BLANK.** Degenerate text matrix (`0 0 0 0 … Tm`). **Single-line and multiline alike.** Pure-CJK and pure-ASCII happen to survive, which is exactly why it looks intermittent | Field has a value and an appearance stream, and draws nothing | Never auto-size a field that can receive CJK. `text_field` refuses `fs=0` unless you pass `allow_autosize=True` |
| 3 | **Auto font size balloons in tall cells** | A single digit renders 30pt tall | Fixed sizes matched to the form's own type (~9pt table cells, 10–11pt fields) |
| 4 | **CJK input needs `/NeedAppearances` + `/DR` fonts** | User types Chinese, sees nothing | `finalize_acroform()` sets both |
| 5 | **CJK text line bboxes are inflated** by ascent/descent and overlap neighbouring lines | Fields placed from line bboxes cover printed labels | Use `geom()` (word-level), confirm against a render |
| 6 | **A filled rect's extent ≠ the visible cell** | Field overruns into the next section's header bar | Read the extent off the render, not the drawing list |
| 7 | **Fixed size + mixed CJK/Latin that overflows the field WIDTH → text renders outside the box**, clipped against a window that doesn't track the box height | Long bilingual answer bleeds into the row below | Make the field **multiline**. Enlarging the box does *not* fix it |
| 8 | **Checkbox/radio rects sized to the row instead of the glyph** | Looks fine empty; the selected dot then lands on the neighbouring label | `box(x0, y0)` — size to the printed glyph |

Also: **`xref_set_key(x, k, "null")` writes `/k null`, it does not delete the key.** A `/T null` left on a radio kid makes it a broken field *and* crashes pypdf's field parser. Rewrite the object source to remove it.

## What the Render Can and Cannot Prove

Be honest about this or you will trust a green that means nothing.

- **It proves geometry:** placement, overflow, clipping, ballooned type, fields covering printed labels. This is real, and it catches footguns 3, 6, 7, 8.
- **It does NOT prove font behaviour in the user's viewer.** `NeedAppearances true` instructs conforming viewers to *discard* the embedded appearance streams and rebuild them from `/DA` + `/DR`. Your PNG shows PyMuPDF's appearance generator; Acrobat / Preview / Chrome each build their own.
- **Therefore:** for a bilingual form, open the result in at least one real viewer and type CJK into it before calling it done. Nothing local substitutes for that.

## What "Good" Means

Not just "has fields":

- **Every** blank covered — including table rows, and the typed-name/date part of a signature block
- **Radio groups** for Yes/No, not two independent checkboxes
- **A visible tint** (light blue fill, no border) so users can find the blanks
- **Consistent type sizes** matching the printed form
- **Tooltips** (`/TU`), bilingual if the form is
- **Descriptive field names** — `company_name`, `contact1_phone`; not `Text1`. Prefix grouped rows (`location2_address`) so a filled form is machine-readable
- **No duplicate field names** — duplicates silently mirror each other's values
- ~3pt padding inside table cells; start a field ~7pt after the label ends

## Common Mistakes

- **Shipping on "it saved without error."** That is not evidence of anything.
- **Stopping at `verify()` clean.** It cannot see layout. Render.
- **Stopping at a good-looking render.** It cannot see structure. Verify.
- **Verifying with the library you built with.** It has the same blind spots.
- **Filling only one field to test.** The bugs are content-dependent: CJK, mixed scripts, long strings and multiline each break something different. Fill everything.
- **Reaching for auto font size to prevent clipping.** It causes footguns 2 and 3. Use a fixed size, and multiline where content can run long.
- **Overwriting the original.** Write to a new file; the flat original is the only clean source if you need to rebuild.

## Verification Checklist

- [ ] `verify()` reports no structural problems (it never raises — a flat or malformed file is reported, not crashed on)
- [ ] Filled render inspected for **every** page that has fields
- [ ] CJK **and mixed CJK+Latin** sample text renders inside its box
- [ ] Radio groups: exactly one kid `/AS` set, siblings `/Off`
- [ ] Opened in a real viewer if the form is bilingual
- [ ] Original file untouched

## Tools

`pdf_form_tools.py` — `probe` · `geom` · `render` · `verify` on the CLI; `text_field` / `checkbox` / `radio_group` / `box` / `finalize_acroform` / `fill_and_render` as imports.

Requires `pymupdf` and `pypdf`. Note **PyMuPDF is AGPL-3.0** — this skill is MIT, but that dependency is not.
