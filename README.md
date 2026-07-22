# making-pdf-forms-fillable

A [Claude Code](https://claude.com/claude-code) skill: turn a flat, non-fillable PDF into a proper AcroForm — and prove the result isn't **silently** broken.

See [`SKILL.md`](SKILL.md) for the actual behaviour, and [`pdf_form_tools.py`](pdf_form_tools.py) for the probe / build / verify helpers.

## The idea

Adding form fields to a PDF is easy. Adding fields that survive contact with a real user is not — because the failure modes are silent. The library saves without error, the field count looks right, and the form looks correct until someone types Chinese into it, or prints it, or clicks "Yes" and watches "No" light up too.

Two checks catch different halves of that, and the skill insists on both:

- **`verify()`** — structural defects that no render can show you (malformed radio groups, duplicate field names, auto-size).
- **Fill every field with realistic data and look at the rendered pages** — geometry defects no structural check can show you (overflow, clipping, misplacement, ballooned type).

Each one has, in practice, passed a form that the other caught.

## What it catches

| Footgun | Symptom |
|---|---|
| Radio groups built the obvious way are malformed | Clicking Yes also selects No |
| Auto font size + text mixing CJK and Latin | Field has a value and an appearance stream, and draws **nothing** — single-line and multiline alike |
| Auto font size in a tall table cell | A single digit renders 30pt tall |
| Missing `NeedAppearances` / `/DR` fonts | User types Chinese, sees nothing |
| CJK line bboxes inflated by ascent/descent | Fields land on top of printed labels |
| A filled rect's extent ≠ the visible cell | Field overruns into the next section's header |
| Fixed size + mixed CJK/Latin overflowing the field width | Text renders *outside* the box, into the row below. A bigger box does not fix it |
| Checkbox rects sized to the row, not the glyph | Looks fine empty; the selected dot lands on the neighbouring label |

Every one was burned in practice rather than theorised. The skill is also explicit about what its own verification **cannot** prove: with `NeedAppearances` set, a conforming viewer discards the embedded appearance streams and rebuilds them, so a locally-rendered PNG shows this library's font handling and not the viewer's. For a bilingual form, open it in a real viewer before calling it done.

## Scope

For **building or auditing** form fields. Not for filling in an already-good form, not for cryptographic signatures (needs a certificate), and not for scanned raster pages with no text layer.

## Install

Python, plus:

```
pip install "pymupdf>=1.24" "pypdf>=4"
```

Note that **PyMuPDF is AGPL-3.0**. This skill is MIT; that dependency is not, which matters if you are shipping commercially.

## License

MIT © 2026 Evan Chan
