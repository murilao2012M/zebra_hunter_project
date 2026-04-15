from __future__ import annotations

import json
import os
import secrets
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from django.http import HttpRequest, JsonResponse
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from pydantic import ValidationError

from .dashboard_data import build_dashboard_payload
from .ops_monitor import collect_ops_snapshot
from zhcore.license_service import check_license_status, create_checkout_session, process_mercado_pago_webhook
from zhcore.models import AsyncTaskRun, Opportunity, PublishedPick, UserProfile


def _api_auth_required(view_func: Callable[..., JsonResponse]) -> Callable[..., JsonResponse]:
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> JsonResponse:
        if not request.user.is_authenticated:
            return JsonResponse({"ok": False, "message": "autenticacao obrigatoria."}, status=401)
        return view_func(request, *args, **kwargs)

    return _wrapped


def _parse_json_body(request: HttpRequest) -> dict[str, Any]:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalido: {exc}") from exc


def _engine_unavailable_response(exc: Exception | None = None) -> JsonResponse:
    message = "Engine Zebra Hunter nao esta disponivel neste deploy de backend."
    if exc:
        message = f"{message} Detalhe: {exc}"
    return JsonResponse({"ok": False, "message": message}, status=503)


def _import_engine_components() -> tuple[Any, Any, Any, Any, Any, Any, Any]:
    from zebra_hunter.api.schemas import AnalyzeAlertsRequest, BackupRequest, PerformanceRequest, ScanRequest, UpdateResultsRequest
    from zebra_hunter.api.service import EngineService
    from zhcore.ingest import ingest_scan_rows

    return (
        AnalyzeAlertsRequest,
        BackupRequest,
        PerformanceRequest,
        ScanRequest,
        UpdateResultsRequest,
        EngineService,
        ingest_scan_rows,
    )


def _import_async_tasks() -> tuple[Any, Any, Any, Any, Any, Any]:
    from zhcore.tasks import (
        analyze_alerts_task,
        backup_task,
        mongo_sync_task,
        performance_task,
        scan_task,
        update_results_task,
    )

    return analyze_alerts_task, backup_task, mongo_sync_task, performance_task, scan_task, update_results_task


def _api_backoffice_allowed(request: HttpRequest) -> bool:
    if not request.user.is_authenticated:
        return False
    profile, _ = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={"display_name": request.user.get_full_name() or request.user.get_username()},
    )
    return profile.can_access_backoffice


def _token_health_allowed(request: HttpRequest) -> bool:
    expected = (os.getenv("DJANGO_HEALTH_TOKEN") or "").strip()
    if not expected:
        return False
    candidate = (
        (request.headers.get("X-Zebra-Health-Token") or "").strip()
        or (request.GET.get("token") or "").strip()
    )
    if not candidate:
        return False
    return secrets.compare_digest(expected, candidate)


@csrf_exempt
@require_POST
def api_public_license_status(request: HttpRequest) -> JsonResponse:
    try:
        payload = _parse_json_body(request)
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    result = check_license_status(payload)
    status_code = 200 if result.get("ok") or str(result.get("status")) in {"trial", "trial_expired", "device_limit", "invalid"} else 400
    return JsonResponse(result, status=status_code)


@csrf_exempt
@require_POST
def api_public_license_checkout(request: HttpRequest) -> JsonResponse:
    try:
        payload = _parse_json_body(request)
    except ValueError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    result = create_checkout_session(payload)
    return JsonResponse(result, status=200 if result.get("ok") else 400)


@csrf_exempt
@require_POST
def api_public_mercadopago_webhook(request: HttpRequest) -> JsonResponse:
    try:
        payload = _parse_json_body(request)
    except ValueError:
        payload = {}
    result = process_mercado_pago_webhook(payload, request.GET.dict(), dict(request.headers))
    status_code = 200 if result.get("ok") else 401 if str(result.get("status")) == "unauthorized" else 400
    return JsonResponse(result, status=status_code)


@csrf_exempt
@require_GET
@_api_auth_required
def api_health(request: HttpRequest) -> JsonResponse:
    try:
        _, _, _, _, _, EngineService, _ = _import_engine_components()
    except Exception as exc:
        return _engine_unavailable_response(exc)
    service = EngineService()
    payload = service.health(scheduler={"enabled": False, "jobs": [], "source": "django"})
    payload["message"] = "django engine online"
    return JsonResponse(payload, status=200)


@csrf_exempt
@require_GET
@_api_auth_required
def api_dashboard_summary(request: HttpRequest) -> JsonResponse:
    payload = build_dashboard_payload()
    return JsonResponse({"ok": True, "data": payload}, status=200)


@csrf_exempt
@require_GET
@_api_auth_required
def api_portal_feed(request: HttpRequest) -> JsonResponse:
    picks = (
        PublishedPick.objects.filter(is_active=True, visibility="members")
        .select_related("opportunity__match__league")
        .order_by("kickoff_snapshot", "-priority")[:20]
    )
    payload = [
        {
            "slug": pick.slug,
            "title": pick.title,
            "league": pick.league_name_snapshot,
            "country": pick.country_snapshot,
            "kickoff": pick.kickoff_snapshot.isoformat() if pick.kickoff_snapshot else None,
            "underdog": pick.underdog_snapshot,
            "odd": pick.odd_snapshot,
            "ev": pick.ev_snapshot,
            "edge": pick.edge_snapshot,
            "conf": pick.conf_snapshot,
            "p_final": pick.p_final_snapshot,
            "status": pick.status,
            "reason": pick.short_reason or pick.public_note,
            "public_note": pick.public_note,
        }
        for pick in picks
    ]
    return JsonResponse({"ok": True, "data": payload}, status=200)


@csrf_exempt
@require_GET
@_api_auth_required
def api_backoffice_candidates(request: HttpRequest) -> JsonResponse:
    if not _api_backoffice_allowed(request):
        return JsonResponse({"ok": False, "message": "acesso restrito ao backoffice."}, status=403)
    candidates = (
        Opportunity.objects.select_related("match__league", "match__home_team", "match__away_team", "underdog_team")
        .filter(Q(review__isnull=True) | Q(review__decision__in=["pending", "approved"]))
        .order_by("-score", "-created_at")[:30]
    )
    payload = [
        {
            "id": opp.id,
            "fixture_id": opp.match.fixture_id,
            "title": f"{opp.match.home_team.name} x {opp.match.away_team.name}",
            "league": opp.match.league.name,
            "country": opp.match.league.country,
            "kickoff": opp.match.kickoff.isoformat(),
            "underdog": opp.underdog_team.name,
            "odd": opp.odd_best,
            "ev": opp.ev,
            "edge": opp.edge,
            "conf": opp.conf,
            "p_final": opp.p_final,
            "score": opp.score,
            "tier": opp.tier,
            "why_entered": opp.why_entered,
            "score_breakdown": opp.score_breakdown,
            "review_decision": getattr(getattr(opp, "review", None), "decision", "pending"),
            "public_reason": getattr(getattr(opp, "review", None), "public_reason", ""),
        }
        for opp in candidates
    ]
    return JsonResponse({"ok": True, "data": payload}, status=200)


@csrf_exempt
@require_GET
def api_ops_healthz(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated and not _token_health_allowed(request):
        return JsonResponse({"ok": False, "message": "autenticacao obrigatoria."}, status=401)
    payload = collect_ops_snapshot()
    status_code = 200 if payload.get("ok") else 503
    return JsonResponse(payload, status=status_code)


@csrf_exempt
@require_GET
@_api_auth_required
def api_ops_metrics(request: HttpRequest) -> JsonResponse:
    payload = collect_ops_snapshot()
    return JsonResponse({"ok": True, "data": payload}, status=200)


@csrf_exempt
@require_POST
@_api_auth_required
def api_scan_run(request: HttpRequest) -> JsonResponse:
    try:
        _, _, _, ScanRequest, _, EngineService, ingest_scan_rows = _import_engine_components()
    except Exception as exc:
        return _engine_unavailable_response(exc)
    try:
        req = ScanRequest(**_parse_json_body(request))
    except (ValueError, ValidationError) as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

    service = EngineService()
    result = service.run_scan(req)
    if result.get("ok"):
        ingested = ingest_scan_rows(result, req)
        result.setdefault("data", {})
        result["data"]["ingested"] = ingested
        return JsonResponse(result, status=200)
    return JsonResponse(result, status=500)


@csrf_exempt
@require_POST
@_api_auth_required
def api_performance_run(request: HttpRequest) -> JsonResponse:
    try:
        _, _, PerformanceRequest, _, _, EngineService, _ = _import_engine_components()
    except Exception as exc:
        return _engine_unavailable_response(exc)
    try:
        req = PerformanceRequest(**_parse_json_body(request))
    except (ValueError, ValidationError) as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

    service = EngineService()
    result = service.run_performance(req)
    return JsonResponse(result, status=200 if result.get("ok") else 400)


@csrf_exempt
@require_POST
@_api_auth_required
def api_update_results_run(request: HttpRequest) -> JsonResponse:
    try:
        _, _, _, _, UpdateResultsRequest, EngineService, _ = _import_engine_components()
    except Exception as exc:
        return _engine_unavailable_response(exc)
    try:
        req = UpdateResultsRequest(**_parse_json_body(request))
    except (ValueError, ValidationError) as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

    service = EngineService()
    result = service.run_update_results(req)
    return JsonResponse(result, status=200 if result.get("ok") else 400)


@csrf_exempt
@require_POST
@_api_auth_required
def api_analyze_alerts_run(request: HttpRequest) -> JsonResponse:
    try:
        AnalyzeAlertsRequest, _, _, _, _, EngineService, _ = _import_engine_components()
    except Exception as exc:
        return _engine_unavailable_response(exc)
    try:
        req = AnalyzeAlertsRequest(**_parse_json_body(request))
    except (ValueError, ValidationError) as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

    service = EngineService()
    result = service.run_analyze_alerts(req)
    return JsonResponse(result, status=200 if result.get("ok") else 400)


def _enqueue_response(task_id: str, kind: str) -> JsonResponse:
    return JsonResponse({"ok": True, "message": "job enfileirado", "data": {"task_id": task_id, "kind": kind}}, status=202)


@csrf_exempt
@require_POST
@_api_auth_required
def api_scan_enqueue(request: HttpRequest) -> JsonResponse:
    try:
        _, _, _, ScanRequest, _, _, _ = _import_engine_components()
        _, _, _, _, scan_task, _ = _import_async_tasks()
    except Exception as exc:
        return _engine_unavailable_response(exc)
    try:
        req = ScanRequest(**_parse_json_body(request))
    except (ValueError, ValidationError) as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    task = scan_task.delay(req.model_dump())
    AsyncTaskRun.objects.update_or_create(
        task_id=task.id,
        defaults={"kind": "scan", "status": "PENDING", "requested_by": request.user.get_username(), "payload_json": req.model_dump()},
    )
    return _enqueue_response(task.id, "scan")


@csrf_exempt
@require_POST
@_api_auth_required
def api_performance_enqueue(request: HttpRequest) -> JsonResponse:
    try:
        _, _, PerformanceRequest, _, _, _, _ = _import_engine_components()
        _, _, _, performance_task, _, _ = _import_async_tasks()
    except Exception as exc:
        return _engine_unavailable_response(exc)
    try:
        req = PerformanceRequest(**_parse_json_body(request))
    except (ValueError, ValidationError) as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    task = performance_task.delay(req.model_dump())
    AsyncTaskRun.objects.update_or_create(
        task_id=task.id,
        defaults={"kind": "performance", "status": "PENDING", "requested_by": request.user.get_username(), "payload_json": req.model_dump()},
    )
    return _enqueue_response(task.id, "performance")


@csrf_exempt
@require_POST
@_api_auth_required
def api_update_results_enqueue(request: HttpRequest) -> JsonResponse:
    try:
        _, _, _, _, UpdateResultsRequest, _, _ = _import_engine_components()
        _, _, _, _, _, update_results_task = _import_async_tasks()
    except Exception as exc:
        return _engine_unavailable_response(exc)
    try:
        req = UpdateResultsRequest(**_parse_json_body(request))
    except (ValueError, ValidationError) as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    task = update_results_task.delay(req.model_dump())
    AsyncTaskRun.objects.update_or_create(
        task_id=task.id,
        defaults={"kind": "update_results", "status": "PENDING", "requested_by": request.user.get_username(), "payload_json": req.model_dump()},
    )
    return _enqueue_response(task.id, "update_results")


@csrf_exempt
@require_POST
@_api_auth_required
def api_analyze_alerts_enqueue(request: HttpRequest) -> JsonResponse:
    try:
        AnalyzeAlertsRequest, _, _, _, _, _, _ = _import_engine_components()
        analyze_alerts_task, _, _, _, _, _ = _import_async_tasks()
    except Exception as exc:
        return _engine_unavailable_response(exc)
    try:
        req = AnalyzeAlertsRequest(**_parse_json_body(request))
    except (ValueError, ValidationError) as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    task = analyze_alerts_task.delay(req.model_dump())
    AsyncTaskRun.objects.update_or_create(
        task_id=task.id,
        defaults={"kind": "analyze_alerts", "status": "PENDING", "requested_by": request.user.get_username(), "payload_json": req.model_dump()},
    )
    return _enqueue_response(task.id, "analyze_alerts")


@csrf_exempt
@require_POST
@_api_auth_required
def api_mongo_sync_enqueue(request: HttpRequest) -> JsonResponse:
    try:
        _, _, _, _, _, _, _ = _import_engine_components()
        _, _, mongo_sync_task, _, _, _ = _import_async_tasks()
    except Exception as exc:
        return _engine_unavailable_response(exc)
    body = _parse_json_body(request)
    task = mongo_sync_task.delay(body or {})
    AsyncTaskRun.objects.update_or_create(
        task_id=task.id,
        defaults={"kind": "mongo_sync", "status": "PENDING", "requested_by": request.user.get_username(), "payload_json": body or {}},
    )
    return _enqueue_response(task.id, "mongo_sync")


@csrf_exempt
@require_POST
@_api_auth_required
def api_backup_enqueue(request: HttpRequest) -> JsonResponse:
    try:
        _, BackupRequest, _, _, _, _, _ = _import_engine_components()
        _, backup_task, _, _, _, _ = _import_async_tasks()
    except Exception as exc:
        return _engine_unavailable_response(exc)
    try:
        req = BackupRequest(**_parse_json_body(request))
    except (ValueError, ValidationError) as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    task = backup_task.delay(req.model_dump())
    AsyncTaskRun.objects.update_or_create(
        task_id=task.id,
        defaults={"kind": "backup", "status": "PENDING", "requested_by": request.user.get_username(), "payload_json": req.model_dump()},
    )
    return _enqueue_response(task.id, "backup")


@csrf_exempt
@require_GET
@_api_auth_required
def api_job_status(request: HttpRequest, task_id: str) -> JsonResponse:
    obj = AsyncTaskRun.objects.filter(task_id=task_id).first()
    if not obj:
        return JsonResponse({"ok": False, "message": "job nao encontrado."}, status=404)
    return JsonResponse(
        {
            "ok": True,
            "data": {
                "task_id": obj.task_id,
                "kind": obj.kind,
                "status": obj.status,
                "requested_by": obj.requested_by,
                "created_at": obj.created_at.isoformat(),
                "started_at": obj.started_at.isoformat() if obj.started_at else None,
                "finished_at": obj.finished_at.isoformat() if obj.finished_at else None,
                "error_message": obj.error_message,
                "result_json": obj.result_json or {},
            },
        },
        status=200,
    )
