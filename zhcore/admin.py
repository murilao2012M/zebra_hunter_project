from __future__ import annotations

from django.contrib import admin

from .models import (
    AsyncTaskRun,
    League,
    LicenseCustomer,
    LicenseDevice,
    LicensePlan,
    LicenseRecord,
    Match,
    ModelArtifact,
    Opportunity,
    OpportunityReview,
    PaymentEvent,
    Pick,
    PublishedPick,
    ScanSession,
    Team,
    UserProfile,
)


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "code", "updated_at")
    search_fields = ("name", "country", "code")
    list_filter = ("country",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "external_id", "updated_at")
    search_fields = ("name", "country", "external_id")
    list_filter = ("country",)


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("fixture_id", "kickoff", "league", "home_team", "away_team", "status")
    search_fields = ("fixture_id", "home_team__name", "away_team__name", "league__name")
    list_filter = ("status", "league")
    autocomplete_fields = ("league", "home_team", "away_team")


@admin.register(ScanSession)
class ScanSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "started_at", "finished_at", "status", "top", "days")
    search_fields = ("id", "source", "status")
    list_filter = ("source", "status", "only_future")


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = ("id", "scan_session", "match", "underdog_team", "ev", "edge", "conf", "tier")
    search_fields = ("match__fixture_id", "underdog_team__name", "match__home_team__name", "match__away_team__name")
    list_filter = ("tier", "scan_session", "match__league")
    autocomplete_fields = ("scan_session", "match", "underdog_team")
    readonly_fields = ("why_entered", "score_breakdown")


@admin.register(Pick)
class PickAdmin(admin.ModelAdmin):
    list_display = ("id", "opportunity", "status", "stake", "profit", "settled_at")
    search_fields = ("id", "opportunity__match__fixture_id")
    list_filter = ("status", "settled_at")
    autocomplete_fields = ("opportunity",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_portal_active", "preferred_language", "updated_at")
    search_fields = ("user__username", "user__email", "display_name")
    list_filter = ("role", "is_portal_active", "preferred_language")
    autocomplete_fields = ("user",)


@admin.register(OpportunityReview)
class OpportunityReviewAdmin(admin.ModelAdmin):
    list_display = ("opportunity", "decision", "reviewed_by", "reviewed_at", "updated_at")
    search_fields = ("opportunity__match__fixture_id", "opportunity__match__home_team__name", "opportunity__match__away_team__name")
    list_filter = ("decision", "reviewed_at")
    autocomplete_fields = ("opportunity", "reviewed_by")


@admin.register(PublishedPick)
class PublishedPickAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "visibility", "published_at", "published_by", "priority", "is_active")
    search_fields = ("title", "slug", "home_team_snapshot", "away_team_snapshot", "underdog_snapshot")
    list_filter = ("status", "visibility", "is_active", "published_at")
    autocomplete_fields = ("opportunity", "published_by")


@admin.register(ModelArtifact)
class ModelArtifactAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "is_active", "created_at")
    search_fields = ("name", "version", "sha256")
    list_filter = ("is_active",)


@admin.register(AsyncTaskRun)
class AsyncTaskRunAdmin(admin.ModelAdmin):
    list_display = ("task_id", "kind", "status", "requested_by", "created_at", "finished_at")
    search_fields = ("task_id", "kind", "requested_by", "error_message")
    list_filter = ("kind", "status")
    readonly_fields = (
        "task_id",
        "kind",
        "status",
        "requested_by",
        "payload_json",
        "result_json",
        "error_message",
        "created_at",
        "started_at",
        "finished_at",
    )


@admin.register(LicensePlan)
class LicensePlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "price_cents", "currency", "billing_days", "trial_days", "max_devices", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active", "currency")


@admin.register(LicenseCustomer)
class LicenseCustomerAdmin(admin.ModelAdmin):
    list_display = ("email", "full_name", "external_reference", "is_active", "last_seen_at")
    search_fields = ("email", "full_name", "external_reference")
    list_filter = ("is_active", "preferred_language")


@admin.register(LicenseRecord)
class LicenseRecordAdmin(admin.ModelAdmin):
    list_display = ("key", "status", "plan", "customer", "max_devices", "current_period_end", "last_validated_at")
    search_fields = ("key", "customer__email", "mercado_pago_external_reference")
    list_filter = ("status", "source", "plan")
    autocomplete_fields = ("customer", "plan")


@admin.register(LicenseDevice)
class LicenseDeviceAdmin(admin.ModelAdmin):
    list_display = ("device_fingerprint", "status", "license", "customer", "platform", "app_version", "last_seen_at")
    search_fields = ("device_fingerprint", "install_id", "external_reference", "hostname")
    list_filter = ("status", "platform", "app_name")
    autocomplete_fields = ("customer", "license", "plan")


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "payment_id", "status", "external_reference", "amount", "currency", "processed_at")
    search_fields = ("provider", "payment_id", "event_id", "external_reference")
    list_filter = ("provider", "status", "currency")
    autocomplete_fields = ("customer", "license")
