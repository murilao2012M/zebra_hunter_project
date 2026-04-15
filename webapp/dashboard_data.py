from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db.utils import OperationalError, ProgrammingError

from zhcore.models import AsyncTaskRun, Match, Opportunity, Pick, ScanSession


@dataclass
class LeagueAccumulator:
    picks: int = 0
    wins: int = 0
    losses: int = 0
    stake: float = 0.0
    profit: float = 0.0


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _pick_dt(pick: Pick) -> datetime:
    return pick.settled_at or pick.created_at


def _downsample(labels: list[str], values: list[float], max_points: int = 140) -> tuple[list[str], list[float]]:
    if len(labels) <= max_points:
        return labels, values
    step = max(1, len(labels) // max_points)
    sampled_labels = labels[::step]
    sampled_values = values[::step]
    if sampled_labels[-1] != labels[-1]:
        sampled_labels.append(labels[-1])
        sampled_values.append(values[-1])
    return sampled_labels, sampled_values


def build_dashboard_payload() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "db_ready": True,
        "kpis": {
            "scans": 0,
            "matches": 0,
            "opportunities": 0,
            "picks_total": 0,
            "picks_settled": 0,
            "hit_rate": 0.0,
            "roi": 0.0,
            "profit_total": 0.0,
            "bankroll": 100.0,
            "max_drawdown": 0.0,
            "avg_edge": 0.0,
            "avg_ev": 0.0,
        },
        "charts": {
            "bankroll_curve": {"labels": [], "values": []},
            "daily_pnl": {"labels": [], "values": []},
            "roi_by_league": {"labels": [], "values": []},
            "status_dist": {"labels": ["G", "P", "E", "V"], "values": [0, 0, 0, 0]},
        },
        "top_leagues": [],
        "latest_scans": [],
        "latest_opportunities": [],
        "latest_jobs": [],
    }

    try:
        scans_count = ScanSession.objects.count()
        matches_count = Match.objects.count()
        opp_count = Opportunity.objects.count()
        picks_total = Pick.objects.count()
    except (OperationalError, ProgrammingError):
        payload["db_ready"] = False
        return payload

    settled_qs = (
        Pick.objects.select_related("opportunity__match__league")
        .exclude(status="O")
        .order_by("settled_at", "created_at", "id")
    )

    bankroll = 100.0
    peak = bankroll
    max_dd = 0.0
    labels: list[str] = []
    values: list[float] = []
    daily: dict[str, float] = defaultdict(float)
    leagues: dict[str, LeagueAccumulator] = defaultdict(LeagueAccumulator)
    status_counts = {"G": 0, "P": 0, "E": 0, "V": 0}

    profit_total = 0.0
    stake_total = 0.0
    wins = 0
    losses = 0
    edge_sum = 0.0
    ev_sum = 0.0
    edge_n = 0

    for pick in settled_qs:
        dt = _pick_dt(pick)
        profit = _to_float(pick.profit)
        stake = _to_float(pick.stake)
        status = (pick.status or "").strip().upper()
        league_name = pick.opportunity.match.league.name if pick.opportunity_id and pick.opportunity.match_id else "Unknown"

        bankroll += profit
        peak = max(peak, bankroll)
        max_dd = min(max_dd, bankroll - peak)

        labels.append(dt.strftime("%d/%m %H:%M"))
        values.append(round(bankroll, 2))
        daily[dt.strftime("%Y-%m-%d")] += profit

        agg = leagues[league_name]
        agg.picks += 1
        agg.stake += stake
        agg.profit += profit
        if status == "G":
            agg.wins += 1
            wins += 1
        elif status == "P":
            agg.losses += 1
            losses += 1

        if status in status_counts:
            status_counts[status] += 1

        if pick.opportunity_id:
            edge_sum += _to_float(pick.opportunity.edge)
            ev_sum += _to_float(pick.opportunity.ev)
            edge_n += 1

        profit_total += profit
        stake_total += stake

    roi = (profit_total / stake_total * 100.0) if stake_total > 0 else 0.0
    hit_rate = (wins / (wins + losses) * 100.0) if (wins + losses) > 0 else 0.0
    avg_edge = (edge_sum / edge_n * 100.0) if edge_n > 0 else 0.0
    avg_ev = (ev_sum / edge_n * 100.0) if edge_n > 0 else 0.0

    curve_labels, curve_values = _downsample(labels, values, max_points=160)

    daily_labels = sorted(daily.keys())
    daily_values = [round(daily[d], 2) for d in daily_labels]

    league_rows: list[dict[str, Any]] = []
    for league_name, agg in leagues.items():
        league_roi = (agg.profit / agg.stake * 100.0) if agg.stake > 0 else 0.0
        league_hit = (agg.wins / (agg.wins + agg.losses) * 100.0) if (agg.wins + agg.losses) > 0 else 0.0
        league_rows.append(
            {
                "league": league_name,
                "picks": agg.picks,
                "profit": round(agg.profit, 2),
                "roi": round(league_roi, 2),
                "hit_rate": round(league_hit, 2),
            }
        )
    league_rows.sort(key=lambda x: (x["profit"], x["picks"]), reverse=True)
    top_leagues = league_rows[:10]

    roi_league_labels = [row["league"] for row in top_leagues]
    roi_league_values = [row["roi"] for row in top_leagues]

    latest_scans = list(ScanSession.objects.order_by("-started_at")[:8])
    latest_opps = list(
        Opportunity.objects.select_related("match", "underdog_team", "scan_session")
        .order_by("-created_at")[:10]
    )
    latest_jobs = list(AsyncTaskRun.objects.order_by("-created_at")[:8])

    payload["kpis"] = {
        "scans": scans_count,
        "matches": matches_count,
        "opportunities": opp_count,
        "picks_total": picks_total,
        "picks_settled": len(labels),
        "hit_rate": round(hit_rate, 2),
        "roi": round(roi, 2),
        "profit_total": round(profit_total, 2),
        "bankroll": round(bankroll, 2),
        "max_drawdown": round(max_dd, 2),
        "avg_edge": round(avg_edge, 2),
        "avg_ev": round(avg_ev, 2),
    }
    payload["charts"] = {
        "bankroll_curve": {"labels": curve_labels, "values": curve_values},
        "daily_pnl": {"labels": daily_labels, "values": daily_values},
        "roi_by_league": {"labels": roi_league_labels, "values": roi_league_values},
        "status_dist": {
            "labels": ["G", "P", "E", "V"],
            "values": [
                status_counts["G"],
                status_counts["P"],
                status_counts["E"],
                status_counts["V"],
            ],
        },
    }
    payload["top_leagues"] = top_leagues
    payload["latest_scans"] = [
        {
            "id": s.id,
            "status": s.status,
            "started_at": s.started_at.strftime("%Y-%m-%d %H:%M"),
            "top": s.top,
        }
        for s in latest_scans
    ]
    payload["latest_opportunities"] = [
        {
            "match": f"{o.match.home_team.name} x {o.match.away_team.name}",
            "underdog": o.underdog_team.name,
            "ev": round(_to_float(o.ev) * 100.0, 2),
            "edge": round(_to_float(o.edge) * 100.0, 2),
            "conf": round(_to_float(o.conf) * 100.0, 2),
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
        }
        for o in latest_opps
    ]
    payload["latest_jobs"] = [
        {
            "task_id": j.task_id,
            "kind": j.kind,
            "status": j.status,
            "created_at": j.created_at.strftime("%Y-%m-%d %H:%M"),
            "finished_at": j.finished_at.strftime("%Y-%m-%d %H:%M") if j.finished_at else "",
        }
        for j in latest_jobs
    ]

    return payload
