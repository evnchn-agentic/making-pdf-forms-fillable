# making-pdf-forms-fillable

A [Claude Code](https://claude.com/claude-code) skill: turn a flat, non-fillable PDF into a proper AcroForm — and prove the result isn't **silently** broken.

See [`SKILL.md`](SKILL.md) for the actual behaviour, and [`pdf_form_tools.py`](pdf_form_tools.py) for the probe / build / verify helpers.

## The idea

Adding form fields to a PDF is easy. Adding fields that survive contact with a real user is not — because **every failure mode here is silent**. The library saves without error, the field count looks right, and the form looks correct until someone types Chinese into it, or prints it, or clicks "Yes" and watches "No" light up too.

So the skill's one load-bearing rule is: **fill every field with realistic data, render every page to an image, and look at it.** No amount of inspecting the structure substitutes for that.

## What it catches

| Footgun | Symptom |
|---|---|
| Radio groups built the obvious way are malformed | Clicking Yes also selects No; some parsers reject the file |
| Multiline + CJK + auto font size | Field has a value and an appearance stream, and draws **nothing** |
| Auto font size in a tall table cell | A single digit renders 30pt tall |
| Missing `NeedAppearances` / `/DR` fonts | User types Chinese, sees nothing |
| CJK line bboxes inflated by ascent/descent | Fields land on top of printed labels |
| A filled rect's extent ≠ the visible cell | Field overruns into the next section's header |

Each was burned in practice, not theorised. The skill also insists you **verify with a different library than you built with** — the one that wrote the file shares its own blind spots, and in the session that produced this skill, the second library was what caught malformed radio structure the builder had happily emitted.

## Scope

For **building or auditing** form fields. Not for filling in an already-good form, not for digital signatures (needs a certificate), and not for scanned raster pages with no text layer.

Python, `pymupdf` + `pypdf`.

## License

MIT © 2026 Evan Chan
