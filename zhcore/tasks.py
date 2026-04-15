from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from celery import shared_task
from django.utils import timezone
from pydantic import ValidationError

from zebra_hunter.api.schemas import AnalyzeAlertsRequest, BackupRequest, PerformanceRequest, ScanRequest, UpdateResultsRequest
from zebra_hunter.api.service import EngineService
from zebra_hunter.api.schemas import MongoSyncRequest
from zebra_hunter.ops.backup_runtime import create_backup_bundle
from .ingest import ingest_scan_rows
from .models import AsyncTaskRun


def _job_start(task_id: str, kind: str, payload: dict[str, Any] | None = None) -> AsyncTaskRun:
    obj, _ = AsyncTaskRun.objects.update_or_create(
        task_id=task_id,
        defaults={
            "kind": kind,
            "status": "STARTED",
            "payload_json": payload or {},
            "started_at": timezone.now(),
            "error_message": "",
        },
    )
    return obj


def _job_finish(obj: AsyncTaskRun, ok: bool, result: dict[str, Any]) -> None:
    obj.status = "SUCCESS" if ok else "FAILURE"
    obj.result_json = result
    obj.error_message = ""
    if not ok:
        err = result.get("message") or ""
        if not err and result.get("stderr_tail"):
            err = "\n".join(result["stderr_tail"][-5:])
        obj.error_message = str(err)
    obj.finished_at = timezone.now()
    obj.save(update_fields=["status", "result_json", "error_message", "finished_at"])


def _job_crash(obj: AsyncTaskRun, exc: Exception) -> None:
    obj.status = "FAILURE"
    obj.error_message = str(exc)
    obj.finished_at = timezone.now()
    obj.save(update_fields=["status", "error_message", "finished_at"])


@shared_task(bind=True, name="zhcore.scan_task")
def scan_task(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    job = _job_start(self.request.id, "scan", payload)
    try:
        req = ScanRequest(**payload)
        service = EngineService()
        result = service.run_scan(req)
        if result.get("ok"):
            result.setdefault("data", {})
            result["data"]["ingested"] = ingest_scan_rows(result, req)
        _job_finish(job, bool(result.get("ok")), result)
        return result
    except ValidationError as exc:
        result = {"ok": False, "message": str(exc), "data": {}, "stdout_tail": [], "stderr_tail": []}
        _job_finish(job, False, result)
        return result
    except Exception as exc:
        _job_crash(job, exc)
        raise


@shared_task(bind=True, name="zhcore.performance_task")
def performance_task(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    job = _job_start(self.request.id, "performance", payload)
    try:
        req = PerformanceRequest(**payload)
        result = EngineService().run_performance(req)
        _job_finish(job, bool(result.get("ok")), result)
        return result
    except ValidationError as exc:
        result = {"ok": False, "message": str(exc), "data": {}, "stdout_tail": [], "stderr_tail": []}
        _job_finish(job, False, result)
        return result
    except Exception as exc:
        _job_crash(job, exc)
        raise


@shared_task(bind=True, name="zhcore.update_results_task")
def update_results_task(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    job = _job_start(self.request.id, "update_results", payload)
    try:
        req = UpdateResultsRequest(**payload)
        result = EngineService().run_update_results(req)
        _job_finish(job, bool(result.get("ok")), result)
        return result
    except ValidationError as exc:
        result = {"ok": False, "message": str(exc), "data": {}, "stdout_tail": [], "stderr_tail": []}
        _job_finish(job, False, result)
        return result
    except Exception as exc:
        _job_crash(job, exc)
        raise


@shared_task(bind=True, name="zhcore.analyze_alerts_task")
def analyze_alerts_task(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    job = _job_start(self.request.id, "analyze_alerts", payload)
    try:
        req = AnalyzeAlertsRequest(**payload)
        result = EngineService().run_analyze_alerts(req)
        _job_finish(job, bool(result.get("ok")), result)
        return result
    except ValidationError as exc:
        result = {"ok": False, "message": str(exc), "data": {}, "stdout_tail": [], "stderr_tail": []}
        _job_finish(job, False, result)
        return result
    except Exception as exc:
        _job_crash(job, exc)
        raise


@shared_task(bind=True, name="zhcore.mongo_sync_task")
def mongo_sync_task(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    job = _job_start(self.request.id, "mongo_sync", payload)
    try:
        req = MongoSyncRequest(**payload)
        result = EngineService().run_mongo_sync(req)
        _job_finish(job, bool(result.get("ok")), result)
        return result
    except ValidationError as exc:
        result = {"ok": False, "message": str(exc), "data": {}, "stdout_tail": [], "stderr_tail": []}
        _job_finish(job, False, result)
        return result
    except Exception as exc:
        _job_crash(job, exc)
        raise


@shared_task(bind=True, name="zhcore.backup_task")
def backup_task(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    job = _job_start(self.request.id, "backup", payload)
    try:
        req = BackupRequest(**payload)
        result = create_backup_bundle(
            output_dir=Path(req.output_dir).resolve() if req.output_dir else None,
            include_mongo=req.include_mongo,
            include_dirs=req.include_dirs,
            keep_last=req.keep_last,
        )
        out = {
            "ok": bool(result.get("ok")),
            "message": "backup concluido com sucesso." if result.get("ok") else "falha ao executar backup.",
            "data": result,
            "stdout_tail": [],
            "stderr_tail": [],
        }
        _job_finish(job, bool(out.get("ok")), out)
        return out
    except ValidationError as exc:
        result = {"ok": False, "message": str(exc), "data": {}, "stdout_tail": [], "stderr_tail": []}
        _job_finish(job, False, result)
        return result
    except Exception as exc:
        _job_crash(job, exc)
        raise


@shared_task(name="zhcore.scheduled_scan_task")
def scheduled_scan_task() -> dict[str, Any]:
    payload = {
        "days": int(os.getenv("DJANGO_SCHED_SCAN_DAYS", "1")),
        "top": int(os.getenv("DJANGO_SCHED_SCAN_TOP", "5")),
        "thr": float(os.getenv("DJANGO_SCHED_SCAN_THR", "0.45")),
        "min_books": int(os.getenv("DJANGO_SCHED_SCAN_MIN_BOOKS", "8")),
        "min_conf": float(os.getenv("DJANGO_SCHED_SCAN_MIN_CONF", "0.55")),
        "min_edge": float(os.getenv("DJANGO_SCHED_SCAN_MIN_EDGE", "0.01")),
        "min_ev": float(os.getenv("DJANGO_SCHED_SCAN_MIN_EV", "0.01")),
        "only_future": True,
    }
    req = ScanRequest(**payload)
    result = EngineService().run_scan(req)
    if result.get("ok"):
        result.setdefault("data", {})
        result["data"]["ingested"] = ingest_scan_rows(result, req)
    return result


@shared_task(name="zhcore.scheduled_update_results_task")
def scheduled_update_results_task() -> dict[str, Any]:
    payload = {"days": int(os.getenv("DJANGO_SCHED_UPDATE_RESULTS_DAYS", "2"))}
    req = UpdateResultsRequest(**payload)
    return EngineService().run_update_results(req)


@shared_task(name="zhcore.scheduled_backup_task")
def scheduled_backup_task() -> dict[str, Any]:
    req = BackupRequest(
        output_dir=os.getenv("DJANGO_BACKUP_DIR") or None,
        include_mongo=(os.getenv("DJANGO_BACKUP_INCLUDE_MONGO", "1").strip().lower() in {"1", "true", "yes", "on"}),
        include_dirs=[
            p.strip()
            for p in (os.getenv("DJANGO_BACKUP_INCLUDE_DIRS", "reports,models,data/processed").split(","))
            if p.strip()
        ],
        keep_last=max(1, int(os.getenv("DJANGO_BACKUP_KEEP_LAST", "14"))),
    )
    result = create_backup_bundle(
        output_dir=Path(req.output_dir).resolve() if req.output_dir else None,
        include_mongo=req.include_mongo,
        include_dirs=req.include_dirs,
        keep_last=req.keep_last,
    )
    return {
        "ok": bool(result.get("ok")),
        "message": "backup agendado executado.",
        "data": result,
        "stdout_tail": [],
        "stderr_tail": [],
    }
