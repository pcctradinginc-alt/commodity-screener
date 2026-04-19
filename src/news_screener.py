"""
News Screener — NEUE VERSION v2.1 (fix)
- Strenger 10-Tage-Filter (kein aggressiver Fallback mehr)
- Dynamische RSS-Query + aktuelles Jahr für Frische
- Vollständiges KEYWORDS-Dict (kein Set mehr!)
- Detailliertes Logging der pubDates
"""

import datetime
import email.utils
import requests
from xml.etree import ElementTree as ET


# ── VOLLSTÄNDIGES KEYWORDS-DICT (exakt aus Original) ─────────────────────
KEYWORDS = {
    "energy": {
        "high": [
            "OPEC cut","OPEC+ cut","production cut","supply disruption",
            "pipeline outage","refinery fire","refinery outage","force majeure",
            "sanctions","embargo","export ban","Iran nuclear",
            "Strait of Hormuz","Red Sea attack","tanker attack",
            "SPR release","strategic reserve","inventory draw","stock draw","crude draw",
            "natural gas shortage","LNG shortage","cold snap","heat dome",
            "Libya shutdown","Nigeria outage","Venezuela sanction",
            "backwardation spike","supply crisis",
        ],
        "medium": [
            "OPEC meeting","OPEC output","oil output","rig count","Baker Hughes",
            "EIA report","EIA weekly","petroleum status","gasoline demand","diesel demand",
            "refinery utilization","crack spread","WTI rally","Brent rally",
            "Henry Hub","natural gas storage","LNG export","contango",
            "oil inventory","crude inventory","fuel demand",
        ],
        "low": [
            "oil price","gas price","energy price","crude oil",
            "petroleum","fuel cost","heating oil","jet fuel",
        ],
        "negation": [
            "OPEC increases output","OPEC raises output","production increase",
            "supply surplus","inventory build","stock build","crude build",
            "demand falls","demand destruction","recession fears cut demand",
            "cut expectations lowered","surplus expected","glut",
            "weak demand","oversupply","ample supply",
        ],
    },
    "agri": {
        "high": [
            "WASDE report","WASDE estimate","crop report","USDA forecast",
            "acreage report","planting intentions","drought monitor",
            "La Nina","El Nino","frost damage","flood damage","crop failure",
            "yield cut","harvest loss","export ban grain","grain embargo",
            "Black Sea blockade","Ukraine export","Russia wheat ban",
            "Argentina drought","Brazil drought","Australia flood",
            "crop disease","blight","aflatoxin","food security crisis",
            "famine warning","global grain shortage","crush margin collapse","soy crush record",
        ],
        "medium": [
            "corn production","soybean production","wheat production",
            "grain stocks","ending stocks","carryout","carryover",
            "export inspection","export sales","weekly export",
            "planting progress","crop condition","crop tour",
            "palm oil","canola","rapeseed","vegetable oil supply",
            "fertilizer price","potash shortage","urea price",
            "ethanol demand","ethanol mandate",
        ],
        "low": [
            "corn price","wheat price","soy price","grain price",
            "agriculture","farming outlook","harvest season",
        ],
        "negation": [
            "record harvest","record crop","bumper crop","record production",
            "higher ending stocks","surplus grain","ample supply",
            "rainfall improves","conditions improve","weather favorable",
            "export ban lifted","trade deal","supply adequate",
            "yield raised","production raised","acreage increase",
        ],
    },
    "metals": {
        "high": [
            "Fed rate decision","Fed surprise","rate hike surprise","rate cut surprise",
            "dollar spike","DXY surge","real yield jump",
            "China stimulus package","PBOC easing","China demand surge",
            "mining strike","mine closure","Codelco strike","Freeport shutdown",
            "LME squeeze","warehouse queue","cancelled warrants",
            "gold record","silver squeeze","copper deficit",
            "EV demand surge","battery metals shortage","lithium crisis",
            "Russia sanction metals","palladium shortage",
            "safe haven demand","geopolitical risk premium","war premium",
            "central bank gold buying","gold reserve",
        ],
        "medium": [
            "LME stocks","COMEX stocks","gold ETF flow","GLD inflow",
            "copper demand","industrial demand","PMI manufacturing",
            "aluminum smelter","zinc smelter","nickel supply",
            "platinum supply","palladium supply",
            "gold rally","silver rally","copper rally",
            "Fed minutes","Fed speech","Powell",
        ],
        "low": [
            "gold price","silver price","copper price","metal price",
            "precious metals","base metals","commodities",
        ],
        "negation": [
            "Fed holds rates","no rate change","dollar strengthens",
            "gold falls","gold declines","copper surplus",
            "China slowdown","China weak demand","PMI contracts",
            "mine output increases","supply glut metals",
            "ETF outflow gold","GLD outflow","rate hike expected","hawkish Fed",
        ],
    },
    "equity_proxy": {
        "high": [
            "sector rotation energy","XLE selloff","XLE rally",
            "commodity ETF outflow","commodity ETF inflow",
            "fund liquidation","margin call commodity",
            "forced selling","de-risking commodity",
            "Fed surprise rate","CPI shock","PPI shock",
            "recession fears","demand destruction",
            "ESG mandate fossil","fossil fuel divestment",
            "ExxonMobil earnings","Chevron earnings","Shell earnings","BP earnings",
            "BHP earnings","Rio Tinto earnings","Glencore warning",
            "unusual options activity","dark pool energy",
        ],
        "medium": [
            "XLE","XOP","USO fund","GLD fund","SLV fund","COPX",
            "commodity index","GSCI","Bloomberg commodity index",
            "options flow energy","put call ratio energy",
            "short interest energy","energy ETF flow",
            "oil major guidance","mining major guidance",
        ],
        "low": [
            "commodity stocks","energy stocks","mining stocks",
            "materials sector","resources sector",
        ],
        "negation": [
            "energy ETF inflows slow","commodity rally fades",
            "oil major misses","energy sector underperforms",
            "XLE underperform","fund inflows slow",
            "rotation out of energy","defensive rotation",
        ],
    },
}


class NewsScreener:
    def __init__(self, cfg):
        self.cfg = cfg
        self.max_age_days = 10

    def _build_rss_url(self, seg: str) -> str:
        base_query = self.cfg["watchlist"][seg].get("rss_query", "commodity news")
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

                if pub_str:
                    try:
                        pub_dt = email.utils.parsedate_to_datetime(pub_str)
                    except:
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
                        if kept <= 5:
                            print(f"    ✅ {age_str} | {title[:90]}")
                    else:
                        skipped += 1
                        if skipped <= 3:
                            print(f"    ❌ {age_str} (zu alt) | {title[:70]}")
                else:
                    skipped += 1
                    if skipped <= 3:
                        print(f"    ⚠️  Kein Datum | {title[:70]}")

            print(f"  [NEWS] → {kept} aktuelle Artikel behalten | {skipped} zu alt/ungültig")

        except Exception as e:
            print(f"  [NEWS] XML parse error: {e}")

        if not titles:
            print("  [NEWS] ⚠️  KEINE aktuellen Artikel in den letzten 10 Tagen → News-Score = 0")

        return titles

    def _score_titles(self, titles, kw_dict):
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
