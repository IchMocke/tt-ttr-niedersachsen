import json
import math
import re
from datetime import datetime
from bs4 import BeautifulSoup
import requests

SCHEDULE_URL = "https://ttvn.click-tt.de/cgi-bin/WebObjects/nuLigaTTDE.woa/wa/groupPage?displayTyp=gesamt&displayDetail=meetings&championship=KV+GS+26%2F27&group=525439"

BASE_URL = "https://ttvn.click-tt.de"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_html(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text

def get_finished_meeting_urls(schedule_html):
    soup = BeautifulSoup(schedule_html, "html.parser")
    meeting_urls = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(key in href for key in ["meeting", "federationMeeting", "meetingReport"]):
            link_text = a.get_text().strip()
            row = a.find_parent("tr")
            row_text = row.get_text() if row else ""

            if re.search(r"\b\d+\s*:\s*\d+\b", link_text) or re.search(r"\b\d+\s*:\s*\d+\b", row_text):
                full_url = href if href.startswith("http") else (BASE_URL + href if href.startswith("/") else BASE_URL + "/" + href)
                if full_url not in meeting_urls:
                    meeting_urls.append(full_url)

    return meeting_urls

def parse_meeting(meeting_html):
    soup = BeautifulSoup(meeting_html, "html.parser")

    date_str = "2026-01-01"
    date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", soup.get_text())
    if date_match:
        date_str = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}"

    matches = []

    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 6:
            continue

        row_text = row.get_text(" ", strip=True)

        if re.search(r"\b(D[1-3]|DA[1-2]|DB[1-2]|Doppel)\b", row_text, re.IGNORECASE):
            continue

        score_match = None
        for cell in reversed(cells):
            txt = cell.get_text(strip=True)
            m = re.fullmatch(r"([0-3])\s*:\s*([0-3])", txt)
            if m:
                s1, s2 = int(m.group(1)), int(m.group(2))
                if (s1 == 3 or s2 == 3) and s1 != s2:
                    score_match = (s1, s2)
                    break

        if not score_match:
            continue

        s_a, s_b = score_match

        links = row.find_all("a")
        player_candidates = [
            a.get_text(strip=True) for a in links
            if len(a.get_text(strip=True)) > 3 and not re.match(r"^(\d+|[A-Z]\d+)$", a.get_text(strip=True))
        ]

        p_a, p_b = None, None
        if len(player_candidates) >= 2:
            p_a, p_b = player_candidates[0], player_candidates[1]
        else:
            text_candidates = []
            for c in cells:
                val = c.get_text(strip=True)
                if len(val) >= 4 and not re.search(r"\d", val) and ":" not in val:
                    text_candidates.append(val)
            if len(text_candidates) >= 2:
                p_a, p_b = text_candidates[0], text_candidates[1]

        if not p_a or not p_b:
            continue

        if "/" in p_a or "/" in p_b:
            continue

        p_a = re.sub(r"^\d+[\.\s]+", "", p_a).strip()
        p_b = re.sub(r"^\d+[\.\s]+", "", p_b).strip()

        winner = p_a if s_a > s_b else p_b
        matches.append({
            "date": date_str,
            "playerA": p_a,
            "playerB": p_b,
            "winner": winner
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

        exp = (p_b["currentTtr"] - p_a["currentTtr"]) / 150.0
        prob_a = 1.0 / (1.0 + math.pow(10, exp))
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
        with open("player_baselines.json", "r", encoding="utf-8") as f:
            baselines = json.load(f)
    except FileNotFoundError:
        print("player_baselines.json nicht gefunden, Fallbacks aktiv.")

    print(f"Lade Spielplan: {SCHEDULE_URL}")
    schedule_html = fetch_html(SCHEDULE_URL)
    meeting_urls = get_finished_meeting_urls(schedule_html)
    print(f"{len(meeting_urls)} Spielberichte gefunden.")

    all_matches = []
    for url in meeting_urls:
        print(f"Lade Bericht: {url}")
        try:
            html = fetch_html(url)
            parsed = parse_meeting(html)
            print(f"  -> {len(parsed)} Einzelpartien gefunden.")
            all_matches.extend(parsed)
        except Exception as e:
            print(f"  Fehler bei {url}: {e}")

    print(f"Gesamt: {len(all_matches)} Einzelpartien erfasst. Berechne TTR-Replay...")
    ranking = run_replay(all_matches, baselines)

    output = {
        "lastUpdated": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "ranking": ranking
    }
    with open("ttr_data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print("ttr_data.json erfolgreich erzeugt.")

if __name__ == "__main__":
    main()
