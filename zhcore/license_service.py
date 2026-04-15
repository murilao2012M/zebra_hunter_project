from __future__ import annotations

import hashlib
import os
import secrets
from datetime import timedelta
from decimal import Decimal
from typing import Any

import requests
from django.db import transaction
from django.utils import timezone

from .models import LicenseCustomer, LicenseDevice, LicensePlan, LicenseRecord, PaymentEvent


def _env_str(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name, str(default))
    try:
        return int(raw)
    except Exception:
        return int(default)


def _env_decimal(name: str, default: str) -> Decimal:
    raw = _env_str(name, default).replace(",", ".")
    try:
        return Decimal(raw)
    except Exception:
        return Decimal(default)


def _make_license_key() -> str:
    return f"ZEBRA-{timezone.now():%Y}-{secrets.token_hex(4).upper()}"


def _make_customer_reference(seed: str) -> str:
    normalized = seed.strip().lower() if seed else secrets.token_hex(8)
    return f"cust_{hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:18]}"


def _make_device_reference(device_fingerprint: str) -> str:
    return f"zbh_{hashlib.sha1(device_fingerprint.encode('utf-8')).hexdigest()[:24]}"


def _payment_url_fallback() -> str:
    return _env_str("LICENSE_PAYMENT_URL") or _env_str("PAYMENT_URL")


def _bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _days_left(deadline) -> int:
    if not deadline:
        return 0
    remaining = (deadline - timezone.now()).total_seconds()
    if remaining <= 0:
        return 0
    return max(0, int((remaining + 86399) // 86400))


def _base_payload(ok: bool, status: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"ok": bool(ok), "status": str(status), "message": str(message)}
    payload.update(extra)
    return payload


def ensure_default_license_plan() -> LicensePlan:
    code = _env_str("LICENSE_PLAN_CODE", "pro-monthly")
    defaults = {
        "name": _env_str("LICENSE_PRODUCT_NAME", "Zebra Hunter Quantum Pro Mensal"),
        "price_cents": int(_env_decimal("LICENSE_PRICE_BRL", "29.00") * 100),
        "currency": _env_str("LICENSE_CURRENCY", "BRL"),
        "billing_days": _env_int("LICENSE_BILLING_DAYS", 30),
        "trial_days": _env_int("LICENSE_TRIAL_DAYS", 30),
        "max_devices": _env_int("LICENSE_MAX_DEVICES", 1),
        "is_active": True,
    }
    plan, _ = LicensePlan.objects.get_or_create(code=code, defaults=defaults)
    changed = False
    for key, value in defaults.items():
        if getattr(plan, key) != value:
            setattr(plan, key, value)
            changed = True
    if changed:
        plan.save(
            update_fields=[
                "name",
                "price_cents",
                "currency",
                "billing_days",
                "trial_days",
                "max_devices",
                "is_active",
                "updated_at",
            ]
        )
    return plan


def _customer_from_payload(payload: dict[str, Any]) -> LicenseCustomer | None:
    email = _env_str("LICENSE_PAYER_EMAIL") or str(payload.get("email") or payload.get("payer_email") or "").strip().lower()
    full_name = str(payload.get("full_name") or payload.get("payer_name") or "").strip()
    if not email and not full_name:
        return None
    external_reference = _make_customer_reference(email or full_name)
    customer, _ = LicenseCustomer.objects.get_or_create(
        external_reference=external_reference,
        defaults={"email": email, "full_name": full_name},
    )
    changed = False
    if email and customer.email != email:
        customer.email = email
        changed = True
    if full_name and customer.full_name != full_name:
        customer.full_name = full_name
        changed = True
    if changed:
        customer.save(update_fields=["email", "full_name", "last_seen_at"])
    return customer


def _upsert_device(payload: dict[str, Any], plan: LicensePlan, customer: LicenseCustomer | None) -> LicenseDevice:
    device_fingerprint = str(payload.get("device_id") or "").strip()
    if not device_fingerprint:
        raise ValueError("device_id obrigatorio para o licenciamento server-side.")
    install_id = str(payload.get("install_id") or "").strip()
    defaults = {
        "install_id": install_id,
        "external_reference": _make_device_reference(device_fingerprint),
        "customer": customer,
        "plan": plan,
        "status": "trial",
        "hostname": str(payload.get("hostname") or "").strip(),
        "platform": str(payload.get("platform") or "").strip(),
        "app_name": str(payload.get("app_name") or "").strip(),
        "app_version": str(payload.get("app_version") or "").strip(),
    }
    device, _ = LicenseDevice.objects.get_or_create(device_fingerprint=device_fingerprint, defaults=defaults)
    changed = False
    for field in ("install_id", "hostname", "platform", "app_name", "app_version"):
        value = str(payload.get(field) or "").strip()
        if value and getattr(device, field) != value:
            setattr(device, field, value)
            changed = True
    if device.plan_id != plan.id:
        device.plan = plan
        changed = True
    if customer and device.customer_id != customer.id:
        device.customer = customer
        changed = True
    metadata = device.metadata_json or {}
    for key in ("app_build", "channel"):
        value = str(payload.get(key) or "").strip()
        if value:
            metadata[key] = value
    if metadata != (device.metadata_json or {}):
        device.metadata_json = metadata
        changed = True
    if changed:
        device.save()
    return device


def _license_needs_expire(license_obj: LicenseRecord) -> bool:
    if license_obj.status != "active":
        return False
    return bool(license_obj.current_period_end and timezone.now() > license_obj.current_period_end)


def _license_result(license_obj: LicenseRecord, message: str = "Licenca valida.") -> dict[str, Any]:
    days_left = _days_left(license_obj.current_period_end)
    return _base_payload(
        True,
        "active",
        message,
        license_key=license_obj.key,
        plan=(license_obj.plan.code if license_obj.plan_id else ""),
        expires_at=license_obj.current_period_end.isoformat() if license_obj.current_period_end else None,
        days_left=days_left,
        max_devices=int(license_obj.max_devices or (license_obj.plan.max_devices if license_obj.plan_id else 1) or 1),
        pay_url=_payment_url_fallback(),
    )


def _trial_result(device: LicenseDevice) -> dict[str, Any]:
    days_left = _days_left(device.trial_expires_at)
    return _base_payload(
        True,
        "trial",
        f"Trial ativo. Restam {days_left} dias.",
        days_left=days_left,
        trial_expires_at=device.trial_expires_at.isoformat() if device.trial_expires_at else None,
        pay_url=device.checkout_url or _payment_url_fallback(),
    )


def _count_other_active_devices(license_obj: LicenseRecord, device: LicenseDevice) -> int:
    return (
        LicenseDevice.objects.filter(license=license_obj, status="active")
        .exclude(pk=device.pk)
        .count()
    )


def _bind_device_to_license(device: LicenseDevice, license_obj: LicenseRecord, customer: LicenseCustomer | None) -> None:
    device.license = license_obj
    device.plan = license_obj.plan
    device.customer = customer or license_obj.customer
    device.status = "active"
    device.save(update_fields=["license", "plan", "customer", "status", "updated_at", "last_seen_at"])
    license_obj.last_validated_at = timezone.now()
    if not license_obj.activated_at:
        license_obj.activated_at = timezone.now()
    license_obj.save(update_fields=["last_validated_at", "activated_at", "updated_at"])


def check_license_status(payload: dict[str, Any]) -> dict[str, Any]:
    plan = ensure_default_license_plan()
    customer = _customer_from_payload(payload)
    try:
        device = _upsert_device(payload, plan, customer)
    except ValueError as exc:
        return _base_payload(False, "missing", str(exc), pay_url=_payment_url_fallback())

    if device.license_id:
        license_obj = device.license
        if license_obj and _license_needs_expire(license_obj):
            license_obj.status = "expired"
            license_obj.save(update_fields=["status", "updated_at"])
            device.status = "blocked"
            device.save(update_fields=["status", "updated_at"])
        elif license_obj and license_obj.status == "active":
            _bind_device_to_license(device, license_obj, customer)
            return _license_result(license_obj, "Licenca valida para este dispositivo.")

    license_key = str(payload.get("license_key") or "").strip()
    if license_key:
        license_obj = LicenseRecord.objects.select_related("plan", "customer").filter(key=license_key).first()
        if not license_obj:
            return _base_payload(False, "invalid", "Licenca nao encontrada.", pay_url=device.checkout_url or _payment_url_fallback())
        if _license_needs_expire(license_obj):
            license_obj.status = "expired"
            license_obj.save(update_fields=["status", "updated_at"])
        if license_obj.status != "active":
            return _base_payload(
                False,
                license_obj.status,
                f"Licenca {license_obj.status}.",
                pay_url=device.checkout_url or _payment_url_fallback(),
            )
        max_devices = int(license_obj.max_devices or (license_obj.plan.max_devices if license_obj.plan_id else 1) or 1)
        if device.license_id != license_obj.id and _count_other_active_devices(license_obj, device) >= max_devices:
            return _base_payload(
                False,
                "device_limit",
                "Limite de dispositivos desta licenca foi atingido.",
                pay_url=device.checkout_url or _payment_url_fallback(),
            )
        _bind_device_to_license(device, license_obj, customer)
        return _license_result(license_obj)

    if not device.trial_started_at:
        now = timezone.now()
        device.trial_started_at = now
        device.trial_expires_at = now + timedelta(days=int(plan.trial_days or 30))
        device.status = "trial"
        device.save(update_fields=["trial_started_at", "trial_expires_at", "status", "updated_at"])
    if device.trial_expires_at and timezone.now() <= device.trial_expires_at:
        if device.status != "trial":
            device.status = "trial"
            device.save(update_fields=["status", "updated_at"])
        return _trial_result(device)

    device.status = "blocked"
    device.save(update_fields=["status", "updated_at"])
    return _base_payload(
        False,
        "trial_expired",
        "Trial expirou. Realize o pagamento para liberar o acesso.",
        days_left=0,
        pay_url=device.checkout_url or _payment_url_fallback(),
        external_reference=device.external_reference,
    )


def _build_notification_url() -> str:
    base = _env_str("DJANGO_PUBLIC_BASE_URL").rstrip("/")
    if not base:
        return ""
    token = _env_str("MERCADO_PAGO_WEBHOOK_TOKEN")
    url = f"{base}/api/public/payments/mercadopago/webhook/"
    if token:
        url = f"{url}?token={token}"
    return url


def _build_back_urls() -> dict[str, str]:
    urls = {
        "success": _env_str("MERCADO_PAGO_SUCCESS_URL"),
        "pending": _env_str("MERCADO_PAGO_PENDING_URL"),
        "failure": _env_str("MERCADO_PAGO_FAILURE_URL"),
    }
    return {k: v for k, v in urls.items() if v}


def _mercado_pago_headers() -> dict[str, str]:
    token = _env_str("MERCADO_PAGO_ACCESS_TOKEN")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": secrets.token_hex(16),
    }


def _ensure_checkout_url(device: LicenseDevice, plan: LicensePlan, customer: LicenseCustomer | None) -> str:
    fallback = _payment_url_fallback()
    access_token = _env_str("MERCADO_PAGO_ACCESS_TOKEN")
    if not access_token:
        return fallback
    if device.checkout_url and device.checkout_created_at:
        age_seconds = (timezone.now() - device.checkout_created_at).total_seconds()
        if age_seconds <= 1800:
            return device.checkout_url

    unit_price = float(plan.price_cents or 2900) / 100.0
    payload: dict[str, Any] = {
        "items": [
            {
                "id": plan.code,
                "title": _env_str("LICENSE_PRODUCT_NAME", "Zebra Hunter Quantum Pro"),
                "description": "Assinatura mensal do Zebra Hunter",
                "quantity": 1,
                "currency_id": plan.currency or "BRL",
                "unit_price": unit_price,
            }
        ],
        "external_reference": device.external_reference,
        "metadata": {
            "device_fingerprint": device.device_fingerprint,
            "install_id": device.install_id,
            "plan_code": plan.code,
        },
    }
    notification_url = _build_notification_url()
    if notification_url:
        payload["notification_url"] = notification_url
    back_urls = _build_back_urls()
    if back_urls:
        payload["back_urls"] = back_urls
        payload["auto_return"] = "approved"
    if customer and customer.email:
        payload["payer"] = {"email": customer.email}

    response = requests.post(
        "https://api.mercadopago.com/checkout/preferences",
        headers=_mercado_pago_headers(),
        json=payload,
        timeout=12,
    )
    response.raise_for_status()
    data = response.json() if response.content else {}
    checkout_url = str(data.get("init_point") or data.get("sandbox_init_point") or "").strip()
    if checkout_url:
        device.checkout_url = checkout_url
        device.checkout_preference_id = str(data.get("id") or "").strip()
        device.checkout_created_at = timezone.now()
        device.save(update_fields=["checkout_url", "checkout_preference_id", "checkout_created_at", "updated_at"])
        return checkout_url
    return fallback


def create_checkout_session(payload: dict[str, Any]) -> dict[str, Any]:
    plan = ensure_default_license_plan()
    customer = _customer_from_payload(payload)
    try:
        device = _upsert_device(payload, plan, customer)
    except ValueError as exc:
        return _base_payload(False, "missing", str(exc), pay_url=_payment_url_fallback())
    try:
        checkout_url = _ensure_checkout_url(device, plan, customer)
    except Exception as exc:
        return _base_payload(False, "checkout_error", f"Falha ao criar checkout: {exc}", pay_url=_payment_url_fallback())
    if not checkout_url:
        return _base_payload(False, "not_configured", "Pagamento nao configurado.", pay_url=_payment_url_fallback())
    return _base_payload(
        True,
        "checkout_ready",
        "Checkout pronto.",
        pay_url=checkout_url,
        external_reference=device.external_reference,
        plan=plan.code,
        price_brl=float(plan.price_cents or 2900) / 100.0,
    )


def _payment_status(raw_status: str) -> str:
    normalized = str(raw_status or "").strip().lower()
    if normalized in {"approved", "authorized", "rejected", "cancelled", "refunded"}:
        return normalized
    if normalized in {"pending", "in_process"}:
        return "pending"
    return "unknown"


def _fetch_mercado_pago_payment(payment_id: str) -> dict[str, Any]:
    token = _env_str("MERCADO_PAGO_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("MERCADO_PAGO_ACCESS_TOKEN nao configurado.")
    response = requests.get(
        f"https://api.mercadopago.com/v1/payments/{payment_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=12,
    )
    response.raise_for_status()
    return response.json() if response.content else {}


def _activate_from_payment(payment_payload: dict[str, Any]) -> LicenseRecord | None:
    external_reference = str(payment_payload.get("external_reference") or "").strip()
    if not external_reference:
        return None
    device = LicenseDevice.objects.select_related("license", "plan", "customer").filter(external_reference=external_reference).first()
    if not device:
        return None
    plan = device.plan or ensure_default_license_plan()
    payer = payment_payload.get("payer") or {}
    customer = device.customer or _customer_from_payload(
        {
            "email": payer.get("email") or "",
            "payer_name": " ".join(
                part for part in [str(payer.get("first_name") or "").strip(), str(payer.get("last_name") or "").strip()] if part
            ),
        }
    )
    license_obj = device.license
    if not license_obj:
        license_obj = LicenseRecord.objects.create(
            key=_make_license_key(),
            customer=customer,
            plan=plan,
            status="active",
            source="mercado_pago",
            max_devices=int(plan.max_devices or 1),
            mercado_pago_external_reference=external_reference,
        )
    now = timezone.now()
    if license_obj.current_period_end and license_obj.current_period_end > now:
        period_start = license_obj.current_period_end
    else:
        period_start = now
    license_obj.customer = customer or license_obj.customer
    license_obj.plan = plan
    license_obj.status = "active"
    license_obj.source = "mercado_pago"
    license_obj.max_devices = int(license_obj.max_devices or plan.max_devices or 1)
    license_obj.current_period_start = period_start
    license_obj.current_period_end = period_start + timedelta(days=int(plan.billing_days or 30))
    license_obj.activated_at = license_obj.activated_at or now
    license_obj.last_validated_at = now
    license_obj.mercado_pago_external_reference = external_reference
    license_obj.save()

    device.license = license_obj
    device.plan = plan
    device.customer = customer or device.customer
    device.status = "active"
    device.save(update_fields=["license", "plan", "customer", "status", "updated_at"])
    return license_obj


@transaction.atomic
def process_mercado_pago_webhook(body: dict[str, Any], query_params: dict[str, Any], headers: dict[str, Any]) -> dict[str, Any]:
    expected_token = _env_str("MERCADO_PAGO_WEBHOOK_TOKEN")
    if expected_token:
        provided = str(query_params.get("token") or headers.get("X-Zebra-Webhook-Token") or "").strip()
        if not secrets.compare_digest(expected_token, provided):
            return _base_payload(False, "unauthorized", "Token do webhook invalido.")

    event_type = str(body.get("type") or body.get("topic") or query_params.get("type") or query_params.get("topic") or "payment").strip()
    action = str(body.get("action") or query_params.get("action") or "").strip()
    data = body.get("data") or {}
    payment_id = str(data.get("id") or query_params.get("data.id") or query_params.get("id") or "").strip()
    event_id = str(body.get("id") or payment_id or secrets.token_hex(8)).strip()
    lookup_payment_id = payment_id or f"event:{event_id}"

    payment_event, _ = PaymentEvent.objects.get_or_create(
        provider="mercado_pago",
        payment_id=lookup_payment_id,
        defaults={"event_id": event_id, "event_type": event_type, "action": action, "payload_json": body or {}},
    )
    payment_event.event_id = event_id
    payment_event.event_type = event_type
    payment_event.action = action
    payment_event.payload_json = body or {}
    payment_event.save(update_fields=["event_id", "event_type", "action", "payload_json", "updated_at"])

    if not payment_id:
        return _base_payload(True, "ignored", "Webhook recebido sem payment_id.", processed=False)

    payment_payload = _fetch_mercado_pago_payment(payment_id)
    payment_event.external_reference = str(payment_payload.get("external_reference") or "").strip()
    payment_event.amount = float(payment_payload.get("transaction_amount") or 0.0)
    payment_event.currency = str(payment_payload.get("currency_id") or "BRL")
    payment_event.status = _payment_status(payment_payload.get("status") or "")
    payment_event.payload_json = payment_payload

    license_obj = None
    if payment_event.status == "approved" and not payment_event.processed_at:
        license_obj = _activate_from_payment(payment_payload)
        payment_event.processed_at = timezone.now()
        payment_event.license = license_obj
        if license_obj and license_obj.customer_id:
            payment_event.customer = license_obj.customer
    payment_event.save()

    return _base_payload(
        True,
        payment_event.status,
        "Webhook processado.",
        processed=bool(payment_event.processed_at),
        license_key=(license_obj.key if license_obj else None),
        external_reference=payment_event.external_reference,
    )
