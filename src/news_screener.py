"""
News Screener — Google News RSS mit hartem 7-Tage-Filter + Spot-Preis-Kontext
"""

import datetime
import email.utils
import requests
from xml.etree import ElementTree as ET

KEYWORDS = { ... }  # bleibt unverändert (deine bestehenden Keywords)

RSS_URLS = { ... }  # bleibt unverändert

RELEASE_DAYS = {"energy": [1], "agri": [4], "metals": [], "equity_proxy": []}


class NewsScreener:
    def __init__(self, cfg):
        self.cfg = cfg

    def _fetch_rss(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            return r.text
        except Exception:
            return ""

    def _parse_titles(self, xml_str, max_age_days=7):
        titles = []
        if not xml_str:
            return titles

        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)

        try:
            root = ET.fromstring(xml_str)
            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                if not title:
                    continue

                pub_str = item.findtext("pubDate", "").strip()
                pub_dt = None
                if pub_str:
                    try:
                        pub_dt = email.utils.parsedate_to_datetime(pub_str)
                    except:
                        pass

                # Nur Artikel der letzten max_age_days Tage
                if pub_dt is None or pub_dt >= cutoff:
                    titles.append(title.lower())

            if not titles and len(root.findall(".//item")) > 0:
                print(f"    WARNING: No recent articles (last {max_age_days} days), using older ones")
                # Fallback: alle Titel nehmen
                for item in root.findall(".//item"):
                    title = item.findtext("title", "").strip()
                    if title:
                        titles.append(title.lower())

        except Exception as e:
            print(f"    RSS parse error: {e}")

        return titles

    def _score_titles(self, titles, kw_dict):
        # bleibt gleich wie bisher
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
        for seg in self.cfg["watchlist"]:
            xml    = self._fetch_rss(RSS_URLS[seg])
            titles = self._parse_titles(xml, max_age_days=7)   # ← harter 7-Tage-Filter
            raw, headlines = self._score_titles(titles, KEYWORDS[seg])
            n_score = self._news_score(raw)
            cal = 1 if datetime.date.today().weekday() in RELEASE_DAYS.get(seg, []) else 0

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
            print(f"  [{seg}] articles={len(titles)} news={n_score} cal={cal} total={total}")

        return results
