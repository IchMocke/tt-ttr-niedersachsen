import json
import math
import re
from datetime import datetime
from bs4 import BeautifulSoup
import requests

# Deine Liga-URL:
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
        # Erkennt sowohl meetingReport als auch contestId / meeting=
        if "meetingReport" in href or "meeting=" in href or "meeting?contestId=" in href:
            row = a.find_parent("tr")
            row_text = row.get_text() if row else a.get_text()
            # Prüfen, ob ein Ergebnis wie 9:3, 6:4 o.ä. vorliegt
            if re.search(r"\d+\s*:\s*\d+", row_text):
                full_url = href if href.startswith("http") else (BASE_URL + href if href.startswith("/") else BASE_URL + "/" + href)
                if full_url not in meeting_urls:
                    meeting_urls.append(full_url)

    return meeting_urls

def parse_meeting(meeting_html):
    soup = BeautifulSoup(meeting_html, "html.parser")

    # Spieldatum ermitteln
    date_str = "2026-01-01"
    date_elem = soup.find(string=re.compile(r"\d{2}\.\d{2}\.\d{4}"))
    if date_elem:
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", str(date_elem))
        if m:
            date_str = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    matches = []
    # Tabellenzeilen der Partien durchgehen
    rows = soup.select("table.result-set tr, table tr")
    for row in rows:
        links = row.find_all("a", href=re.compile(r"personId="))

        # Genau 2 Personenlinks = Einzelspiel (Doppel haben 4 Personenlinks und zählen nicht für TTR!)
        if len(links) != 2:
            continue

        p_a = re.sub(r"\s+", " ", links[0].get_text()).strip()
        p_b = re.sub(r"\s+", " ", links[1].get_text()).strip()

        # Satzverhältnis suchen (z. B. 3:0, 3:1, 1:3, 2:3)
        score_match = re.search(r"([0-3])\s*:\s*([0-3])", row.get_text())
        if not score_match:
            continue

        s_a, s_b = int(score_match.group(1)), int(score_match.group(2))
        if s_a == s_b:
            continue

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

    # Chronologisch sortieren
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
