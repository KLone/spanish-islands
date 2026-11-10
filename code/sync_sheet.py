"""
sync_sheet.py

Converts the Google Sheet 'Islands' tab to data/islands.json.

Usage:
  python3 sync_sheet.py                  # read data/islands.csv
  python3 sync_sheet.py --fetch          # download CSV from sheet (must be link-shared)
  python3 sync_sheet.py --region MX      # substitute MX variants where available
  python3 sync_sheet.py --fetch --region MX

Output: data/islands.json
  [
    {
      "island_num": 1,
      "island": "Getting Coffee",
      "island_slug": "getting-coffee",
      "sections": [
        {
          "section": "Bebidas",
          "lines": [
            {
              "line_id": "01-getting-coffee-01",
              "line": 1,
              "speaker": "Mesero",
              "spanish": "¡Buenos días! ¿Qué le sirvo?",
              "english": "Good morning! What can I get you?",
              "region": "",
              "notes": ""
            },
            ...
          ]
        }
      ]
    }
  ]
"""

import csv
import json
import os
import re
import sys
import urllib.request
import urllib.error

SHEET_ID   = "1tF1nY0rZuojjOMGBlouzPOvHx9J7Yl2iV4-Pe6OFMf0"
SHEET_GID  = "101"
CSV_PATH   = "data/islands.csv"
OUTPUT     = "data/islands.json"


def fetch_csv():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"
    print(f"Fetching sheet from Google Docs...")
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print("ERROR: Sheet is not publicly link-shared.")
            print("Share the sheet: File → Share → Anyone with the link → Viewer")
        else:
            print(f"ERROR: HTTP {e.code} fetching sheet.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Could not fetch sheet: {e}")
        sys.exit(1)


def slugify(text):
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def parse_rows(raw_csv, region):
    """Parse CSV rows into structured island data.

    Columns (0-indexed): Island, Section, Line, Speaker, Spanish, English,
                         Region, Variant, Variant Region, Notes
    """
    reader = csv.reader(raw_csv.splitlines())
    header = next(reader, None)  # skip header row

    islands_ordered = []   # island names in sheet order
    island_map = {}        # island_name -> {sections_ordered, sections_map}

    for row_num, row in enumerate(reader, start=2):
        if len(row) < 6:
            continue
        # Pad to at least 10 cols
        row = row + [""] * (10 - len(row))

        island_name   = row[0].strip()
        section_name  = row[1].strip()
        line_raw      = row[2].strip()
        speaker       = row[3].strip()
        spanish_col_e = row[4].strip()
        english       = row[5].strip()
        region_col_g  = row[6].strip()
        variant_h     = row[7].strip()
        variant_reg_i = row[8].strip()
        notes         = row[9].strip()

        if not island_name or not speaker:
            continue

        # Determine Spanish text to use
        if region and variant_reg_i.upper() == region.upper() and variant_h:
            spanish = variant_h
            used_region = variant_reg_i
        else:
            spanish = spanish_col_e
            used_region = region_col_g

        if not spanish or not english:
            print(f"WARNING row {row_num}: empty Spanish or English — skipping")
            continue

        # Stage directions are display-only, never spoken
        is_stage_direction = notes.startswith("Stage direction:")

        try:
            line_num = int(line_raw)
        except ValueError:
            print(f"WARNING row {row_num}: non-integer line number '{line_raw}' — skipping")
            continue

        if island_name not in island_map:
            island_map[island_name] = {"sections_ordered": [], "sections_map": {}}
            islands_ordered.append(island_name)

        idata = island_map[island_name]
        if section_name not in idata["sections_map"]:
            idata["sections_map"][section_name] = []
            idata["sections_ordered"].append(section_name)

        idata["sections_map"][section_name].append({
            "line_num": line_num,
            "speaker": speaker,
            "spanish": spanish,
            "english": english,
            "used_region": used_region,
            "notes": notes,
            "is_stage_direction": is_stage_direction,
        })

    return islands_ordered, island_map


def validate_and_build(islands_ordered, island_map):
    output = []
    total_lines = 0
    total_kirk = 0
    errors = []

    for island_num, island_name in enumerate(islands_ordered, start=1):
        slug = slugify(island_name)
        idata = island_map[island_name]
        sections_out = []

        for section_name in idata["sections_ordered"]:
            raw_lines = sorted(idata["sections_map"][section_name], key=lambda x: x["line_num"])

            # Validate contiguous line numbers
            nums = [l["line_num"] for l in raw_lines]
            expected = list(range(nums[0], nums[0] + len(nums)))
            if nums != expected:
                errors.append(f"Island '{island_name}' section '{section_name}': "
                               f"line numbers not contiguous: {nums}")

            lines_out = []
            for l in raw_lines:
                line_id = f"{island_num:02d}-{slug}-{l['line_num']:02d}"
                lines_out.append({
                    "line_id": line_id,
                    "line": l["line_num"],
                    "speaker": l["speaker"],
                    "spanish": l["spanish"],
                    "english": l["english"],
                    "region": l["used_region"],
                    "notes": l["notes"],
                    "is_stage_direction": l["is_stage_direction"],
                })
                total_lines += 1
                if l["speaker"].lower() == "kirk":
                    total_kirk += 1

            sections_out.append({"section": section_name, "lines": lines_out})

        output.append({
            "island_num": island_num,
            "island": island_name,
            "island_slug": slug,
            "sections": sections_out,
        })

    if errors:
        print("VALIDATION ERRORS:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)

    return output, total_lines, total_kirk


def main():
    args = sys.argv[1:]
    do_fetch = "--fetch" in args
    region = None
    if "--region" in args:
        idx = args.index("--region")
        if idx + 1 < len(args):
            region = args[idx + 1].upper()
        else:
            print("ERROR: --region requires a value (e.g. --region MX)")
            sys.exit(1)

    os.makedirs("data", exist_ok=True)

    if do_fetch:
        raw_csv = fetch_csv()
        with open(CSV_PATH, "w", encoding="utf-8") as f:
            f.write(raw_csv)
        print(f"Saved to {CSV_PATH}")
    else:
        if not os.path.exists(CSV_PATH):
            print(f"ERROR: {CSV_PATH} not found.")
            print("Download the 'Islands' tab: File → Download → CSV, save as data/islands.csv")
            print("Or run with --fetch if the sheet is publicly shared.")
            sys.exit(1)
        with open(CSV_PATH, encoding="utf-8") as f:
            raw_csv = f.read()

    islands_ordered, island_map = parse_rows(raw_csv, region)
    output, total_lines, total_kirk = validate_and_build(islands_ordered, island_map)

    total_sections = sum(len(i["sections"]) for i in output)
    total_stage = sum(
        1 for i in output
        for s in i["sections"]
        for l in s["lines"]
        if l["is_stage_direction"]
    )

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    region_label = f" (region: {region})" if region else ""
    print(f"Wrote {OUTPUT}{region_label}")
    print(f"  Islands:         {len(output)}")
    print(f"  Sections:        {total_sections}")
    print(f"  Lines:           {total_lines}  ({total_stage} stage directions, never spoken)")
    print(f"  Kirk lines:      {total_kirk}")
    print(f"  Partner lines:   {total_lines - total_kirk - total_stage}")


if __name__ == "__main__":
    main()
