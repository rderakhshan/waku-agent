"""Every copy of a mark must stay one drawing.

The dashboard paints a mark through a CSS mask, so its colour comes from the
page and one file is enough. A README cannot do that — GitHub gives an <img> no
way to read the page theme, and strips styling from a README's SVG — so the two
inks ship as two more files, picked by <picture>. Three files, one shape: that
is a drift waiting to happen the next time a mark is redrawn, and these tests
are what catches it.

Two marks are covered: Waku's, which the stock dashboard still wears, and
Irina's, which is the one this project's README shows.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "docs" / "brand"

# master file -> the README variants of it, and the ink each one paints itself.
FAMILIES = {
    ROOT / "waku" / "ops" / "static" / "waku-mark.svg": {
        "waku-mark-on-light.svg": "#161614",
        "waku-mark-on-dark.svg": "#C9CDD1",
    },
    ROOT / "concentric" / "static" / "irina-mark.svg": {
        "irina-mark-on-light.svg": "#161614",
        "irina-mark-on-dark.svg": "#C9CDD1",
    },
}


def _geometry(svg: str) -> str:
    """Just the outline — the first `d` attribute, with colour and layout stripped."""
    return re.search(r'\sd="([^"]+)"', svg).group(1)


def test_every_variant_draws_the_same_shape():
    for master, variants in FAMILIES.items():
        assert master.is_file(), f"missing master {master}"
        shape = _geometry(master.read_text(encoding="utf-8"))
        for name in variants:
            variant = BRAND / name
            assert variant.is_file(), f"missing {variant}"
            assert _geometry(variant.read_text(encoding="utf-8")) == shape, (
                f"{name} has drifted from {master.name} — regenerate it rather "
                "than editing it by hand"
            )


def test_each_variant_states_its_ink_outright():
    """A README SVG that inherits its colour renders as nothing on one theme."""
    for variants in FAMILIES.values():
        for name, ink in variants.items():
            svg = (BRAND / name).read_text(encoding="utf-8")
            assert f'fill="{ink}"' in svg, f"{name} should paint itself {ink}"
            assert "prefers-color-scheme" not in svg, (
                f"{name} must not rely on a media query — GitHub strips styling "
                "from README SVGs, and <picture> is what does the switching here"
            )


def test_the_readme_offers_both_inks_of_the_mark_it_shows():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert 'media="(prefers-color-scheme: dark)"' in readme
    for name in FAMILIES[ROOT / "concentric" / "static" / "irina-mark.svg"]:
        assert f"docs/brand/{name}" in readme, f"README never references {name}"
