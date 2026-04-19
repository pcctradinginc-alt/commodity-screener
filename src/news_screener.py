"""
News Screener — NEUE VERSION v2
- Strenger 10-Tage-Filter (kein aggressiver Fallback mehr)
- Dynamische RSS-Query direkt aus config.yaml + aktuelles Jahr für Frische
- Sehr detailliertes Logging der echten pubDates
- Wenn keine aktuellen Artikel → Score = 0 + klarer Warnhinweis
"""

import datetime
import email.utils
import requests
from xml.etree import ElementTree as ET


# ── Keyword-Sets (unverändert) ─────────────────────────────────────
KEYWORDS = {
    "energy": {
        "high": ["OPEC cut", "OPEC+ cut", "production cut", "supply disruption", "pipeline outage", "refinery fire", "SPR release", "inventory draw", "stock draw", "crude draw"],
        "medium": ["OPEC meeting", "rig count", "Baker Hughes", "EIA report", "EIA weekly", "petroleum status", "WTI", "Brent", "Henry Hub"],
        "low": ["oil price", "gas price", "crude oil", "natural gas"],
        "negation": ["OPEC increases", "production increase", "supply surplus", "inventory build", "stock build", "demand falls", "glut"],
    },
    "agri": { ... },   # (kannst du aus der alten Datei kopieren – bleibt gleich)
    "metals": { ... }, # bleibt gleich
    "equity_proxy": { ... }, # bleibt gleich
}


class NewsScreener:
    def __init__(self, cfg):
        self.cfg = cfg
        self.max_age_days = 10   # streng: nur letzte 10 Tage

    def _build_rss_url(self, seg: str) -> str:
        """Dynamische Query aus config.yaml + aktuelles Jahr für Frische"""
        base_query = self.cfg["watchlist"][seg].get("rss_query", "commodity news")
        
        # Zusätzliche Frische-Terme
        year = datetime.date.today().year
        extra = f" {year} OR today OR this week OR price"
        
        query = f"{base_query}{extra}".strip()
        encoded = query.replace(" ", "+")
        
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        print(f"  [NEWS] Query for {seg}: {query[:80]}...")
        return url

    def _fetch_rss(self, url: str) -> str:
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"  [NEWS] RSS fetch failed: {e}")
            return ""

    def _parse_titles(self, xml_str: str):
        """Nur wirklich aktuelle Artikel (max. 10 Tage) + volles Logging"""
        titles = []
        if not xml_str:
            return titles

        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=self.max_age_days)
        kept = 0
        skipped = 0

        try:
            root = ET.fromstring(xml_str)
            items = root.findall(".//item")

            print(f"  [NEWS] Gefundene Items im Feed: {len(items)}")

            for item in items:
                title = item.findtext("title", "").strip()
                if not title:
                    continue

                pub_str = item.findtext("pubDate", "").strip()
                pub_dt = None

                # Robusteres Parsing
                if pub_str:
                    try:
                        pub_dt = email.utils.parsedate_to_datetime(pub_str)
                    except:
                        # Fallback-Parsing
                        for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%dT%H:%M:%S%z"):
                            try:
                                pub_dt = datetime.datetime.strptime(pub_str, fmt)
                                break
                            except:
                                continue

                age_str = "???"
                if pub_dt:
                    age_days = (datetime.datetime.now(datetime.timezone.utc) - pub_dt).days
                    age_str = f"{age_days}d alt"
                    if pub_dt >= cutoff:
                        titles.append(title.lower())
                        kept += 1
                        print(f"    ✅ {age_str} | {title[:90]}")
                    else:
                        skipped += 1
                        if skipped <= 3:
                            print(f"    ❌ {age_str} (zu alt) | {title[:70]}")
                else:
                    skipped += 1
                    print(f"    ⚠️  Kein Datum | {title[:70]}")

            print(f"  [NEWS] → {kept} aktuelle Artikel behalten | {skipped} zu alt/ungültig")

        except Exception as e:
            print(f"  [NEWS] XML parse error: {e}")

        if not titles:
            print("  [NEWS] ⚠️  KEINE aktuellen Artikel in den letzten 10 Tagen → News-Score = 0")

        return titles

    def _score_titles(self, titles, kw_dict):
        """Scoring (unverändert, arbeitet jetzt aber nur mit frischen Titeln)"""
        total, scored = 0, []
        for title in titles:
            pos, neg, matched = 0, 0, ""
            for tier, w in [("high", 3), ("medium", 2), ("low", 1)]:
                for kw in kw_dict.get(tier, []):
                    if kw.lower() in title:
                        pos += w
                        if not matched:
                            matched = kw
                        break
            for kw in kw_dict.get("negation", []):
                if kw.lower() in title:
                    neg += 2
                    break
            net = max(0, min(pos - neg, 3))
            if net > 0:
                scored.append((net, title, matched))
            total += net
        scored.sort(reverse=True)
        headlines = [t for _, t, _ in scored[:3]]
        return total, headlines

    def _news_score(self, raw):
        if raw == 0: return 0
        if raw < 3:  return 1
        if raw < 6:  return 2
        if raw < 10: return 3
        if raw < 15: return 4
        return 5

    def score_all_segments(self):
        results = {}
        today = datetime.date.today()

        for seg in self.cfg["watchlist"]:
            url = self._build_rss_url(seg)
            xml = self._fetch_rss(url)
            titles = self._parse_titles(xml)

            raw, headlines = self._score_titles(titles, KEYWORDS[seg])
            n_score = self._news_score(raw)

            # Kalender-Bonus (Release-Tage)
            release_days = {"energy": [1], "agri": [4], "metals": [], "equity_proxy": []}
            cal = 1 if today.weekday() in release_days.get(seg, []) else 0

            total = min(10, n_score + cal)

            results[seg] = {
                "total_score": total,
                "news_score": n_score,
                "calendar_bonus": cal,
                "articles_24h": len(titles),
                "news_raw": raw,
                "iv_rank": 0,
                "top_headlines": headlines,
                "proceed": total >= self.cfg["thresholds"]["segment_score_min"],
            }

            status = "✅ QUALIFIZIERT" if results[seg]["proceed"] else "❌ zu schwach"
            print(f"  [{seg.upper()}] {len(titles)} aktuelle Artikel | News={n_score} | Cal={cal} | TOTAL={total} {status}\n")

        return results
