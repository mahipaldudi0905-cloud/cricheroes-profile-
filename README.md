# CricHeroes Team Scraper

CricHeroes team ke members aur unke batting/bowling/fielding stats
CSV mein nikaalta hai. Public web API use karta hai — login ki zaroorat nahi.

## Usage

    python3 cricheroes_scraper.py <team-url-ya-team-id> [options]

    python3 cricheroes_scraper.py 14492365 -o ~/Desktop/team.csv
    python3 cricheroes_scraper.py 14492365 --members-only
    python3 cricheroes_scraper.py 14492365 --all-stats

## Output columns

Batting: matches, innings, runs, highest, average, strike rate, 30s, 50s, 100s
Bowling: matches, innings, overs, wickets
Fielding: matches, catches, run outs, stumpings
Profile: batter/bowler category, playing role, batting hand, bowling style, city

## Requirements

Python 3.8+ — koi external package nahi (certifi optional hai, macOS SSL ke liye).
