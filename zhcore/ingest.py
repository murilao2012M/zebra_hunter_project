from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from django.utils import timezone

from zhcore.models import League, Match, Opportunity, ScanSession, Team


def to_aware(dt_raw: Any) -> datetime:
    parsed = pd.to_datetime(dt_raw, utc=True, errors="coerce")
    if pd.isna(parsed):
        return timezone.now()
    return parsed.to_pydatetime()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def ingest_scan_rows(scan_result: dict[str, Any], req: Any) -> dict[str, int]:
    out_path = (scan_result.get("data") or {}).get("out_path")
    if not out_path:
        return {"matches": 0, "opportunities": 0}

    try:
        raw = json.loads(Path(out_path).read_text(encoding="utf-8"))
    except Exception:
        return {"matches": 0, "opportunities": 0}

    if not isinstance(raw, list):
        return {"matches": 0, "opportunities": 0}

    session = ScanSession.objects.create(
        source="django",
        started_at=timezone.now(),
        finished_at=timezone.now(),
        days=req.days,
        top=req.top,
        min_books=req.min_books,
        min_conf=req.min_conf,
        min_edge=req.min_edge,
        min_ev=req.min_ev,
        market_thr=req.thr,
        only_future=req.only_future,
        status="completed",
    )

    created_matches = 0
    created_opps = 0
    for row in raw:
        league_name = str(row.get("league", "")).strip() or "Unknown League"
        country = str(row.get("country", "")).strip()
        league_logo = str(row.get("league_logo", "")).strip()
        league, _ = League.objects.get_or_create(
            name=league_name,
            country=country,
            defaults={"code": "", "logo_url": league_logo},
        )
        if league_logo and not league.logo_url:
            league.logo_url = league_logo
            league.save(update_fields=["logo_url", "updated_at"])

        home_name = str(row.get("home", "")).strip() or "Home"
        away_name = str(row.get("away", "")).strip() or "Away"
        underdog_name = str(row.get("underdog", "")).strip() or away_name
        home_logo = str(row.get("home_logo", "")).strip()
        away_logo = str(row.get("away_logo", "")).strip()
        underdog_logo = str(row.get("underdog_logo", "")).strip()

        home, _ = Team.objects.get_or_create(name=home_name, country=country, defaults={"logo_url": home_logo})
        away, _ = Team.objects.get_or_create(name=away_name, country=country, defaults={"logo_url": away_logo})
        underdog, _ = Team.objects.get_or_create(
            name=underdog_name,
            country=country,
            defaults={"logo_url": underdog_logo},
        )

        fixture_id = str(row.get("fixture_id", "")).strip()
        if not fixture_id:
            continue
        kickoff = to_aware(row.get("kickoff"))
        match, created = Match.objects.get_or_create(
            fixture_id=fixture_id,
            defaults={
                "kickoff": kickoff,
                "league": league,
                "home_team": home,
                "away_team": away,
                "status": "NS",
                "source": "api_sports",
            },
        )
        if created:
            created_matches += 1
        else:
            updates: list[str] = []
            if match.kickoff != kickoff:
                match.kickoff = kickoff
                updates.append("kickoff")
            if match.league_id != league.id:
                match.league = league
                updates.append("league")
            if match.home_team_id != home.id:
                match.home_team = home
                updates.append("home_team")
            if match.away_team_id != away.id:
                match.away_team = away
                updates.append("away_team")
            if updates:
                updates.append("updated_at")
                match.save(update_fields=updates)

        Opportunity.objects.create(
            scan_session=session,
            match=match,
            underdog_team=underdog,
            odd_best=to_float(row.get("odd_best")),
            p_market=to_float(row.get("p_mkt") or row.get("p_market")),
            p_model=to_float(row.get("p_model")),
            p_api=to_float(row.get("p_api")),
            p_final=to_float(row.get("p_final")),
            edge=to_float(row.get("edge")),
            ev=to_float(row.get("ev")),
            conf=to_float(row.get("conf")),
            score=to_float(row.get("score")),
            books=to_int(row.get("books")),
            tier=str(row.get("tier") or "C")[:1],
            why_entered=str(row.get("why_entered") or ""),
            score_breakdown=str(row.get("score_breakdown") or ""),
        )
        created_opps += 1

    return {"matches": created_matches, "opportunities": created_opps}
