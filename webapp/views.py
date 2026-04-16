from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from zhcore.models import Opportunity, OpportunityReview, PublishedPick, UserProfile

from .dashboard_data import build_dashboard_payload


def _get_profile(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={"display_name": user.get_full_name() or user.get_username()},
    )
    if not profile.display_name:
        profile.display_name = user.get_full_name() or user.get_username()
        profile.save(update_fields=["display_name", "updated_at"])
    return profile


def _backoffice_allowed(user) -> bool:
    return user.is_authenticated and _get_profile(user).can_access_backoffice


def _default_public_reason(opportunity: Opportunity) -> str:
    if opportunity.why_entered:
        first_block = str(opportunity.why_entered).split("|", 1)[0].strip()
        if first_block:
            return first_block
    return (
        f"Escolhida por EV {opportunity.ev:.1%}, edge {opportunity.edge:.1%}, "
        f"conf {opportunity.conf:.1%} e probabilidade final {opportunity.p_final:.1%}."
    )


def _sync_publication_from_pick(publication: PublishedPick) -> None:
    latest_pick = publication.opportunity.picks.order_by("-updated_at", "-created_at").first()
    if not latest_pick or latest_pick.status == "O":
        return
    status_map = {
        "G": "won",
        "P": "lost",
        "E": "draw",
        "V": "void",
    }
    new_status = status_map.get(latest_pick.status, publication.status)
    fields = []
    if publication.status != new_status:
        publication.status = new_status
        fields.append("status")
    if publication.result_label != latest_pick.status:
        publication.result_label = latest_pick.status
        fields.append("result_label")
    if publication.result_profit != latest_pick.profit:
        publication.result_profit = latest_pick.profit
        fields.append("result_profit")
    if latest_pick.settled_at and publication.settled_at != latest_pick.settled_at:
        publication.settled_at = latest_pick.settled_at
        fields.append("settled_at")
    if fields:
        fields.append("updated_at")
        publication.save(update_fields=fields)


def _publication_kpis(queryset) -> dict[str, float]:
    total = queryset.count()
    resolved = queryset.exclude(status__in=["scheduled", "live", "archived"])
    wins = resolved.filter(status="won").count()
    profit_total = resolved.aggregate(total=Sum("result_profit")).get("total") or 0.0
    hit_rate = (wins / resolved.count() * 100.0) if resolved.exists() else 0.0
    roi = (profit_total / resolved.count() * 100.0) if resolved.exists() else 0.0
    return {
        "published": total,
        "resolved": resolved.count(),
        "hit_rate": round(hit_rate, 2),
        "roi": round(roi, 2),
        "profit_total": round(float(profit_total), 2),
    }


def public_home_view(request: HttpRequest) -> HttpResponse:
    return JsonResponse(
        {
            "ok": True,
            "service": "zebra-license-backend",
            "message": "License backend online.",
            "endpoints": {
                "license_status": "/api/public/license/status/",
                "license_checkout": "/api/public/license/checkout/",
                "mercado_pago_webhook": "/api/public/payments/mercadopago/webhook/",
            },
        },
        status=200,
    )


@login_required
def post_login_redirect_view(request: HttpRequest) -> HttpResponse:
    if _backoffice_allowed(request.user):
        return redirect("backoffice_dashboard")
    return redirect("member_dashboard")


@login_required
def member_dashboard_view(request: HttpRequest) -> HttpResponse:
    profile = _get_profile(request.user)
    if not profile.is_portal_active:
        messages.error(request, "Seu acesso ao portal esta desativado.")
        return redirect("logout")

    upcoming = list(
        PublishedPick.objects.filter(is_active=True, visibility="members", status__in=["scheduled", "live"])
        .select_related("opportunity__match__league")
        .order_by("kickoff_snapshot", "-priority")[:10]
    )
    recent = list(
        PublishedPick.objects.filter(is_active=True, visibility="members")
        .exclude(status__in=["scheduled", "live"])
        .select_related("opportunity__match__league")
        .order_by("-settled_at", "-updated_at")[:10]
    )
    all_public = list(
        PublishedPick.objects.filter(is_active=True, visibility="members")
        .select_related("opportunity__match__league")
        .order_by("-published_at")[:20]
    )
    for item in upcoming + recent + all_public:
        _sync_publication_from_pick(item)
    kpis = _publication_kpis(PublishedPick.objects.filter(is_active=True, visibility="members"))
    context = {
        "profile": profile,
        "kpis": kpis,
        "upcoming_picks": upcoming,
        "recent_results": recent,
        "latest_publications": all_public[:8],
    }
    return render(request, "member_dashboard.html", context)


@login_required
def member_pick_detail_view(request: HttpRequest, slug: str) -> HttpResponse:
    publication = get_object_or_404(
        PublishedPick.objects.select_related("opportunity__match__league", "opportunity__match__home_team", "opportunity__match__away_team"),
        slug=slug,
        is_active=True,
    )
    _sync_publication_from_pick(publication)
    context = {"pick": publication}
    return render(request, "member_pick_detail.html", context)


@login_required
def backoffice_dashboard_view(request: HttpRequest) -> HttpResponse:
    if not _backoffice_allowed(request.user):
        messages.info(request, "Seu acesso e somente leitura. Abrindo o portal do cliente.")
        return redirect("member_dashboard")

    payload = build_dashboard_payload()
    pending_candidates = (
        Opportunity.objects.select_related("match__league", "match__home_team", "match__away_team", "underdog_team")
        .filter(Q(review__isnull=True) | Q(review__decision="pending"))
        .order_by("-created_at")[:6]
    )
    latest_publications = list(
        PublishedPick.objects.filter(is_active=True).select_related("opportunity__match__league").order_by("-published_at")[:6]
    )
    for item in latest_publications:
        _sync_publication_from_pick(item)

    context = {
        "db_ready": payload.get("db_ready", True),
        "kpis": payload.get("kpis", {}),
        "top_leagues": payload.get("top_leagues", []),
        "latest_scans": payload.get("latest_scans", []),
        "latest_opportunities": payload.get("latest_opportunities", []),
        "latest_jobs": payload.get("latest_jobs", []),
        "charts_json": json.dumps(payload.get("charts", {}), ensure_ascii=False),
        "pending_candidates": pending_candidates,
        "published_count": PublishedPick.objects.filter(is_active=True).count(),
        "latest_publications": latest_publications,
    }
    return render(request, "dashboard.html", context)


@login_required
def backoffice_review_view(request: HttpRequest) -> HttpResponse:
    if not _backoffice_allowed(request.user):
        messages.error(request, "Acesso restrito ao backoffice.")
        return redirect("member_dashboard")

    candidates = (
        Opportunity.objects.select_related("match__league", "match__home_team", "match__away_team", "underdog_team")
        .filter(Q(review__isnull=True) | Q(review__decision__in=["pending", "approved"]))
        .order_by("-score", "-created_at")[:24]
    )
    published = list(
        PublishedPick.objects.filter(is_active=True).select_related("opportunity__match__league").order_by("-published_at")[:12]
    )
    for item in published:
        _sync_publication_from_pick(item)
    context = {
        "candidates": candidates,
        "published_picks": published,
    }
    return render(request, "backoffice_review.html", context)


@login_required
def backoffice_review_action_view(request: HttpRequest, opportunity_id: int) -> HttpResponse:
    if request.method != "POST":
        return redirect("backoffice_review")
    if not _backoffice_allowed(request.user):
        messages.error(request, "Acesso restrito ao backoffice.")
        return redirect("member_dashboard")

    opportunity = get_object_or_404(
        Opportunity.objects.select_related("match__league", "match__home_team", "match__away_team", "underdog_team"),
        pk=opportunity_id,
    )
    review, _ = OpportunityReview.objects.get_or_create(opportunity=opportunity)
    action = (request.POST.get("action") or "").strip().lower()
    public_reason = (request.POST.get("public_reason") or "").strip()
    private_note = (request.POST.get("private_note") or "").strip()
    public_note = (request.POST.get("public_note") or "").strip()
    priority_raw = (request.POST.get("priority") or "0").strip()
    try:
        priority = int(priority_raw)
    except ValueError:
        priority = 0

    review.reviewed_by = request.user
    review.reviewed_at = timezone.now()
    if public_reason:
        review.public_reason = public_reason
    if private_note:
        review.private_note = private_note

    if action == "approve":
        review.decision = "approved"
        review.save()
        messages.success(request, f"Oportunidade {opportunity.id} aprovada para publicacao.")
    elif action == "reject":
        review.decision = "rejected"
        review.save()
        messages.warning(request, f"Oportunidade {opportunity.id} rejeitada.")
    elif action == "publish":
        review.decision = "published"
        if not review.public_reason:
            review.public_reason = _default_public_reason(opportunity)
        review.save()
        publication, _ = PublishedPick.objects.get_or_create(opportunity=opportunity)
        publication.title = publication.title or f"{opportunity.match.home_team.name} x {opportunity.match.away_team.name}"
        publication.short_reason = review.public_reason
        publication.public_note = public_note or publication.public_note or (
            f"Underdog {opportunity.underdog_team.name} com leitura favoravel em odd {opportunity.odd_best:.2f}."
        )
        publication.priority = priority
        publication.published_by = request.user
        publication.visibility = "members"
        publication.is_active = True
        publication.status = "scheduled" if opportunity.match.status in {"NS", "PST"} else "live"
        publication.save()
        messages.success(request, f"Oportunidade {opportunity.id} publicada no portal do cliente.")
    elif action == "archive":
        publication = getattr(opportunity, "published_pick", None)
        if publication:
            publication.is_active = False
            publication.status = "archived"
            publication.save(update_fields=["is_active", "status", "updated_at"])
            messages.info(request, f"Pick {publication.title} arquivada.")
        else:
            messages.warning(request, "Nao havia pick publicada para arquivar.")
    else:
        messages.error(request, "Acao invalida.")

    return redirect("backoffice_review")
