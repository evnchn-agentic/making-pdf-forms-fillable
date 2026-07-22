---
name: making-pdf-forms-fillable
description: Use when a PDF needs form fields — adding AcroForm text/checkbox/radio fields to a flat non-fillable PDF, auditing whether an existing PDF's fields are any good, fixing fields that print blank or clipped, or answering "is this PDF editable / can I type into it". Triggers on proposal forms, application forms, insurance/government/bank forms, scanned-looking PDFs, bilingual or CJK forms, "make this fillable", "add form fields", pypdf/PyMuPDF/fitz AcroForm work.
---

# Making PDF Forms Fillable

## Overview

Building an AcroForm is easy. Building one that is not **silently broken** is not.

**Core principle: every failure mode in this domain is silent.** The library saves without error, the field count looks right, and the form looks correct — until someone types Chinese into it, or prints it, or clicks "Yes" and watches "No" light up too. You cannot inspect your way to confidence here.

**So the rule is: fill every field with realistic data, render every page to an image, and look at it.** That is the entire skill. Everything below is the specific ways it goes wrong.

## When to Use

- A PDF has **zero** form fields and someone wants to type into it
- A PDF *has* fields but they're invisible, clip text, print blank, or don't cover every blank
- Any bilingual / CJK form (highest risk — see footguns 2 and 4)
- Someone asks "does this have good editable fields?"

**Not for:** filling out an already-good form (just set values), signing (needs a certificate), or OCR of a scanned raster page (no text layer = different problem).

## The Loop

1. **Probe.** Field count, and whether they're real. `get_fields()` returning 0 = flat PDF.
2. **Map the geometry.** Word bboxes + vector rules give you the grid. **Then render the page to PNG and look at it** — step 2 is not optional, see footgun 5.
3. **Build.** Text fields, checkboxes, radio groups (footgun 1).
4. **Parse with a *different* library than you built with.** Build with PyMuPDF → verify with pypdf. This is the check that catches malformed structure; PyMuPDF wrote radio fields that pypdf crashed on.
5. **Fill every field with realistic data — including CJK if the form is bilingual — render every page, and look.** Blank boxes and ballooned text only show up here.
6. Iterate 3–5 until every page looks like a form a human filled in.

## Footguns (all empirically burned, all silent)

| # | Footgun | Symptom | Fix |
|---|---|---|---|
| 1 | **PyMuPDF radio groups are malformed.** Two widgets sharing a `field_name` become two *top-level* fields both with on-state `Yes` | Clicking Yes also selects No. Some parsers crash | Hand-build a parent field with `/Kids` and distinct on-states. See `pdf_form_tools.py` |
| 2 | **multiline + CJK + auto font size (`0 Tf`) renders BLANK** | Field has a value, appearance stream exists, nothing is drawn | Never auto-size a multiline field. Fixed size only |
| 3 | **Auto font size balloons in tall cells** | A "8" in a table cell renders 30pt tall; form looks unprofessional | Fixed sizes matched to the form's own type (~9pt cells, 10–11pt fields) |
| 4 | **CJK input needs `/NeedAppearances true` + `/DR` fonts** | User types Chinese, sees nothing | Set both on the AcroForm dict |
| 5 | **CJK text line bboxes are inflated** by font ascent/descent — they overlap neighbouring lines | Fields placed from line bboxes cover printed labels | Use word-level bboxes, and confirm against a rendered PNG |
| 6 | **A filled rect's extent ≠ the visible cell** | Field overruns into the next section's header bar | Read the extent off the render, not the drawing list |

Also: **`xref_set_key(x, "T", "null")` writes `/T null`, it does not delete the key.** Rewrite the object string to actually remove it.

## What "Good" Means

Not just "has fields". A good form has:

- **Every** blank covered — including table rows and signature blocks
- **Radio groups** for Yes/No, not two independent checkboxes
- **A visible tint** (light blue fill, no border) so users can find the blanks
- **Consistent type sizes** matching the printed form
- **Tooltips** (`/TU`), bilingual if the form is
- **Descriptive field names** (`company_name`, not `Text1`)
- **No duplicate field names** — duplicates silently mirror each other's values

## Common Mistakes

- **Shipping on "it saved without error."** That is not evidence of anything.
- **Verifying with the library you built with.** It has the same blind spots.
- **Filling only one field to test.** The bugs are content-dependent — CJK, multiline, and long strings each break different things.
- **Overwriting the original.** Write to a new file; the flat original is the only clean source if you need to rebuild.
- Trusting auto font size because "it prevents clipping". It does, and it introduces footguns 2 and 3. Fixed sizes scroll on overflow, which is standard viewer behaviour and the lesser evil.

## Verification Checklist

- [ ] Second library parses it without error
- [ ] No duplicate field names
- [ ] Radio groups report distinct on-states (`['/Yes','/No']`, not `['/Off','/Yes']` twice)
- [ ] Filled render inspected for **every** page that has fields
- [ ] CJK sample text renders (if bilingual)
- [ ] `NeedAppearances` true, `/DR` has `/Helv` + `/ZaDb`
- [ ] Original file untouched

Tools: `pdf_form_tools.py` in this directory (probe, radio group builder, fill-and-render harness).
