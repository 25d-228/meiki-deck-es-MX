"""Check one completed stage and its relationships to accepted earlier stages."""

import json
import re
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COUNTS = {"01": 600, "02": 800, "03": 1000, "04": 1200,
          "05": 1400, "06": 1600, "07": 1000}
REQUIRED = {"schema_version", "id", "locale", "sentence", "cloze", "answer",
            "accepted_answers", "lemma", "meaning", "part_of_speech"}
OPTIONAL = {"register", "note"}
SPECIFIC = {"morphology", "pronunciation", "usage", "variety"}


def length(text):
    normalized = unicodedata.normalize("NFC", text)
    words = len(re.findall(r"[^\W_]+(?:['’][^\W_]+)*", normalized))
    chars = sum(not char.isspace() for char in normalized)
    return words, chars


def check(stage):
    errors = []
    cards = json.loads((ROOT / f"cards/es-MX/{stage}.json").read_text())
    expected = [f"es-{stage}-{index:04d}" for index in range(1, COUNTS[stage] + 1)]
    if not isinstance(cards, list):
        raise ValueError("Stage must be a JSON array")
    actual = [card.get("common", {}).get("id") for card in cards]
    if actual != expected:
        errors.append("Card count or ordered IDs do not match the fixed stage")

    coverage = (ROOT / f"coverage/es-MX/{stage}.md").read_text()
    rows = []
    for line in coverage.splitlines():
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if parts and re.fullmatch(rf"es-{stage}-\d{{4}}", parts[0]):
            rows.append(parts)
    if [row[0] for row in rows] != expected:
        errors.append("Coverage must contain exactly one ordered row per card")
    if any(len(row) != 3 or not all(row) for row in rows):
        errors.append("Coverage rows require ID, block and hidden learning point")

    previous_ids = set()
    sentences = {}
    for path in sorted((ROOT / "cards/es-MX").glob("*.json")):
        if path.stem >= stage:
            continue
        for card in json.loads(path.read_text()):
            common = card["common"]
            previous_ids.add(common["id"])
            sentences[unicodedata.normalize("NFC", common["sentence"]).strip().casefold()] = common["id"]

    seen_ids = set(previous_ids)
    word_cap, char_cap = {"01": (12, 90), "02": (16, 120)}.get(stage, (20, 150))
    for index, card in enumerate(cards, 1):
        label = f"es-{stage}-{index:04d}"
        local = []
        if not isinstance(card, dict) or set(card) != {"common", "language_specific"}:
            errors.append(f"{label}: expected exactly the two card objects")
            continue
        common, specific = card["common"], card["language_specific"]
        if not isinstance(common, dict) or not isinstance(specific, dict):
            errors.append(f"{label}: both card regions must be objects")
            continue
        if not REQUIRED <= set(common) or set(common) - REQUIRED - OPTIONAL:
            local.append("incorrect common fields")
        if set(specific) - SPECIFIC:
            local.append("unplanned language-specific field")
        if type(common.get("schema_version")) is not int or common.get("schema_version") != 2:
            local.append("schema_version must be integer 2")
        if common.get("locale") != "es-MX":
            local.append("incorrect locale")
        for key in (REQUIRED - {"schema_version", "accepted_answers"}) | (OPTIONAL & set(common)):
            value = common.get(key)
            if not isinstance(value, str) or not value.strip():
                local.append(f"{key} must be a nonempty string")
        for key, value in specific.items():
            if not isinstance(value, str) or not value.strip():
                local.append(f"{key} must be a nonempty string")
        for value in list(common.values()) + list(specific.values()):
            if isinstance(value, str) and unicodedata.normalize("NFC", value) != value:
                local.append("text must be NFC")
        variants = common.get("accepted_answers")
        if not isinstance(variants, list) or any(not isinstance(v, str) or not v.strip() for v in variants):
            local.append("accepted_answers must be an array of nonempty strings")
            variants = []
        if len(variants) != len(set(variants)) or common.get("answer") in variants:
            local.append("redundant accepted answer")
        sentence, cloze = common.get("sentence"), common.get("cloze")
        if isinstance(sentence, str) and isinstance(cloze, str) and cloze:
            if common.get("answer") != cloze or sentence.count(cloze) != 1:
                local.append("cloze must occur exactly once and equal answer")
            else:
                start = sentence.index(cloze)
                end = start + len(cloze)
                if unicodedata.combining(cloze[0]) or (end < len(sentence) and unicodedata.combining(sentence[end])):
                    local.append("cloze splits a grapheme")
            if any(measure > cap for measure, cap in zip(length(sentence), (word_cap, char_cap))):
                local.append("sentence exceeds hard cap")
            for value in [cloze, *variants]:
                if unicodedata.normalize("NFC", value) != value or any(measure > cap for measure, cap in zip(length(value), (5, 40))):
                    local.append("cloze or accepted answer violates NFC/length cap")
            normalized = unicodedata.normalize("NFC", sentence).strip().casefold()
            if normalized in sentences:
                local.append(f"duplicate sentence with {sentences[normalized]}")
            sentences[normalized] = label
        if common.get("id") in seen_ids:
            local.append("duplicate ID")
        seen_ids.add(common.get("id"))
        if "pronunciation" in specific and not specific["pronunciation"].startswith(("Target:", "Sentence:")):
            local.append("pronunciation requires declared target/sentence scope")
        if stage == "01" and index <= 80 and "pronunciation" not in specific:
            local.append("foundation pronunciation support missing")
        if stage == "07" and not specific.get("usage", "").startswith("Domain:"):
            local.append("stage 07 domain/relationship support missing")
        errors.extend(f"{label}: {message}" for message in local)

    if errors:
        print("\n".join(errors))
        return 1
    print(f"PASS: stage {stage}; {len(cards)} cards and synchronized coverage; fields, caps, clozes and duplicates checked")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COUNTS:
        raise SystemExit("Usage: .venv/bin/python scripts/check_content.py NN")
    raise SystemExit(check(sys.argv[1]))
