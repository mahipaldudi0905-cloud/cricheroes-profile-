#!/usr/bin/env python3
"""
CricHeroes team scraper.

Wahi flow jo browser mein hota hai, lekin script se:

    Team open  ->  Members list  ->  har player ke Stats  ->  CSV

Login ki zaroorat nahi -- CricHeroes ki public web API use hoti hai
(api-key website ke apne JS bundle mein hardcoded hai).

Usage:
    python3 cricheroes_scraper.py <team-url-ya-team-id> [options]

Examples:
    python3 cricheroes_scraper.py https://cricheroes.com/team-profile/14492365/abc-test/members
    python3 cricheroes_scraper.py 14492365 -o ~/Desktop/team.csv
    python3 cricheroes_scraper.py 14492365 --members-only    # sirf list, stats skip
    python3 cricheroes_scraper.py 14492365 --all-stats       # har available stat
"""

import argparse
import csv
import json
import os
import re
import secrets
import ssl
import sys
import time
import urllib.error
import urllib.request

WEB = "https://cricheroes.com"
API = "https://api.cricheroes.in/api/v1"
API_KEY = "cr!CkH3r0s"          # CricHeroes ke public web bundle se
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
UDID = secrets.token_hex(16)    # browser jaisa per-run device id

# macOS ke python.org build mein system certs nahi hote -- certifi se kaam chalao.
try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()


# ---------------------------------------------------------------- networking

def _get(url, headers, retries=3, timeout=30):
    req = urllib.request.Request(url, headers=headers)
    last = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, ssl.SSLError) as e:
            last = e
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise IOError(str(last))


def api(path):
    """Public web API call -- wahi headers jo CricHeroes ka apna site bhejta hai."""
    body = _get(f"{API}/{path}", {
        "api-key": API_KEY,
        "udid": UDID,
        "device-type": UA,
        "User-Agent": UA,
        "Accept": "application/json",
        "Origin": WEB,
        "Referer": WEB + "/",
    })
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise IOError("JSON nahi mila")
    if not payload.get("status"):
        raise IOError(payload.get("error", {}).get("message", "unknown error"))
    return payload.get("data") or {}


# ------------------------------------------------------- step 1: team open

def team_id_from(target):
    """Team ID ya kisi bhi team-profile URL se numeric team id nikaalo."""
    target = target.strip()
    if target.isdigit():
        return target
    m = re.search(r"/team-profile/(\d+)", target)
    if m:
        return m.group(1)
    sys.exit(f"ERROR: '{target}' mein team ID nahi mili.\n"
             f"Team ID ya poora team-profile URL dijiye.")


# ------------------------------------------------------ step 2: members list

def html_members(team_id):
    """
    Fallback: agar API se members na mile to team page ke server-rendered
    HTML (Next.js RSC payload) se nikaal lo.
    """
    html = _get(f"{WEB}/team-profile/{team_id}/team/members",
                {"User-Agent": UA, "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"})
    chunks = re.findall(
        r'self\.__next_f\.push\(\s*\[\s*1\s*,\s*("(?:[^"\\]|\\.)*")\s*\]\s*\)', html)
    payload = "".join(json.loads(c) for c in chunks if _decodable(c)) or html.replace('\\"', '"')

    for m in re.finditer(r'"members"\s*:\s*\[', payload):
        raw = _balanced(payload, payload.index("[", m.start()))
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list) and data and "player_id" in data[0]:
            return data
    return []


def _decodable(s):
    try:
        json.loads(s)
        return True
    except json.JSONDecodeError:
        return False


def _balanced(text, start):
    """`[`/`{` se balanced JSON kaat do (strings ka dhyan rakhte hue)."""
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


# ------------------------------------------------------- step 3: player stats

def flatten(stats):
    """{'batting':[{'title':..,'value':..}]} -> {('batting','matches'): value}"""
    flat = {}
    for section, items in (stats or {}).items():
        if isinstance(items, list):
            for it in items:
                title = str(it.get("title", "")).strip().lower()
                if title:
                    flat[(section.lower(), title)] = it.get("value", "")
    return flat


# (CSV heading, API section, API title) -- exactly jo maanga gaya tha
WANTED = [
    ("bat_matches",     "batting",  "matches"),
    ("bat_innings",     "batting",  "innings"),
    ("bat_runs",        "batting",  "runs"),
    ("bat_highest",     "batting",  "highest runs"),
    ("bat_average",     "batting",  "avg"),
    ("bat_strike_rate", "batting",  "sr"),
    ("bat_30s",         "batting",  "30s"),
    ("bat_50s",         "batting",  "50s"),
    ("bat_100s",        "batting",  "100s"),
    ("bowl_matches",    "bowling",  "matches"),
    ("bowl_innings",    "bowling",  "innings"),
    ("bowl_overs",      "bowling",  "overs"),
    ("bowl_wickets",    "bowling",  "wickets"),
    ("field_matches",   "fielding", "matches"),
    ("field_catches",   "fielding", "catches"),
    ("field_run_outs",  "fielding", "run outs"),
    ("field_stumpings", "fielding", "stumpings"),
]

IDENTITY = ["player_id", "name", "batter_category", "bowler_category",
            "playing_role", "batting_hand", "bowling_style", "city",
            "is_captain", "is_admin", "is_pro"]


def main():
    ap = argparse.ArgumentParser(
        description="CricHeroes team ke members + unke batting/bowling/fielding stats -> CSV")
    ap.add_argument("target", help="team URL ya team ID")
    ap.add_argument("-o", "--output", help="CSV path (default: team_<id>.csv)")
    ap.add_argument("--members-only", action="store_true",
                    help="sirf members list, per-player stats skip")
    ap.add_argument("--all-stats", action="store_true",
                    help="maange gaye columns ke alawa har available stat bhi")
    ap.add_argument("--delay", type=float, default=0.4,
                    help="do players ke beech seconds (default: 0.4)")
    args = ap.parse_args()

    team_id = team_id_from(args.target)

    # --- Step 1: team open ------------------------------------------------
    print(f"[1/4] Team open       : id {team_id}")
    try:
        info = api(f"team/get-team-profile-info/{team_id}")
        print(f"      -> {info.get('team_name', '?')}"
              f"{', ' + info['city_name'] if info.get('city_name') else ''}")
    except IOError as e:
        print(f"      -> team info nahi mili ({e}), aage badh rahe hain")

    # --- Step 2: members --------------------------------------------------
    print("[2/4] Members list    : ", end="", flush=True)
    try:
        members = api(f"team/get-team-member/{team_id}").get("members", [])
        source = "API"
    except IOError as e:
        print(f"API fail ({e}), HTML fallback... ", end="", flush=True)
        members, source = html_members(team_id), "HTML"
    if not members:
        sys.exit("\nERROR: members nahi mile -- team private/khaali ho sakti hai, "
                 "ya CricHeroes ne structure badla hai.")
    print(f"{len(members)} players ({source})")

    # --- Step 3: har player ke stats --------------------------------------
    rows, extra_cols, failed = [], [], []
    if not args.members_only:
        print(f"[3/4] Player stats    : {len(members)} players")

    for i, m in enumerate(members, 1):
        pid = m.get("player_id")
        row = {
            "player_id": pid,
            "name": m.get("name", ""),
            "batter_category": m.get("batter_category", ""),
            "bowler_category": m.get("bowler_category", ""),
            "is_captain": m.get("is_captain", 0),
            "is_admin": m.get("is_admin", 0),
            "is_pro": m.get("is_player_pro", 0),
            "playing_role": "", "batting_hand": "", "bowling_style": "", "city": "",
            "profile_url": f"{WEB}/player-profile/{pid}/"
                           f"{re.sub(r'[^a-z0-9]+', '-', str(m.get('name', '')).lower()).strip('-')}"
                           f"/statistics",
        }

        if not args.members_only:
            print(f"      [{i:>2}/{len(members)}] {m.get('name', pid)}", end="", flush=True)
            try:
                prof = api(f"player/get-player-profile-web/{pid}")
                row.update({
                    "playing_role":  prof.get("playing_role", ""),
                    "batting_hand":  prof.get("batting_hand", ""),
                    "bowling_style": prof.get("bowling_style", ""),
                    "city":          prof.get("city_name", ""),
                })
                for k in ("batter_category", "bowler_category"):
                    if prof.get(k):
                        row[k] = prof[k]           # profile ka value zyada bharosemand

                flat = flatten(api(f"player/get-player-statistic/{pid}").get("statistics", {}))
                for col, sec, key in WANTED:
                    row[col] = flat.get((sec, key), "")
                if args.all_stats:
                    known = {c for c, _, _ in WANTED}
                    for (sec, key), val in flat.items():
                        col = f"{sec}_{re.sub(r'[^a-z0-9]+', '_', key).strip('_')}"
                        if col not in known and col not in row:
                            row[col] = val
                            if col not in extra_cols:
                                extra_cols.append(col)
                print("  ok")
            except IOError as e:
                print(f"  SKIP ({e})")
                failed.append(str(m.get("name", pid)))
            time.sleep(args.delay)

        rows.append(row)

    # --- Step 4: CSV ------------------------------------------------------
    stat_cols = [] if args.members_only else [c for c, _, _ in WANTED]
    header = IDENTITY + stat_cols + extra_cols + ["profile_url"]
    out = os.path.expanduser(args.output or f"team_{team_id}.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})

    print(f"[4/4] CSV saved       : {out}")
    print(f"      {len(rows)} players x {len(header)} columns")
    if failed:
        print(f"      stats nahi mile ({len(failed)}): {', '.join(failed)}")


if __name__ == "__main__":
    main()
