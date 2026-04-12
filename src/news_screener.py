"""
News Screener — Google News RSS + weighted keyword scoring
Segment-specific keywords with negation penalty
"""

import datetime
import datetime
import email.utils
import requests
from xml.etree import ElementTree as ET

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

RSS_URLS = {
    "energy":       "https://news.google.com/rss/search?q=crude+oil+WTI+Brent+OPEC+natural+gas&hl=en-US&gl=US&ceid=US:en",
    "agri":         "https://news.google.com/rss/search?q=USDA+WASDE+corn+wheat+soybean+crop+harvest&hl=en-US&gl=US&ceid=US:en",
    "metals":       "https://news.google.com/rss/search?q=gold+silver+copper+LME+Fed+interest+rate+metals&hl=en-US&gl=US&ceid=US:en",
    "equity_proxy": "https://news.google.com/rss/search?q=XLE+GLD+USO+energy+ETF+commodity+fund&hl=en-US&gl=US&ceid=US:en",
}

RELEASE_DAYS = {"energy": [1], "agri": [4], "metals": [], "equity_proxy": []}
MAX_POINTS_PER_TITLE = 3


class NewsScreener:
    def __init__(self, cfg):
        self.cfg = cfg

    def _fetch_rss(self, url):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            return r.text
        except Exception:
            return ""

    def _parse_titles(self, xml_str):
        titles = []
        if not xml_str:
            return titles
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)
        try:
            root = ET.fromstring(xml_str)
            for item in root.findall(".//item"):
                t = item.findtext("title", "").strip()
                if not t:
                    continue
                pub_str = item.findtext("pubDate", "").strip()
                pub_dt  = None
                if pub_str:
                    try:
                        # RFC-2822 parser — handles all RSS date variants reliably
                        pub_dt = email.utils.parsedate_to_datetime(pub_str)
                    except Exception:
                        pass
                # If date unparseable → include (conservative)
                # If date parseable and older than cutoff → skip
                if pub_dt is not None and pub_dt < cutoff:
                    continue
                titles.append(t.lower())
        except ET.ParseError:
            pass
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
            net = max(0, min(pos - neg, MAX_POINTS_PER_TITLE))
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
            xml = self._fetch_rss(RSS_URLS[seg])
            print(f"  [{seg}] RSS length: {len(xml)} chars")
            if xml:
                # Show first pubDate for debugging
                try:
                    from xml.etree import ElementTree as ET2
                    root2 = ET2.fromstring(xml)
                    first = root2.find(".//item/pubDate")
                    print(f"  [{seg}] First pubDate: {repr(first.text if first is not None else 'none')}")
                except Exception:
                    pass
            titles = self._parse_titles(xml)
            raw, headlines = self._score_titles(titles, KEYWORDS[seg])
            n_score = self._news_score(raw)
            cal = 1 if datetime.date.today().weekday() in RELEASE_DAYS.get(seg, []) else 0

            ticker = self.cfg["watchlist"][seg]["tickers"][0]
            iv_rank = 0
            motion = 0

            total = min(10, n_score + motion + cal)
            results[seg] = {
                "total_score": total,
                "news_score": n_score,
                "motion_score": motion,
                "calendar_bonus": cal,
                "articles_24h": len(titles),
                "news_raw": raw,
                "iv_rank": iv_rank,
                "top_headlines": headlines,
                "proceed": total >= self.cfg["thresholds"]["segment_score_min"],
            }
            print(f"  [{seg}] articles={len(titles)} news={n_score} cal={cal} total={total}")
        return results
