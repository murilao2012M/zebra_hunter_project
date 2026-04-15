from __future__ import annotations

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from . import api_views
from .views import (
    backoffice_dashboard_view,
    backoffice_review_action_view,
    backoffice_review_view,
    member_dashboard_view,
    member_pick_detail_view,
    post_login_redirect_view,
    public_home_view,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/public/license/status/", api_views.api_public_license_status, name="api_public_license_status"),
    path("api/public/license/checkout/", api_views.api_public_license_checkout, name="api_public_license_checkout"),
    path("api/public/payments/mercadopago/webhook/", api_views.api_public_mercadopago_webhook, name="api_public_mercadopago_webhook"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/redirect/", post_login_redirect_view, name="post_login_redirect"),
    path("", public_home_view, name="public_home"),
    path("app/", member_dashboard_view, name="member_dashboard"),
    path("app/picks/<slug:slug>/", member_pick_detail_view, name="member_pick_detail"),
    path("backoffice/", backoffice_dashboard_view, name="backoffice_dashboard"),
    path("backoffice/review/", backoffice_review_view, name="backoffice_review"),
    path("backoffice/review/<int:opportunity_id>/action/", backoffice_review_action_view, name="backoffice_review_action"),
    path("api/health/", api_views.api_health, name="api_health"),
    path("api/ops/healthz/", api_views.api_ops_healthz, name="api_ops_healthz"),
    path("api/ops/metrics/", api_views.api_ops_metrics, name="api_ops_metrics"),
    path("api/dashboard/summary/", api_views.api_dashboard_summary, name="api_dashboard_summary"),
    path("api/portal/feed/", api_views.api_portal_feed, name="api_portal_feed"),
    path("api/backoffice/candidates/", api_views.api_backoffice_candidates, name="api_backoffice_candidates"),
    path("api/scanner/run/", api_views.api_scan_run, name="api_scan_run"),
    path("api/scanner/enqueue/", api_views.api_scan_enqueue, name="api_scan_enqueue"),
    path("api/performance/run/", api_views.api_performance_run, name="api_performance_run"),
    path("api/performance/enqueue/", api_views.api_performance_enqueue, name="api_performance_enqueue"),
    path("api/operations/update-results/", api_views.api_update_results_run, name="api_update_results_run"),
    path("api/operations/update-results/enqueue/", api_views.api_update_results_enqueue, name="api_update_results_enqueue"),
    path("api/operations/analyze-alerts/", api_views.api_analyze_alerts_run, name="api_analyze_alerts_run"),
    path("api/operations/analyze-alerts/enqueue/", api_views.api_analyze_alerts_enqueue, name="api_analyze_alerts_enqueue"),
    path("api/operations/backup/enqueue/", api_views.api_backup_enqueue, name="api_backup_enqueue"),
    path("api/mongo-sync/enqueue/", api_views.api_mongo_sync_enqueue, name="api_mongo_sync_enqueue"),
    path("api/jobs/<str:task_id>/", api_views.api_job_status, name="api_job_status"),
]
