from __future__ import annotations
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from providers import ApiFootball, OddsApi, ProviderError, api_football_stats_to_summary
from engine import analyze_quotes

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
app = FastAPI(title="Value Engine", version="1.2.0", description="Multi-source football analysis and value estimation")
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["*"])
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND)), name="assets")

class AnalyzeRequest(BaseModel):
    home: str = Field(min_length=2, max_length=80)
    away: str = Field(min_length=2, max_length=80)
    date: str | None = None
    min_ev_pct: float = Field(default=2.0, ge=0, le=50)
    user_odds: list[dict[str, Any]] = Field(default_factory=list)

@app.get("/")
async def home_page():
    page = FRONTEND / "value-engine.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Frontend file not found")
    return FileResponse(page)

@app.get("/health")
async def health():
    return {"ok": True, "service": "value-engine", "version": app.version,
            "time": datetime.now(timezone.utc).isoformat(),
            "api_football_configured": bool(os.getenv("APISPORTS_KEY")),
            "odds_api_configured": bool(os.getenv("ODDS_API_KEY"))}

def _market_to_model(market: str, outcome: str, home: str, away: str, point: float | None):
    key = (market or "").lower()
    name = (outcome or "").strip().lower()
    if key == "h2h":
        if name == "draw": return "1X2", "X", "h2h", "draw", "draw"
        if name.casefold() == home.casefold(): return "1X2", "1", "h2h", "home", "home_win"
        if name.casefold() == away.casefold(): return "1X2", "2", "h2h", "away", "away_win"
        return None
    if key == "totals" and point is not None and abs(point - round(point)) == 0.5:
        line = str(point).replace(".", "_")
        side = "over" if name == "over" else "under" if name == "under" else None
        if side:
            return f"Toplam gol {point}", f"{side.title()} {point}", f"totals:{point}", side, f"{side}_{line}"
    if key == "btts":
        if name in ("yes", "evet"): return "Karşılıklı gol", "Var", "btts", "yes", "btts_yes"
        if name in ("no", "hayır", "hayir"): return "Karşılıklı gol", "Yok", "btts", "no", "btts_no"
    return None

def _odds_to_quotes(odds_data: dict, home: str, away: str):
    quotes=[]; raw=[]
    for event in odds_data.get("events", []):
        for bookmaker in event.get("bookmakers", []):
            bm = bookmaker.get("title") or bookmaker.get("key") or "Unknown bookmaker"
            for market in bookmaker.get("markets", []):
                mkey = market.get("key")
                for outcome in market.get("outcomes", []):
                    price = outcome.get("price")
                    if not isinstance(price, (int, float)) or price <= 1: continue
                    mapped = _market_to_model(mkey, outcome.get("name", ""), home, away, outcome.get("point"))
                    raw.append({"bookmaker": bm, "market": mkey, "name": outcome.get("name"),
                                "point": outcome.get("point"), "price": price,
                                "last_update": market.get("last_update")})
                    if not mapped: continue
                    label, selection, group, selection_key, model_key = mapped
                    quotes.append({"market": label, "selection": selection, "group": f"{bm}:{group}",
                                   "selection_key": selection_key, "model_key": model_key,
                                   "odds": float(price), "bookmaker": bm, "source": "The Odds API"})
    return quotes, raw

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    football = ApiFootball(); odds_provider = OddsApi()
    try:
        import asyncio
        home, away = await asyncio.gather(football.find_team(req.home), football.find_team(req.away))
        fixture = await football.find_fixture(home, away, req.date)
        league = fixture.get("league", {}); season = league.get("season")
        if not season: raise ProviderError("Sezon bilgisi alınamadı; analiz durduruldu.")
        hs, aws = await asyncio.gather(football.team_stats(home["id"], league["id"], season),
                                       football.team_stats(away["id"], league["id"], season))
        hsum, asum = api_football_stats_to_summary(hs), api_football_stats_to_summary(aws)
        league_avg = 2.65  # documented fallback prior; replace with league-specific historical estimate in calibrated release
        h_att, a_def = hsum.get("goals_for_per_match"), asum.get("goals_against_per_match")
        a_att, h_def = asum.get("goals_for_per_match"), hsum.get("goals_against_per_match")
        if None in (h_att, a_def, a_att, h_def):
            raise ProviderError("Takım sezon gol ortalamaları eksik; güvenilir hesap yapılamadığı için analiz durduruldu.")
        # Provisional goals-based attack/defence baseline. Explicitly not labelled as xG.
        lambda_home = max(.2, min(4.5, (h_att / league_avg) * (a_def / league_avg) * league_avg * 1.08))
        lambda_away = max(.2, min(4.5, (a_att / league_avg) * (h_def / league_avg) * league_avg * .92))
        odds_data = await odds_provider.odds_for_match(home["name"], away["name"])
        automatic_quotes, raw_odds = _odds_to_quotes(odds_data, home["name"], away["name"])
        # User's executable odds are kept as a distinct source and take priority in the UI.
        for q in req.user_odds:
            q = dict(q); q["source"] = "User playable odds"; q["bookmaker"] = q.get("bookmaker") or "User bookmaker"
            automatic_quotes.append(q)
        analysis = analyze_quotes(lambda_home, lambda_away, automatic_quotes, req.min_ev_pct)
        fixture_id = fixture.get("fixture", {}).get("id")
        injuries, lineups = await asyncio.gather(football.injuries(fixture_id), football.lineups(fixture_id))
        return {
            "match": {"home": home, "away": away,
                      "fixture": {"id": fixture_id, "date": fixture.get("fixture", {}).get("date"),
                                  "venue": fixture.get("fixture", {}).get("venue"),
                                  "referee": fixture.get("fixture", {}).get("referee"),
                                  "league": league, "status": fixture.get("fixture", {}).get("status")}},
            "data": {"home_team_season": hsum, "away_team_season": asum,
                     "injuries": injuries, "lineups": lineups,
                     "odds_api": odds_data, "odds_quotes_raw": raw_odds},
            "model_type": "provisional_goals_based_poisson_dixon_coles_not_xg",
            "model_quality": {"status": "PROVISIONAL", "reason": "Season goals averages + fixed league prior; not yet trained/calibrated on historical match-level data.",
                              "validated": False, "xg_available": False},
            "analysis": analysis,
            "coverage": {"modelled": ["1X2", "half-goal totals", "BTTS", "team goals when matching odds are supplied"],
                         "not_modelled": ["cards", "corners", "half-time markets", "player props", "correct score combos", "referee card-rate adjustments"],
                         "note": "Unsupported markets are omitted, never assigned fabricated probabilities. Odds availability depends on competition and provider subscription."},
            "sources": ["API-Football team/fixture statistics", "The Odds API if configured", "User-entered executable odds if provided"],
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    except ProviderError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Veri sağlayıcı/analiz hatası: {e}")
