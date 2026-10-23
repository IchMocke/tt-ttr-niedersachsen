import json
import math
import re
import urllib.request
from datetime import datetime
from bs4 import BeautifulSoup

# HIER DIE URL DEINER LIGA EINTRAGEN:
SCHEDULE_URL = "https://ttvn.click-tt.de/cgi-bin/WebObjects/nuLigaTTDE.woa/wa/groupPage?championship=KV+GS+26%2F27&group=525439"

BASE_URL = "https://ttvn.click-tt.de"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def fetch_html(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")

def get_finished_meeting_urls(schedule_html):
    soup = BeautifulSoup(schedule_html, "html.parser")
    meeting_urls = []
    for a in soup.find_all("a", href=True):
        if "meeting?contestId=" in a["href"]:
            row = a.find_parent("tr")
            if row and re.search(r"\d+\s*:\s*\d+", row.get_text()):
                full_url = BASE_URL + a["href"] if a["href"].startswith("/") else a["href"]
                if full_url not in meeting_urls:
                    meeting_urls.append(full_url)
    return meeting_urls

def parse_meeting(meeting_html):
    soup = BeautifulSoup(meeting_html, "html.parser")
    date_str = "2026-01-01"
    date_elem = soup.find(string=re.compile(r"\d{2}\.\d{2}\.\d{4}"))
    if date_elem:
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", str(date_elem))
        if m:
            date_str = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    matches = []
    rows = soup.select(".result-set tr, table tr")
    for row in rows:
        links = row.find_all("a", href=re.compile(r"personId="))
        if len(links) < 2:
            continue
        p_a = re.sub(r"\s+", " ", links[0].get_text()).strip()
        p_b = re.sub(r"\s+", " ", links[1].get_text()).strip()
        score_match = re.search(r"([0-3])\s*:\s*([0-3])", row.get_text())
        if not score_match:
            continue
        s_a, s_b = int(score_match.group(1)), int(score_match.group(2))
        if s_a == s_b:
            continue
        matches.append({
            "date": date_str,
            "playerA": p_a,
            "playerB": p_b,
            "winner": p_a if s_a > s_b else p_b
        })
    return matches

def run_replay(all_matches, baselines):
    players = {}
    def get_player(name):
        if name not in players:
            base = baselines.get(name, 1500)
            players[name] = {"name": name, "qttr": base, "currentTtr": base, "matches": 0}
        return players[name]

    all_matches.sort(key=lambda x: x["date"])

    for m in all_matches:
        p_a = get_player(m["playerA"])
        p_b = get_player(m["playerB"])
        exp_a = (p_b["currentTtr"] - p_a["currentTtr"]) / 150.0
        prob_a = 1.0 / (1.0 + math.pow(10, exp_a))
        prob_b = 1.0 - prob_a
        act_a = 1.0 if m["winner"] == m["playerA"] else 0.0
        act_b = 1.0 - act_a
        delta_a = round((act_a - prob_a) * 16)
        delta_b = round((act_b - prob_b) * 16)
        p_a["currentTtr"] += delta_a
        p_b["currentTtr"] += delta_b
        p_a["matches"] += 1
        p_b["matches"] += 1

    ranking = list(players.values())
    for p in ranking:
        p["diff"] = p["currentTtr"] - p["qttr"]
    ranking.sort(key=lambda x: x["currentTtr"], reverse=True)
    return ranking

def main():
    baselines = {}
    try:
        with open("baselines.json", "r", encoding="utf-8") as f:
            baselines = json.load(f)
    except FileNotFoundError:
        pass

    schedule_html = fetch_html(SCHEDULE_URL)
    meeting_urls = get_finished_meeting_urls(schedule_html)

    all_matches = []
    for url in meeting_urls:
        html = fetch_html(url)
        all_matches.extend(parse_meeting(html))

    ranking = run_replay(all_matches, baselines)
    output = {
        "lastUpdated": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "ranking": ranking
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
