"""
News Screener v3 – FinBERT Sentiment + Keyword-Fallback
"""

import datetime
import email.utils
import requests
from xml.etree import ElementTree as ET

from sentiment.finbert_sentiment import FinBertSentiment   # ← NEU


class NewsScreener:
    def __init__(self, cfg):
        self.cfg = cfg
        self.max_age_days = 14                     # etwas großzügiger
        self.finbert = FinBertSentiment()          # ← FinBERT wird einmalig geladen

    def _build_rss_url(self, seg: str) -> str:
        base = self.cfg["watchlist"][seg].get("rss_query", "commodity")
        year = datetime.date.today().year
        extra = f" {year} OR today OR this week OR price OR forecast OR outlook OR rises OR falls OR surge OR slump OR Hormuz OR OPEC"
        query = f"{base}{extra}".strip()
        encoded = query.replace(" ", "+")
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        print(f"  [NEWS] Query for {seg}: {query[:110]}...")
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
        titles = []
        if not xml_str:
            return titles

        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=self.max_age_days)
        try:
            root = ET.fromstring(xml_str)
            items = root.findall(".//item")

            for item in items:
                title = item.findtext("title", "").strip()
                if not title:
                    continue

                pub_str = item.findtext("pubDate", "").strip()
                if pub_str:
                    try:
                        pub_dt = email.utils.parsedate_to_datetime(pub_str)
                        if pub_dt >= cutoff:
                            titles.append(title)
                    except:
                        continue
                else:
                    titles.append(title)   # ohne Datum trotzdem nehmen

        except Exception as e:
            print(f"  [NEWS] XML parse error: {e}")

        return titles

    def _score_titles(self, titles, segment):
        """FinBERT Sentiment + leichter Keyword-Fallback"""
        total_score = 0.0
        headlines = []
        kw_dict = self.cfg.get("keywords", {}).get(segment, {})

        for title in titles[:15]:   # nur die relevantesten analysieren
            # FinBERT Sentiment
            sentiment, confidence = self.finbert.get_sentiment(title)

            if sentiment == "bullish":
                total_score += 3.5 * confidence
            elif sentiment == "bearish":
                total_score -= 3.5 * confidence

            # leichter Keyword-Boost als Fallback
            if any(kw.lower() in title.lower() for kw in kw_dict.get("high", [])):
                total_score += 1.5
            elif any(kw.lower() in title.lower() for kw in kw_dict.get("medium", [])):
                total_score += 0.8

            headlines.append(title)

        # Normalisierung
        final_score = max(0, min(round(total_score, 1), 10))
        return final_score, headlines[:5]

    def score_all_segments(self):
        results = {}

        for seg in self.cfg["watchlist"]:
            url = self._build_rss_url(seg)
            xml = self._fetch_rss(url)
            titles = self._parse_titles(xml)

            raw_score, headlines = self._score_titles(titles, seg)

            cal = 1 if datetime.date.today().weekday() in [1, 4] else 0   # EIA / COT Tage

            total = min(10, raw_score + cal)

            results[seg] = {
                "total_score": total,
                "news_score": round(raw_score, 1),
                "calendar_bonus": cal,
                "articles_24h": len(titles),
                "top_headlines": headlines,
                "proceed": total >= self.cfg["thresholds"]["segment_score_min"],
            }

            status = "✅ QUALIFIZIERT" if results[seg]["proceed"] else "❌ zu schwach"
            print(f"  [{seg.upper()}] FinBERT-Score={raw_score:.1f} | Cal={cal} | TOTAL={total} {status}\n")

        return results
