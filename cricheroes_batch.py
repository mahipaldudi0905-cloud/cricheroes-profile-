#!/usr/bin/env python3
"""
CricHeroes batch scraper -- Excel/CSV se player links padho, stats nikaalo.

    Excel (links/IDs)  ->  har player ke stats  ->  CSV

Input file ki saari original columns output mein bani rehti hain, unke
aage stats jud jate hain. Link ya bare player ID -- dono chalte hain.

Usage:
    python3 cricheroes_batch.py <excel-ya-csv> [options]

Examples:
    python3 cricheroes_batch.py ~/Desktop/players.xlsx
    python3 cricheroes_batch.py players.xlsx -o ~/Desktop/stats.csv
    python3 cricheroes_batch.py players.xlsx --column player_link
    python3 cricheroes_batch.py players.csv --all-stats
"""

import argparse
import csv
import os
import re
import sys
import time
import shutil
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

from cricheroes_scraper import WEB, UA, SSL_CTX, api, flatten, WANTED

# Bare number ko player ID maanne ke liye itne digits chahiye -- warna
# "Sr No" jaisa column galti se ID samajh liya jayega.
SRC_ROW = "__sheet_row__"   # internal key, output mein nahi jata

MIN_ID_DIGITS = 4

# Header naam jinme ID milne ki sabse zyada ummeed hai (priority order).
ID_HEADER_HINTS = ["player_url", "player url", "player_link", "player link",
                   "player_id", "player id", "profile", "url", "link", "id"]


# --------------------------------------------------------------- xlsx reader
# .xlsx sirf zip'd XML hai -- stdlib se padh lete hain taaki is project ki
# "koi external package nahi" wali baat bani rahe.

def _tag(el):
    return el.tag.split("}")[-1]


def _col_index(ref):
    """'BC12' -> 54 (0-based column index)."""
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _first_sheet_path(z):
    """workbook.xml + rels se pehli sheet ka andar-zip path nikaalo."""
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    except KeyError:
        return "xl/worksheets/sheet1.xml"

    targets = {r.get("Id"): r.get("Target") for r in rels}
    for sheets in wb:
        if _tag(sheets) != "sheets":
            continue
        for sheet in sheets:
            rid = next((v for k, v in sheet.attrib.items() if k.endswith("}id")), None)
            target = targets.get(rid)
            if target:
                target = target.lstrip("/")
                return target if target.startswith("xl/") else "xl/" + target
    return "xl/worksheets/sheet1.xml"


def read_xlsx(path):
    """[[cell, cell, ...], ...] -- pehli sheet, sab values as text."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
                shared.append("".join(t.text or "" for t in si.iter()
                                      if _tag(t) == "t"))

        sheet = ET.fromstring(z.read(_first_sheet_path(z)))

    rows = []
    for el in sheet.iter():
        if _tag(el) != "row":
            continue
        cells = {}
        for c in el:
            if _tag(c) != "c":
                continue
            idx = _col_index(c.get("r") or "A")
            kind = c.get("t")
            if kind == "inlineStr":
                val = "".join(t.text or "" for t in c.iter() if _tag(t) == "t")
            else:
                v = next((x for x in c if _tag(x) == "v"), None)
                val = "" if v is None or v.text is None else v.text
                if kind == "s" and val.isdigit() and int(val) < len(shared):
                    val = shared[int(val)]
            if val.strip():
                cells[idx] = val.strip()
        n = int(el.get("r") or len(rows) + 1)
        while len(rows) < n - 1:          # khaali rows ki jagah bhi rakho
            rows.append([])
        rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
    return rows


def read_table(path):
    """Excel ya CSV -> (headers, rows-as-dicts). Blank rows hat jati hain."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        grid = read_xlsx(path)
    elif path.lower().endswith(".xls"):
        sys.exit("ERROR: purana .xls format support nahi hai.\n"
                 "Excel mein 'Save As' -> .xlsx ya .csv karke dobara dijiye.")
    else:
        with open(path, newline="", encoding="utf-8-sig") as f:
            grid = list(csv.reader(f))

    if not grid:
        sys.exit(f"ERROR: '{path}' khaali hai.")

    headers = [h.strip() or f"col_{i+1}" for i, h in enumerate(grid[0])]
    rows = []
    for n, raw in enumerate(grid[1:], start=2):
        row = {h: (raw[i].strip() if i < len(raw) else "")
               for i, h in enumerate(headers)}
        if any(row.values()):
            row[SRC_ROW] = n          # sheet ka asli row number
            rows.append(row)
    return headers, rows


# ------------------------------------------------------------ ID extraction

def id_from_value(value, allow_bare=True):
    """Ek cell se player ID -- URL se ya bare number se."""
    text = str(value or "").strip()
    if not text:
        return None
    m = re.search(r"/player-profile/(\d+)", text)
    if m:
        return m.group(1)
    if allow_bare and text.isdigit() and len(text) >= MIN_ID_DIGITS:
        return text
    return None


def resolve_short_link(url):
    """chshare.link/player/xxx -> asli player ID (redirect follow karke)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25, context=SSL_CTX) as r:
            blob = r.geturl() + " " + r.read(20000).decode("utf-8", "replace")
    except Exception:
        return None
    m = re.search(r"/player-profile/(\d+)", blob)
    return m.group(1) if m else None


def resolve_id(value):
    """(player_id, kaise-mila) -- zaroorat pade to network bhi use karta hai."""
    text = str(value or "").strip()
    if not text:
        return None, "khaali"

    m = re.search(r"/player-profile/(\d+)", text)
    if m:
        return m.group(1), "link"
    if text.isdigit() and len(text) >= MIN_ID_DIGITS:
        return text, "ID"

    short = re.search(r"https?://\S*chshare\.link/\S+", text)
    if short:
        pid = resolve_short_link(short.group(0).rstrip(".,)"))
        return (pid, "short link") if pid else (None, "short link toota")

    # "623 290" jaisi cheez -- space/comma hata kar dekho, par flag kar do
    squashed = re.sub(r"[\s,]", "", text)
    if squashed.isdigit() and len(squashed) >= MIN_ID_DIGITS:
        return squashed, "space hataya (CHECK KARO)"

    return None, "ID nahi hai"


def row_label(row, i):
    """Progress line ke liye row ka sabse pehchaan-ne layak text."""
    for val in row.values():
        text = str(val or "").strip()
        if text and not text.isdigit() and "://" not in text:
            return text
    return f"row {i}"


def pick_column(headers, rows, forced=None):
    """Kaunsi column mein player IDs hain -- header hint + actual data dekh kar."""
    if forced:
        match = next((h for h in headers if h.lower() == forced.lower()), None)
        if not match:
            sys.exit(f"ERROR: column '{forced}' nahi mili. "
                     f"Available: {', '.join(headers)}")
        return match

    sample = rows[:50]

    def hits(header, allow_bare):
        return sum(1 for r in sample if id_from_value(r.get(header), allow_bare))

    # URLs sabse pakka signal hain -- pehle wahi dhoondo, kisi bhi column mein.
    url_cols = [(hits(h, False), h) for h in headers]
    best = max(url_cols, key=lambda x: x[0])
    if best[0]:
        return best[1]

    # URL nahi mila -> bare numbers, lekin sirf un columns mein jinka naam
    # ID jaisa lagta hai (warna "Sr No" pakad lega).
    for hint in ID_HEADER_HINTS:
        for h in headers:
            if hint in h.lower() and hits(h, True):
                return h

    sys.exit("ERROR: koi player link ya ID wali column nahi mili.\n"
             f"Columns dekhi: {', '.join(headers)}\n"
             "--column <naam> se khud bata dijiye.")


def write_xlsx(src_path, out_path, headers, new_cols, out_rows):
    """Original sheet ke aage nayi columns jod do -- baaki sab jaisa tha waisa."""
    try:
        import openpyxl
    except ImportError:
        sys.exit("ERROR: Excel likhne ke liye openpyxl chahiye:\n"
                 "  pip3 install openpyxl\n"
                 "Ya -o ke saath .csv naam dijiye.")

    if os.path.abspath(src_path) == os.path.abspath(out_path):
        backup = f"{os.path.splitext(src_path)[0]}.backup{os.path.splitext(src_path)[1]}"
        shutil.copy2(src_path, backup)
        print(f"      backup rakha    : {backup}")

    wb = openpyxl.load_workbook(src_path)
    ws = wb[wb.sheetnames[0]]
    start = len(headers) + 1

    for j, name in enumerate(new_cols):
        ws.cell(1, start + j, name)

    for r in out_rows:
        sheet_row = r.get(SRC_ROW)
        if not sheet_row:
            continue
        for j, name in enumerate(new_cols):
            val = r.get(name, "")
            if val != "":
                ws.cell(sheet_row, start + j, val)

    wb.save(out_path)


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="Excel/CSV mein diye CricHeroes player links -> stats CSV")
    ap.add_argument("input", help="Excel (.xlsx) ya CSV file")
    ap.add_argument("-o", "--output",
                    help="alag file mein likho (.csv ya .xlsx). Default: Excel "
                         "diya to usi mein, CSV diya to <naam>_stats.csv")
    ap.add_argument("--column", help="player link/ID wali column ka naam "
                                     "(default: khud detect)")
    ap.add_argument("--in-place", action="store_true",
                    help="CSV ke liye bhi usi file mein likho (Excel mein "
                         "ye pehle se default hai)")
    ap.add_argument("--all-stats", action="store_true",
                    help="maange gaye columns ke alawa har available stat bhi")
    ap.add_argument("--delay", type=float, default=0.4,
                    help="do players ke beech seconds (default: 0.4)")
    args = ap.parse_args()

    src = os.path.expanduser(args.input)
    if not os.path.exists(src):
        sys.exit(f"ERROR: file nahi mili: {src}")

    # --- Step 1: file padho -----------------------------------------------
    print(f"[1/3] Input padha    : {os.path.basename(src)}")
    headers, rows = read_table(src)
    col = pick_column(headers, rows, args.column)
    print(f"      {len(rows)} rows, {len(headers)} columns")
    print(f"      player IDs is column se: '{col}'")

    # --- Step 2: har player ke stats --------------------------------------
    print(f"[2/3] Player stats   : {len(rows)} rows")
    out_rows, extra_cols, failed, no_id = [], [], [], []
    stat_cols = [c for c, _, _ in WANTED]

    for i, row in enumerate(rows, 1):
        out = dict(row)                       # original columns as-is
        pid, how = resolve_id(row.get(col))
        label = row_label(row, i)
        out["id_source"] = how

        if not pid:
            print(f"      [{i:>3}/{len(rows)}] {label[:32]}  -- {how}")
            no_id.append(f"{label} [{how}]")
            out_rows.append(out)
            continue

        out["player_id"] = pid
        print(f"      [{i:>3}/{len(rows)}] {pid}", end="", flush=True)
        try:
            prof = api(f"player/get-player-profile-web/{pid}")
            name = prof.get("name") or prof.get("player_name") or ""
            out.update({
                "fetched_name":   name,
                "playing_role":   prof.get("playing_role", ""),
                "batting_hand":   prof.get("batting_hand", ""),
                "bowling_style":  prof.get("bowling_style", ""),
                "city":           prof.get("city_name", ""),
                "batter_category": prof.get("batter_category", ""),
                "bowler_category": prof.get("bowler_category", ""),
                "profile_url": f"{WEB}/player-profile/{pid}/"
                               f"{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}"
                               f"/statistics",
            })

            flat = flatten(api(f"player/get-player-statistic/{pid}").get("statistics", {}))
            for c, sec, key in WANTED:
                out[c] = flat.get((sec, key), "")
            if args.all_stats:
                known = set(stat_cols)
                for (sec, key), val in flat.items():
                    c = f"{sec}_{re.sub(r'[^a-z0-9]+', '_', key).strip('_')}"
                    if c not in known and c not in out:
                        out[c] = val
                        if c not in extra_cols:
                            extra_cols.append(c)
            print(f"  {name[:28] or '(no name)'}  ok")
        except IOError as e:
            print(f"  SKIP ({e})")
            failed.append(f"{label[:24]} (id {pid})")

        out_rows.append(out)
        time.sleep(args.delay)

    # --- Step 3: CSV ------------------------------------------------------
    added = ["player_id", "id_source", "fetched_name",
             "batter_category", "bowler_category",
             "playing_role", "batting_hand", "bowling_style", "city"]
    header = headers + [c for c in added if c not in headers] \
             + stat_cols + extra_cols + ["profile_url"]

    # Excel diya aur -o nahi bataya -> usi Excel mein columns jod do.
    # Yahi aam kaam hai; backup apne aap ban jata hai.
    if args.output:
        out_path = os.path.expanduser(args.output)
    elif args.in_place or src.lower().endswith((".xlsx", ".xlsm")):
        out_path = src
    else:
        out_path = os.path.splitext(src)[0] + "_stats.csv"

    new_cols = [c for c in header if c not in headers]
    if out_path.lower().endswith((".xlsx", ".xlsm")):
        write_xlsx(src, out_path, headers, new_cols, out_rows)
    else:
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
            w.writeheader()
            for r in out_rows:
                w.writerow({k: r.get(k, "") for k in header})

    ok = len(out_rows) - len(failed) - len(no_id)
    same = os.path.abspath(out_path) == os.path.abspath(src)
    print(f"[3/3] {'Usi file mein' if same else 'Nayi file'}  : {out_path}")
    print(f"      {len(out_rows)} rows x {len(header)} columns -- {ok} ke stats mile")
    if no_id:
        print(f"      ID nahi mili ({len(no_id)}): {', '.join(no_id[:5])}"
              f"{' ...' if len(no_id) > 5 else ''}")
    if failed:
        print(f"      stats nahi mile ({len(failed)}): {', '.join(failed[:5])}"
              f"{' ...' if len(failed) > 5 else ''}")


if __name__ == "__main__":
    main()
