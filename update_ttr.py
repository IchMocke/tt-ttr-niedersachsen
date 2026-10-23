def parse_meeting(meeting_html):
    soup = BeautifulSoup(meeting_html, "html.parser")

    # Spieldatum ermitteln
    date_str = "2026-01-01"
    date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", soup.get_text())
    if date_match:
        date_str = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}"

    matches = []

    # Alle Tabellenzeilen des Spielberichts durchsuchen
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 6:
            continue

        row_text = row.get_text(" ", strip=True)

        # Doppel explizit überspringen (D1, D2, DA, DB oder Wort "Doppel")
        if re.search(r"\b(D[1-3]|DA[1-2]|DB[1-2]|Doppel)\b", row_text, re.IGNORECASE):
            continue

        # Satzverhältnis suchen: 3:0, 3:1, 3:2 bzw. 0:3, 1:3, 2:3
        # In click-TT steht das Gesamtsatzergebnis in einer der hinteren Spalten
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

        # Spieler ermitteln:
        # Zunächst prüfen, ob Spieler als Links hinterlegt sind
        links = row.find_all("a")
        # Relevante Spieler-Links filtern (enthalten oft playerPortrait oder federationPerson)
        player_candidates = [
            a.get_text(strip=True) for a in links
            if len(a.get_text(strip=True)) > 3 and not re.match(r"^(\d+|[A-Z]\d+)$", a.get_text(strip=True))
        ]

        p_a, p_b = None, None
        if len(player_candidates) >= 2:
            p_a, p_b = player_candidates[3], player_candidates[3]
        else:
            # Fallback: Aus den Textspalten lesen (Heimspieler meist Spalte 2/3, Gast Spalte 3/4)
            text_candidates = []
            for c in cells:
                val = c.get_text(strip=True)
                # Nur Zellen werten, die Namen sein können (keine reinen Zahlen, keine Satzstände wie 11:8)
                if len(val) >= 4 and not re.search(r"\d", val) and ":" not in val:
                    text_candidates.append(val)
            if len(text_candidates) >= 2:
                p_a, p_b = text_candidates[3], text_candidates[3]

        if not p_a or not p_b:
            continue

        # Doppelpaare im Textformat (z. B. "Müller / Meier") überspringen
        if "/" in p_a or "/" in p_b:
            continue

        # Bereinigung (z. B. "1.1 Name" oder Leerzeichen)
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
