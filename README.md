# CricHeroes Scrapers

CricHeroes se players ke batting/bowling/fielding stats CSV mein nikaalte hain.
Public web API use hoti hai — login ki zaroorat nahi.

Do script hain:

| Script | Input | Kaam |
|---|---|---|
| `cricheroes_scraper.py` | team URL ya team ID | poori team ke saare members + unke stats |
| `cricheroes_batch.py` | Excel/CSV with player links ya IDs | sirf listed players ke stats |

## 1. Poori team — `cricheroes_scraper.py`

    python3 cricheroes_scraper.py <team-url-ya-team-id> [options]

    python3 cricheroes_scraper.py 14492365 -o ~/Desktop/team.csv
    python3 cricheroes_scraper.py 14492365 --members-only
    python3 cricheroes_scraper.py 14492365 --all-stats

## 2. Excel se list — `cricheroes_batch.py`

Apni Excel/CSV mein player ke link ya ID wali ek column rakhiye. Baaki
columns jaisi hain waisi hi output mein aa jayengi, unke aage stats jud
jayenge.

    python3 cricheroes_batch.py <excel-ya-csv> [options]

    python3 cricheroes_batch.py ~/Desktop/players.xlsx
    python3 cricheroes_batch.py players.xlsx -o ~/Desktop/stats.csv
    python3 cricheroes_batch.py players.xlsx --column "CricHeroes Link"
    python3 cricheroes_batch.py players.csv --all-stats
    python3 cricheroes_batch.py players.xlsx --in-place

Input file aisi ho sakti hai:

| Sr No | Player Name | Notes | CricHeroes Link |
|---|---|---|---|
| 1 | Abhijit | opener | https://cricheroes.com/player-profile/6814484/abhijit/statistics |
| 2 | Abhisheikh | bowler | 8552279 |

Link ki jagah sirf player ID bhi chalti hai. Column khud detect ho jati
hai — na ho toh `--column <naam>` se bata dijiye. Jis row ka link/ID na
mile ya galat ho, wo row original data ke saath rehti hai, stats khaali
reh jate hain, aur end mein list ban jati hai.

Link ki jagah CricHeroes ka short link (`chshare.link/player/...`) ya
poora share message bhi chalta hai — script redirect follow karke asli ID
nikaal leti hai. Column `id_source` batati hai har ID kahan se aayi, taaki
galat entry pakdi ja sake.

`--in-place` se nayi columns usi Excel file mein jud jati hain (purani
columns ko haath nahi lagta) aur saath mein `<naam>.backup.xlsx` ban jati
hai.

Format `.xlsx` ya `.csv` — purana `.xls` support nahi hai (Excel mein
Save As karke `.xlsx` bana lijiye).

## Common options

    -o, --output      output path (.csv ya .xlsx)
    --in-place        usi Excel file mein columns jod do (+ backup)
    --column          link/ID wali column ka naam (default: khud detect)
    --all-stats       maange gaye columns ke alawa har available stat
    --delay           do players ke beech seconds (default: 0.4)

## Output columns

Batting: matches, innings, runs, highest, average, strike rate, 30s, 50s, 100s
Bowling: matches, innings, overs, wickets
Fielding: matches, catches, run outs, stumpings
Profile: batter/bowler category, playing role, batting hand, bowling style, city

## Requirements

Python 3.8+ — Excel *padhne* ke liye koi external package nahi, `.xlsx`
stdlib se hi padhi jati hai.

Optional: `openpyxl` sirf tab chahiye jab Excel *likhni* ho (`--in-place`
ya `-o something.xlsx`). `certifi` macOS SSL ke liye.
