"""Generate synthetic sample label images with known ground-truth verdicts.

These are drawn (not photographed), so every printed field is one we chose, which
means we know the exact lawful verdict for each label. That gives two independent
ground-truth checks:

  - A FREE deterministic test (tests/test_sample_labels.py) feeds each label's
    declared fields straight into the rule engine and asserts the verdict equals
    the manifest's "expected". This proves the answer key is correct per the real
    rules, with no model call.
  - A PAID live eval (evals/sample_eval.py) runs the rendered IMAGE through the
    real pipeline (vision read -> rules) and checks it reaches the same verdict.

Unlike the real bottle photos (copyrighted, local only), these are ours, so the
PNGs and the manifest are committed. Drop the folder into batch mode for a demo
with a believable PASS / FAIL / NEEDS REVIEW spread.

Regenerate with:

    python -m sample_labels.generate
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.rules.warning import CANONICAL

BASE = Path(__file__).parent
IMAGES = BASE / "images"
MANIFEST = BASE / "manifest.json"

# A warning whose wording is verbatim but whose required header is not in capital
# letters (title case). 27 CFR 16.22 requires "GOVERNMENT WARNING" in capitals, so
# this is a real FAIL even though every word is correct.
WARNING_TITLECASE_HEADER = CANONICAL.replace("GOVERNMENT WARNING", "Government Warning", 1)
# A warning read cleanly but with the wording altered: a genuine violation.
WARNING_GARBLED = CANONICAL.replace("health problems.", "health issues.")


# ---- field builders (full field dicts with legibility flags set true) ----

def _spirits(**over):
    f = dict(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        name_and_address="Bottled by Old Tom Distillery, Bardstown, KY",
        government_warning=CANONICAL,
        warning_legible=True,
        overall_legible=True,
    )
    f.update(over)
    return f


def _wine(**over):
    f = dict(
        brand_name="STONECREST CELLARS",
        class_type="Cabernet Sauvignon",
        alcohol_content="13.5% Alc./Vol.",
        net_contents="750 mL",
        name_and_address="Produced and bottled by Stonecrest Cellars, Napa, CA",
        government_warning=CANONICAL,
        appellation="Napa Valley",
        vintage="2019",
        grape_varietal="Cabernet Sauvignon",
        sulfite_statement="Contains Sulfites",
        warning_legible=True,
        overall_legible=True,
    )
    f.update(over)
    return f


def _beer(**over):
    f = dict(
        brand_name="RIVERBED BREWING",
        class_type="India Pale Ale",
        alcohol_content="6.5% Alc/Vol",
        net_contents="12 FL OZ",
        name_and_address="Brewed and bottled by Riverbed Brewing Co., Portland, OR",
        government_warning=CANONICAL,
        is_flavored_malt_beverage=False,
        warning_legible=True,
        overall_legible=True,
    )
    f.update(over)
    return f


# ---- the label set: id, beverage, expected verdict, what is planted, fields ----

SPECS = [
    # Distilled spirits (27 CFR Part 5) -------------------------------------
    {"id": "spirits_pass_bourbon", "beverage": "spirits", "expected": "PASS",
     "planted": "Fully compliant bourbon.", "fields": _spirits()},
    {"id": "spirits_pass_vodka", "beverage": "spirits", "expected": "PASS",
     "planted": "Compliant vodka at an authorized 1 L fill.",
     "fields": _spirits(brand_name="NORTH CREEK VODKA", class_type="Vodka",
                        alcohol_content="40% Alc/Vol", net_contents="1 L",
                        name_and_address="Distilled by North Creek Spirits, Austin, TX")},
    {"id": "spirits_pass_rye", "beverage": "spirits", "expected": "PASS",
     "planted": "Compliant rye in a 1.75 L handle.",
     "fields": _spirits(brand_name="IRON RIDGE RYE", class_type="Straight Rye Whiskey",
                        alcohol_content="50% Alc./Vol.", net_contents="1.75 L")},
    {"id": "spirits_fail_fill", "beverage": "spirits", "expected": "FAIL",
     "planted": "800 mL is not an authorized standard of fill (27 CFR 5.203).",
     "fields": _spirits(net_contents="800 mL")},
    {"id": "spirits_fail_warning_garbled", "beverage": "spirits", "expected": "FAIL",
     "planted": "Warning read cleanly but wording altered ('health issues' for 'health problems').",
     "fields": _spirits(government_warning=WARNING_GARBLED)},
    {"id": "spirits_fail_warning_header", "beverage": "spirits", "expected": "FAIL",
     "planted": "'Government Warning' not in capital letters (27 CFR 16.22).",
     "fields": _spirits(government_warning=WARNING_TITLECASE_HEADER)},
    {"id": "spirits_fail_proof_only", "beverage": "spirits", "expected": "FAIL",
     "planted": "Only proof stated; percent alcohol by volume is mandatory (27 CFR 5.65).",
     "fields": _spirits(alcohol_content="90 Proof")},
    {"id": "spirits_review_classtype", "beverage": "spirits", "expected": "NEEDS REVIEW",
     "planted": "Unrecognized class/type routes to a human, not an automatic fail.",
     "fields": _spirits(brand_name="MYSTIC STILL", class_type="Artisanal Mystery Spirit")},

    # Wine (27 CFR Part 4) ---------------------------------------------------
    {"id": "wine_pass_cabernet", "beverage": "wine", "expected": "PASS",
     "planted": "Compliant varietal wine with appellation and vintage.",
     "fields": _wine()},
    {"id": "wine_pass_table_no_abv", "beverage": "wine", "expected": "PASS",
     "planted": "Table wine 14% or under may omit the numeric ABV (27 CFR 4.36).",
     "fields": _wine(brand_name="HARVEST ROAD", class_type="Red Table Wine",
                    alcohol_content=None, appellation=None, vintage=None,
                    grape_varietal=None)},
    {"id": "wine_pass_chardonnay", "beverage": "wine", "expected": "PASS",
     "planted": "Compliant Chardonnay with appellation for its varietal/vintage.",
     "fields": _wine(brand_name="SONOMA BLUFF", class_type="Chardonnay",
                    grape_varietal="Chardonnay", appellation="Sonoma Coast",
                    vintage="2021")},
    {"id": "wine_fail_fill", "beverage": "wine", "expected": "FAIL",
     "planted": "900 mL is a spirits size, not an authorized WINE fill (27 CFR 4.72).",
     "fields": _wine(net_contents="900 mL")},
    {"id": "wine_fail_no_abv", "beverage": "wine", "expected": "FAIL",
     "planted": "Non-table wine with no ABV statement (27 CFR 4.36).",
     "fields": _wine(brand_name="CELLAR 9", class_type="Merlot", alcohol_content=None,
                    grape_varietal=None, vintage=None, appellation=None)},
    {"id": "wine_review_no_appellation", "beverage": "wine", "expected": "NEEDS REVIEW",
     "planted": "Varietal and vintage shown but no appellation (27 CFR 4.34) -> review.",
     "fields": _wine(appellation=None)},
    {"id": "wine_review_classtype", "beverage": "wine", "expected": "NEEDS REVIEW",
     "planted": "Unrecognized designation with no varietal routes to a human.",
     "fields": _wine(brand_name="ODD LOT", class_type="Mystery Cuvee",
                    grape_varietal=None, vintage=None, appellation=None)},

    # Malt beverage / beer (27 CFR Part 7) -----------------------------------
    {"id": "beer_pass_ipa", "beverage": "beer", "expected": "PASS",
     "planted": "Compliant IPA with optional ABV stated correctly.",
     "fields": _beer()},
    {"id": "beer_pass_lager_no_abv", "beverage": "beer", "expected": "PASS",
     "planted": "Ordinary lager may omit ABV (optional federally, 27 CFR 7.65).",
     "fields": _beer(brand_name="STILLWATER LAGER", class_type="Lager",
                    alcohol_content=None)},
    {"id": "beer_fail_fmb_no_abv", "beverage": "beer", "expected": "FAIL",
     "planted": "Flavored malt beverage MUST state ABV but none is shown (27 CFR 7.63).",
     "fields": _beer(brand_name="FIZZ HARD SELTZER", class_type="Malt Beverage",
                    alcohol_content=None, is_flavored_malt_beverage=True,
                    statement_of_composition="Malt beverage with natural flavors")},
    {"id": "beer_fail_warning", "beverage": "beer", "expected": "FAIL",
     "planted": "Warning read cleanly but wording altered.",
     "fields": _beer(government_warning=WARNING_GARBLED)},
    {"id": "beer_review_abv_abbrev", "beverage": "beer", "expected": "NEEDS REVIEW",
     "planted": "'ABV' is not an authorized abbreviation (27 CFR 7.65) -> review.",
     "fields": _beer(alcohol_content="5% ABV")},
    {"id": "beer_review_classtype", "beverage": "beer", "expected": "NEEDS REVIEW",
     "planted": "Unrecognized style with no statement of composition routes to a human.",
     "fields": _beer(brand_name="ZAP SELTZER", class_type="Sparkle Pop",
                    alcohol_content="5% Alc/Vol")},
]


# ---- rendering ----

def _font(size, bold=False):
    """Load a TrueType font, trying common system paths, with a safe fallback."""
    candidates = (
        ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/System/Library/Fonts/Helvetica.ttc"]
        if bold else
        ["/System/Library/Fonts/Supplemental/Arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/System/Library/Fonts/Helvetica.ttc"]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    """Greedy word-wrap so the warning fits the label width."""
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def render(spec) -> None:
    W, H = 640, 880
    margin = 40
    text_w = W - 2 * margin
    img = Image.new("RGB", (W, H), (247, 244, 236))
    d = ImageDraw.Draw(img)
    f = spec["fields"]
    bev = spec["beverage"]

    y = 54
    if f.get("brand_name"):
        d.text((margin, y), f["brand_name"], font=_font(38, bold=True), fill=(18, 18, 18))
        y += 64
    if f.get("class_type"):
        d.text((margin, y), f["class_type"], font=_font(26), fill=(40, 40, 40))
        y += 46

    if bev == "wine":
        for key in ("vintage", "grape_varietal", "appellation"):
            if f.get(key):
                d.text((margin, y), f[key], font=_font(20), fill=(55, 55, 55))
                y += 32
    if bev == "beer" and f.get("statement_of_composition"):
        d.text((margin, y), f["statement_of_composition"], font=_font(20), fill=(55, 55, 55))
        y += 32

    y += 24
    if f.get("alcohol_content"):
        d.text((margin, y), f["alcohol_content"], font=_font(22), fill=(20, 20, 20))
        y += 36
    if f.get("net_contents"):
        d.text((margin, y), f["net_contents"], font=_font(22), fill=(20, 20, 20))
        y += 36
    if bev == "wine" and f.get("sulfite_statement"):
        d.text((margin, y), f["sulfite_statement"], font=_font(17), fill=(70, 70, 70))
        y += 32
    if f.get("name_and_address"):
        for line in _wrap(d, f["name_and_address"], _font(17), text_w):
            d.text((margin, y), line, font=_font(17), fill=(70, 70, 70))
            y += 24

    # Government Warning block, anchored near the bottom. The header is drawn in a
    # bold font for realism, but the exact characters of the stored string are what
    # gets printed (and read), so the case-sensitive header check is honest.
    gw = f.get("government_warning")
    if gw:
        wy = H - 230
        if ":" in gw:
            header, body = gw.split(":", 1)
            header += ":"
        else:
            header, body = gw, ""
        d.text((margin, wy), header, font=_font(16, bold=True), fill=(0, 0, 0))
        wy += 26
        for line in _wrap(d, body.strip(), _font(16), text_w):
            d.text((margin, wy), line, font=_font(16), fill=(0, 0, 0))
            wy += 22

    img.save(IMAGES / f"{spec['id']}.png")


def main() -> int:
    IMAGES.mkdir(parents=True, exist_ok=True)
    entries = []
    for spec in SPECS:
        render(spec)
        entries.append({
            "id": spec["id"],
            "file": f"images/{spec['id']}.png",
            "beverage": spec["beverage"],
            "expected": spec["expected"],
            "planted": spec["planted"],
            "fields": spec["fields"],
        })
    MANIFEST.write_text(json.dumps(entries, indent=2) + "\n")

    by_verdict = {}
    for e in entries:
        by_verdict[e["expected"]] = by_verdict.get(e["expected"], 0) + 1
    print(f"Rendered {len(entries)} labels to {IMAGES}")
    print("By expected verdict:", ", ".join(f"{k}={v}" for k, v in sorted(by_verdict.items())))
    print(f"Manifest written to {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
