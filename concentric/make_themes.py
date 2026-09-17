"""Generate concentric/static/themes.css from Irina's vendored opencode themes.

    python -m concentric.make_themes [path/to/Irina/irina/cli/themes]

Irina's CLI wears any of opencode's built-in colour themes, vendored as JSON
under ``irina/cli/themes/``: a ``defs`` table of named colours and a ``theme``
table of semantic tokens, where each value is a hex, a ``defs`` reference, or a
``{dark, light}`` pair. That is pure data, so it can drive the dashboard too.

This reads those files and writes one CSS block per theme, mapping Irina's
semantic tokens onto the tokens waku's dashboard already reads. The output is
committed — the themes live in a sibling checkout, not in this repo — so the
generator is a one-off tool, not a build step. Re-run it when that checkout's
themes change.

Colour is the only thing this sets. Layout, spacing and motion stay in ui.css.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULT_SOURCE = Path(os.environ.get("IRINA_THEMES_DIR", "")) or None

# Irina's token -> the dashboard token it drives. The dashboard's names are
# waku's (tokens.css); the values are opencode's.
MAP = {
    "surface-bg": "background",
    "surface-paper": "backgroundPanel",
    "surface-raised": "backgroundElement",
    "text-ink": "text",
    "text-muted": "textMuted",
    "rule": "border",
    "rule-hard": "borderActive",
    "accent": "primary",
    "accent-fg": "primary",
    "ok": "success",
    "warn": "warning",
    "bad": "error",
}


def _expand(value: str) -> str | None:
    """A hex string, normalised to #rrggbb. None if it is not a colour."""
    if not isinstance(value, str) or not value.startswith("#"):
        return None
    body = value.lstrip("#").lower()
    if len(body) == 3:
        body = "".join(c * 2 for c in body)
    if len(body) == 8:
        body = body[:6]
    if len(body) != 6 or any(c not in "0123456789abcdef" for c in body):
        return None
    return "#" + body


def _resolve(value, defs: dict, mode: str, seen: frozenset = frozenset()):
    """Collapse a {dark, light} pair, then follow defs references to a hex."""
    if isinstance(value, dict):
        value = value.get(mode, value.get("dark", value.get("light")))
    if isinstance(value, str) and value not in defs:
        return _expand(value)
    if isinstance(value, str) and value in defs and value not in seen:
        return _resolve(defs[value], defs, mode, seen | {value})
    return None


def resolve_theme(data: dict, mode: str) -> dict[str, str]:
    defs = data.get("defs") or {}
    out: dict[str, str] = {}
    for token, source in MAP.items():
        colour = _resolve((data.get("theme") or {}).get(source), defs, mode)
        if colour:
            out[token] = colour
    return out


def _block(selector: str, tokens: dict[str, str],
           extras: dict[str, str] | None = None) -> list[str]:
    if not tokens and not extras:
        return []
    lines = [f"{selector} {{"]
    for name, value in tokens.items():
        lines.append(f"  --{name}: {value};")
    # The ones waku derives with color-mix, derived the same way here: a custom
    # property is substituted where it is DECLARED, so a theme that sets
    # --surface-bg does not recompute the greys declared in tokens.css. Each
    # theme has to carry its own.
    bg = tokens.get("surface-bg")
    ink = tokens.get("text-ink")
    accent = tokens.get("accent")
    if ink and bg:
        lines.append(f"  --surface-sunk: color-mix(in srgb, {ink} 12%, {bg});")
        lines.append(f"  --text-faint: color-mix(in srgb, {ink} 62%, {bg});")
        lines.append(f"  --scrollbar-thumb: color-mix(in srgb, {ink} 25%, transparent);")
        lines.append(f"  --accent-ink: {bg};")
    if accent and bg:
        lines.append(f"  --accent-hover: color-mix(in srgb, {accent} 88%, {ink or '#000000'});")
        lines.append(f"  --accent-active: color-mix(in srgb, {accent} 78%, {ink or '#000000'});")
        lines.append(f"  --chart-1: {accent};")
        for step, pct in ((2, 78), (3, 58), (4, 40), (5, 24)):
            lines.append(f"  --chart-{step}: color-mix(in srgb, {accent} {pct}%, {bg});")
    # A local theme's own shape and elevation, written out verbatim.
    for name, value in (extras or {}).items():
        lines.append(f"  --{name}: {value};")
    lines.append("}")
    return lines


def build(source: Path) -> str:
    """Every theme from `source` (the vendored opencode set) and from
    concentric/themes/ (ours). Local names win, so a theme can be corrected here
    without touching the vendored files."""
    local = Path(__file__).resolve().parent / "themes"
    files: dict[str, Path] = {}
    for folder in (source, local):
        if folder.is_dir():
            for path in sorted(folder.glob("*.json")):
                files[path.stem] = path      # the later folder wins on a name clash
    if not files:
        raise SystemExit(f"no theme JSON files under {source} or {local}")

    out = [
        "/* Irina's dashboard — the theme layer. GENERATED, do not edit by hand.",
        " *",
        " * Sources:",
        " *   - the opencode palettes Irina's CLI vendors (irina/cli/themes/*.json)",
        " *   - concentric/themes/*.json, this repository's own (Materio lives there)",
        " *",
        " * Regenerate with:",
        " *",
        " *     python -m concentric.make_themes <path to irina/cli/themes>",
        " *",
        " * Each block maps a theme's semantic tokens onto the tokens waku's",
        " * dashboard reads. Colour, plus anything a local theme puts in its",
        " * `irina` block (radius, shadows). The default — no data-irina-theme —",
        " * is waku's own palette.",
        " */",
        "",
    ]
    names = []
    for name, path in sorted(files.items()):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        extras = {k: v for k, v in (data.get("irina") or {}).items()
                  if not k.startswith("_")}
        for mode, selector in (
            ("dark", f'[data-irina-theme="{name}"]'),
            ("light", f'[data-theme="light"][data-irina-theme="{name}"]'),
        ):
            out += _block(selector, resolve_theme(data, mode), extras)
            out.append("")
        names.append(name)

    out += [
        "/* The selector's options, so theme.js and this file cannot disagree. */",
        f":root {{ --irina-theme-count: {len(names)}; }}",
        "/* " + " ".join(names) + " */",
        "",
    ]
    return "\n".join(out)


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    if source is None or not source.is_dir():
        raise SystemExit(
            "point me at Irina's theme directory:\n"
            "  python -m concentric.make_themes <path to irina/cli/themes>"
        )
    out = Path(__file__).resolve().parents[1] / "concentric" / "static" / "themes.css"
    out.write_text(build(source), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes) from {source}")


if __name__ == "__main__":
    main()
