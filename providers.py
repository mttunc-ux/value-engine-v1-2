from __future__ import annotations
import os, re
from datetime import datetime, timezone
from typing import Any
import httpx

class ProviderError(RuntimeError): pass

class ApiFootball:
    def __init__(self):
        self.key=os.getenv("APISPORTS_KEY","").strip()
        self.base=os.getenv("APISPORTS_BASE","https://v3.football.api-sports.io").rstrip("/")

    async def get(self, path: str, params: dict | None=None):
        if not self.key: raise ProviderError("APISPORTS_KEY yapılandırılmamış")
        async with httpx.AsyncClient(timeout=25) as c:
            r=await c.get(self.base+path,params=params or {},headers={"x-apisports-key":self.key})
            r.raise_for_status(); data=r.json()
        if data.get("errors"): raise ProviderError(f"API-Football: {data['errors']}")
        return data.get("response",[])

    async def find_team(self, name: str):
        rows=await self.get("/teams",{"search":name})
        if not rows: raise ProviderError(f"Takım bulunamadı: {name}")
        # Exact normalized name wins; otherwise best API result is returned but flagged.
        norm=lambda s: re.sub(r"[^a-z0-9]","",s.lower())
        exact=[x for x in rows if norm(x.get("team",{}).get("name",""))==norm(name)]
        item=(exact or rows)[0]
        return {"id":item["team"]["id"],"name":item["team"]["name"],"country":item["team"].get("country"),"venue":item.get("venue",{})}

    async def find_fixture(self, home: dict, away: dict, date: str | None=None):
        params={"team":home["id"],"next":50,"timezone":"Europe/Istanbul"}
        if date: params={"team":home["id"],"from":date,"to":date,"timezone":"Europe/Istanbul"}
        rows=await self.get("/fixtures",params)
        for f in rows:
            teams=f.get("teams",{})
            if teams.get("home",{}).get("id")==home["id"] and teams.get("away",{}).get("id")==away["id"]:
                return f
        raise ProviderError("Bu iki takım arasında yaklaşan eşleşme bulunamadı. Takım adlarını/tarihi kontrol et.")

    async def team_stats(self, team_id: int, league_id: int, season: int):
        rows=await self.get("/teams/statistics",{"team":team_id,"league":league_id,"season":season})
        return rows if isinstance(rows,dict) else (rows[0] if rows else {})

    async def injuries(self, fixture_id: int):
        try: return await self.get("/injuries",{"fixture":fixture_id})
        except Exception as e: return {"unavailable":str(e)}

    async def lineups(self, fixture_id: int):
        try: return await self.get("/fixtures/lineups",{"fixture":fixture_id})
        except Exception as e: return {"unavailable":str(e)}

    async def recent_fixtures(self, team_id: int, last: int=10):
        try: return await self.get("/fixtures",{"team":team_id,"last":last,"status":"FT","timezone":"Europe/Istanbul"})
        except Exception as e: return {"unavailable":str(e)}

class OddsApi:
    def __init__(self):
        self.key=os.getenv("ODDS_API_KEY","").strip()
        self.base=os.getenv("ODDS_API_BASE","https://api.the-odds-api.com/v4").rstrip("/")
        self.regions=os.getenv("ODDS_REGIONS","eu,uk")
        self.sports=[x.strip() for x in os.getenv("ODDS_SPORT_KEYS","soccer_epl,soccer_turkey_super_league,soccer_germany_bundesliga,soccer_spain_la_liga,soccer_italy_serie_a,soccer_france_ligue_one,soccer_uefa_champs_league").split(",") if x.strip()]

    async def odds_for_match(self, home: str, away: str):
        if not self.key: return {"available":False,"reason":"ODDS_API_KEY yapılandırılmamış","events":[]}
        found=[]; errors=[]
        async with httpx.AsyncClient(timeout=25) as c:
            for sport in self.sports:
                try:
                    r=await c.get(f"{self.base}/sports/{sport}/odds/",params={"apiKey":self.key,"regions":self.regions,"markets":"h2h,totals,btts","oddsFormat":"decimal"})
                    if r.status_code==404: continue
                    r.raise_for_status()
                    for ev in r.json():
                        if _same_match(ev.get("home_team",""),ev.get("away_team",""),home,away): found.append(ev)
                except Exception as e: errors.append(f"{sport}: {e}")
        return {"available":bool(found),"events":found,"errors":errors,"checked_at":datetime.now(timezone.utc).isoformat()}

def _norm(s): return re.sub(r"[^a-z0-9]","",(s or "").lower())
def _same_match(h,a,want_h,want_a):
    return _norm(h)==_norm(want_h) and _norm(a)==_norm(want_a)

def api_football_stats_to_summary(stats: dict[str,Any]):
    """Extract stable team scoring averages; leave unsupported fields null rather than inventing them."""
    fixtures=stats.get("fixtures",{})
    played=(fixtures.get("played",{}).get("total") or 0)
    goals=stats.get("goals",{})
    gf=(goals.get("for",{}).get("total",{}).get("total"))
    ga=(goals.get("against",{}).get("total",{}).get("total"))
    return {"played":played,"goals_for_total":gf,"goals_against_total":ga,
            "goals_for_per_match":(gf/played if played and gf is not None else None),
            "goals_against_per_match":(ga/played if played and ga is not None else None),
            "cards":stats.get("cards"),"clean_sheet":stats.get("clean_sheet"),"failed_to_score":stats.get("failed_to_score")}
