from __future__ import annotations

import os
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from zhcore.models import AsyncTaskRun, Match, Opportunity, Pick, ScanSession


APP_STARTED_AT = timezone.now()


def _format_bytes(num: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(num)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{num} B"


def _count_status(window_hours: int = 24) -> dict[str, int]:
    since = timezone.now() - timedelta(hours=window_hours)
    qs = AsyncTaskRun.objects.filter(created_at__gte=since)
    return {
        "pending": qs.filter(status="PENDING").count(),
        "started": qs.filter(status="STARTED").count(),
        "success": qs.filter(status="SUCCESS").count(),
        "failure": qs.filter(status="FAILURE").count(),
        "total": qs.count(),
    }


def collect_ops_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "ok": True,
        "timestamp": timezone.now().isoformat(),
        "uptime_seconds": int((timezone.now() - APP_STARTED_AT).total_seconds()),
        "app_version": "1.0.0",
        "debug": bool(settings.DEBUG),
        "database": {"ok": True, "name": str(settings.DATABASES["default"]["NAME"])},
        "queue": {"pending": 0, "started": 0, "success": 0, "failure": 0, "total": 0},
        "scheduler": {
            "enabled_jobs": sorted(list(settings.CELERY_BEAT_SCHEDULE.keys())),
            "jobs_count": len(settings.CELERY_BEAT_SCHEDULE),
        },
        "storage": {},
        "warnings": [],
    }

    try:
        snapshot["database"]["counts"] = {
            "scans": ScanSession.objects.count(),
            "matches": Match.objects.count(),
            "opportunities": Opportunity.objects.count(),
            "picks": Pick.objects.count(),
            "jobs": AsyncTaskRun.objects.count(),
        }
        snapshot["queue"] = _count_status()
    except (OperationalError, ProgrammingError) as exc:
        snapshot["ok"] = False
        snapshot["database"] = {"ok": False, "error": str(exc)}

    data_path = Path(settings.DATABASES["default"]["NAME"])
    if data_path.exists():
        snapshot["storage"]["sqlite_size"] = _format_bytes(data_path.stat().st_size)
    else:
        snapshot["storage"]["sqlite_size"] = "0 B"
        snapshot["warnings"].append(f"SQLite nao encontrado em {data_path}")

    try:
        usage = shutil.disk_usage(str(Path(settings.BASE_DIR)))
        snapshot["storage"]["disk_total"] = _format_bytes(int(usage.total))
        snapshot["storage"]["disk_used"] = _format_bytes(int(usage.used))
        snapshot["storage"]["disk_free"] = _format_bytes(int(usage.free))
    except Exception as exc:
        snapshot["warnings"].append(f"Falha ao ler disco: {exc}")

    # Security warnings
    if settings.DEBUG:
        snapshot["warnings"].append("DEBUG habilitado: desative em producao.")
    if not settings.ALLOWED_HOSTS:
        snapshot["warnings"].append("ALLOWED_HOSTS vazio.")
    if not getattr(settings, "SESSION_COOKIE_SECURE", False):
        snapshot["warnings"].append("SESSION_COOKIE_SECURE desabilitado.")
    if not getattr(settings, "CSRF_COOKIE_SECURE", False):
        snapshot["warnings"].append("CSRF_COOKIE_SECURE desabilitado.")
    if int(getattr(settings, "SECURE_HSTS_SECONDS", 0)) <= 0:
        snapshot["warnings"].append("HSTS desabilitado (SECURE_HSTS_SECONDS <= 0).")

    monitor_token_set = bool((os.getenv("DJANGO_HEALTH_TOKEN") or "").strip())
    snapshot["monitoring"] = {"token_required": monitor_token_set}

    return snapshot

