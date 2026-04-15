from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class League(models.Model):
    name = models.CharField(max_length=120, db_index=True)
    country = models.CharField(max_length=80, blank=True, default="")
    code = models.CharField(max_length=16, blank=True, default="", db_index=True)
    logo_url = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.country})" if self.country else self.name


class Team(models.Model):
    name = models.CharField(max_length=140, db_index=True)
    external_id = models.CharField(max_length=40, blank=True, default="", db_index=True)
    country = models.CharField(max_length=80, blank=True, default="")
    logo_url = models.URLField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "country"], name="uniq_team_name_country"),
        ]

    def __str__(self) -> str:
        return self.name


class Match(models.Model):
    STATUS_CHOICES = [
        ("NS", "Nao iniciado"),
        ("LIVE", "Ao vivo"),
        ("FT", "Encerrado"),
        ("AET", "Prorrogacao"),
        ("PEN", "Penaltis"),
        ("PST", "Adiado"),
        ("CANC", "Cancelado"),
    ]

    fixture_id = models.CharField(max_length=40, unique=True, db_index=True)
    kickoff = models.DateTimeField(db_index=True)
    league = models.ForeignKey(League, on_delete=models.PROTECT, related_name="matches")
    home_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="home_matches")
    away_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="away_matches")
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default="NS", db_index=True)
    home_score = models.IntegerField(null=True, blank=True)
    away_score = models.IntegerField(null=True, blank=True)
    source = models.CharField(max_length=24, default="api_sports")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-kickoff"]

    def __str__(self) -> str:
        return f"{self.home_team} x {self.away_team} ({self.kickoff:%Y-%m-%d %H:%M})"


class ScanSession(models.Model):
    SOURCE_CHOICES = [
        ("desktop", "Desktop"),
        ("engine_api", "Engine API"),
        ("django", "Django"),
    ]

    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default="django")
    started_at = models.DateTimeField(db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True, db_index=True)
    days = models.IntegerField(default=1)
    top = models.IntegerField(default=5)
    min_books = models.IntegerField(default=8)
    min_conf = models.FloatField(default=0.55)
    min_edge = models.FloatField(default=0.01)
    min_ev = models.FloatField(default=0.01)
    market_thr = models.FloatField(default=0.45)
    only_future = models.BooleanField(default=True)
    status = models.CharField(max_length=16, default="running", db_index=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Scan {self.id} [{self.status}] {self.started_at:%Y-%m-%d %H:%M}"


class Opportunity(models.Model):
    TIER_CHOICES = [("A", "A"), ("B", "B"), ("C", "C")]

    scan_session = models.ForeignKey(ScanSession, on_delete=models.CASCADE, related_name="opportunities")
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="opportunities")
    underdog_team = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="underdog_opportunities")
    odd_best = models.FloatField(default=0.0)
    p_market = models.FloatField(default=0.0)
    p_model = models.FloatField(default=0.0)
    p_api = models.FloatField(default=0.0)
    p_final = models.FloatField(default=0.0)
    edge = models.FloatField(default=0.0)
    ev = models.FloatField(default=0.0)
    conf = models.FloatField(default=0.0)
    score = models.FloatField(default=0.0)
    books = models.IntegerField(default=0)
    tier = models.CharField(max_length=1, choices=TIER_CHOICES, default="C")
    why_entered = models.TextField(blank=True, default="")
    score_breakdown = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["scan_session", "-score"]),
            models.Index(fields=["-ev", "-edge"]),
        ]

    def __str__(self) -> str:
        return f"{self.match} | EV {self.ev:.2%} | Edge {self.edge:.2%}"


class Pick(models.Model):
    RESULT_CHOICES = [
        ("O", "Aberta"),
        ("G", "Ganho"),
        ("P", "Perda"),
        ("E", "Empate"),
        ("V", "Void"),
    ]

    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name="picks")
    stake = models.FloatField(default=0.0)
    status = models.CharField(max_length=1, choices=RESULT_CHOICES, default="O", db_index=True)
    profit = models.FloatField(default=0.0)
    settled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Pick {self.id} [{self.status}] lucro={self.profit:.2f}"


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ("member", "Membro"),
        ("analyst", "Analista"),
        ("admin", "Administrador"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portal_profile")
    display_name = models.CharField(max_length=120, blank=True, default="")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default="member", db_index=True)
    preferred_language = models.CharField(max_length=16, default="pt-BR")
    is_portal_active = models.BooleanField(default=True, db_index=True)
    accepted_terms_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self) -> str:
        return self.display_name or self.user.get_username()

    @property
    def effective_role(self) -> str:
        if self.user.is_superuser:
            return "admin"
        if self.user.is_staff and self.role == "member":
            return "analyst"
        return self.role

    @property
    def can_access_backoffice(self) -> bool:
        return self.effective_role in {"analyst", "admin"}


class LicensePlan(models.Model):
    code = models.SlugField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    price_cents = models.PositiveIntegerField(default=2900)
    currency = models.CharField(max_length=8, default="BRL")
    billing_days = models.PositiveIntegerField(default=30)
    trial_days = models.PositiveIntegerField(default=30)
    max_devices = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True, db_index=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class LicenseCustomer(models.Model):
    email = models.EmailField(blank=True, default="", db_index=True)
    full_name = models.CharField(max_length=160, blank=True, default="")
    external_reference = models.CharField(max_length=80, unique=True, db_index=True)
    preferred_language = models.CharField(max_length=16, default="pt-BR")
    is_active = models.BooleanField(default=True, db_index=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["email", "external_reference"]

    def __str__(self) -> str:
        return self.email or self.external_reference


class LicenseRecord(models.Model):
    STATUS_CHOICES = [
        ("trial", "Trial"),
        ("active", "Ativa"),
        ("past_due", "Pagamento pendente"),
        ("expired", "Expirada"),
        ("cancelled", "Cancelada"),
        ("blocked", "Bloqueada"),
    ]
    SOURCE_CHOICES = [
        ("manual", "Manual"),
        ("trial", "Trial"),
        ("mercado_pago", "Mercado Pago"),
        ("admin", "Admin"),
        ("migration", "Migracao"),
    ]

    key = models.CharField(max_length=64, unique=True, db_index=True)
    customer = models.ForeignKey(
        "LicenseCustomer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="licenses",
    )
    plan = models.ForeignKey("LicensePlan", on_delete=models.PROTECT, related_name="licenses")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="active", db_index=True)
    source = models.CharField(max_length=24, choices=SOURCE_CHOICES, default="manual", db_index=True)
    max_devices = models.PositiveIntegerField(default=1)
    issued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    activated_at = models.DateTimeField(null=True, blank=True, db_index=True)
    current_period_start = models.DateTimeField(null=True, blank=True, db_index=True)
    current_period_end = models.DateTimeField(null=True, blank=True, db_index=True)
    last_validated_at = models.DateTimeField(null=True, blank=True, db_index=True)
    mercado_pago_external_reference = models.CharField(max_length=120, blank=True, default="", db_index=True)
    mercado_pago_preference_id = models.CharField(max_length=120, blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.key} [{self.status}]"


class LicenseDevice(models.Model):
    STATUS_CHOICES = [
        ("trial", "Trial"),
        ("active", "Ativo"),
        ("blocked", "Bloqueado"),
        ("revoked", "Revogado"),
    ]

    device_fingerprint = models.CharField(max_length=128, unique=True, db_index=True)
    install_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    external_reference = models.CharField(max_length=120, unique=True, db_index=True)
    customer = models.ForeignKey(
        "LicenseCustomer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devices",
    )
    license = models.ForeignKey(
        "LicenseRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devices",
    )
    plan = models.ForeignKey(
        "LicensePlan",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="devices",
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="trial", db_index=True)
    hostname = models.CharField(max_length=160, blank=True, default="")
    platform = models.CharField(max_length=80, blank=True, default="")
    app_name = models.CharField(max_length=120, blank=True, default="")
    app_version = models.CharField(max_length=40, blank=True, default="")
    trial_started_at = models.DateTimeField(null=True, blank=True, db_index=True)
    trial_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    checkout_url = models.URLField(blank=True, default="")
    checkout_preference_id = models.CharField(max_length=120, blank=True, default="")
    checkout_created_at = models.DateTimeField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self) -> str:
        return f"{self.device_fingerprint[:12]} [{self.status}]"


class PaymentEvent(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pendente"),
        ("approved", "Aprovado"),
        ("authorized", "Autorizado"),
        ("rejected", "Rejeitado"),
        ("cancelled", "Cancelado"),
        ("refunded", "Estornado"),
        ("unknown", "Desconhecido"),
    ]

    provider = models.CharField(max_length=40, default="mercado_pago", db_index=True)
    event_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    payment_id = models.CharField(max_length=120, blank=True, default="", db_index=True)
    event_type = models.CharField(max_length=80, blank=True, default="", db_index=True)
    action = models.CharField(max_length=80, blank=True, default="")
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="pending", db_index=True)
    external_reference = models.CharField(max_length=120, blank=True, default="", db_index=True)
    customer = models.ForeignKey(
        "LicenseCustomer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_events",
    )
    license = models.ForeignKey(
        "LicenseRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_events",
    )
    amount = models.FloatField(default=0.0)
    currency = models.CharField(max_length=8, default="BRL")
    payload_json = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "payment_id"],
                condition=~models.Q(payment_id=""),
                name="uniq_payment_provider_payment_id",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.payment_id or self.event_id} [{self.status}]"


class OpportunityReview(models.Model):
    DECISION_CHOICES = [
        ("pending", "Pendente"),
        ("approved", "Aprovada"),
        ("rejected", "Rejeitada"),
        ("published", "Publicada"),
    ]

    opportunity = models.OneToOneField(Opportunity, on_delete=models.CASCADE, related_name="review")
    decision = models.CharField(max_length=16, choices=DECISION_CHOICES, default="pending", db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="opportunity_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    public_reason = models.CharField(max_length=240, blank=True, default="")
    private_note = models.TextField(blank=True, default="")
    risk_note = models.CharField(max_length=240, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Review oportunidade {self.opportunity_id} [{self.decision}]"


class PublishedPick(models.Model):
    VISIBILITY_CHOICES = [
        ("members", "Membros"),
        ("private", "Privada"),
    ]
    STATUS_CHOICES = [
        ("scheduled", "Agendada"),
        ("live", "Ao vivo"),
        ("won", "Ganha"),
        ("lost", "Perdida"),
        ("draw", "Empate"),
        ("void", "Void"),
        ("archived", "Arquivada"),
    ]

    opportunity = models.OneToOneField(Opportunity, on_delete=models.CASCADE, related_name="published_pick")
    slug = models.SlugField(max_length=240, unique=True, db_index=True, blank=True)
    title = models.CharField(max_length=220, blank=True, default="")
    short_reason = models.CharField(max_length=240, blank=True, default="")
    public_note = models.TextField(blank=True, default="")
    visibility = models.CharField(max_length=16, choices=VISIBILITY_CHOICES, default="members", db_index=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_picks",
    )
    published_at = models.DateTimeField(auto_now_add=True, db_index=True)
    kickoff_snapshot = models.DateTimeField(null=True, blank=True, db_index=True)
    league_name_snapshot = models.CharField(max_length=120, blank=True, default="")
    country_snapshot = models.CharField(max_length=80, blank=True, default="")
    home_team_snapshot = models.CharField(max_length=140, blank=True, default="")
    away_team_snapshot = models.CharField(max_length=140, blank=True, default="")
    underdog_snapshot = models.CharField(max_length=140, blank=True, default="")
    odd_snapshot = models.FloatField(default=0.0)
    ev_snapshot = models.FloatField(default=0.0)
    edge_snapshot = models.FloatField(default=0.0)
    conf_snapshot = models.FloatField(default=0.0)
    p_final_snapshot = models.FloatField(default=0.0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="scheduled", db_index=True)
    result_label = models.CharField(max_length=8, blank=True, default="")
    result_profit = models.FloatField(default=0.0)
    priority = models.IntegerField(default=0, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    settled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-priority"]

    def __str__(self) -> str:
        return self.title or f"Publicado {self.opportunity_id}"

    def save(self, *args, **kwargs):
        match = self.opportunity.match if self.opportunity_id else None
        if match:
            if not self.title:
                self.title = f"{match.home_team.name} x {match.away_team.name}"
            if not self.kickoff_snapshot:
                self.kickoff_snapshot = match.kickoff
            if not self.league_name_snapshot:
                self.league_name_snapshot = match.league.name
            if not self.country_snapshot:
                self.country_snapshot = match.league.country
            if not self.home_team_snapshot:
                self.home_team_snapshot = match.home_team.name
            if not self.away_team_snapshot:
                self.away_team_snapshot = match.away_team.name
            if not self.underdog_snapshot:
                self.underdog_snapshot = self.opportunity.underdog_team.name
        if not self.odd_snapshot:
            self.odd_snapshot = self.opportunity.odd_best
        if not self.ev_snapshot:
            self.ev_snapshot = self.opportunity.ev
        if not self.edge_snapshot:
            self.edge_snapshot = self.opportunity.edge
        if not self.conf_snapshot:
            self.conf_snapshot = self.opportunity.conf
        if not self.p_final_snapshot:
            self.p_final_snapshot = self.opportunity.p_final
        if not self.slug:
            base_slug = slugify(f"{self.title or 'pick'}-{self.opportunity_id}")[:220]
            self.slug = base_slug or f"pick-{self.opportunity_id}"
        super().save(*args, **kwargs)


class ModelArtifact(models.Model):
    name = models.CharField(max_length=120, db_index=True)
    version = models.CharField(max_length=40, db_index=True)
    path = models.CharField(max_length=320)
    sha256 = models.CharField(max_length=128, blank=True, default="")
    is_active = models.BooleanField(default=False, db_index=True)
    metrics_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["name", "version"], name="uniq_model_name_version"),
        ]

    def __str__(self) -> str:
        return f"{self.name}:{self.version}"


class AsyncTaskRun(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pendente"),
        ("STARTED", "Iniciado"),
        ("SUCCESS", "Sucesso"),
        ("FAILURE", "Falha"),
    ]

    task_id = models.CharField(max_length=80, unique=True, db_index=True)
    kind = models.CharField(max_length=40, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="PENDING", db_index=True)
    requested_by = models.CharField(max_length=150, blank=True, default="")
    payload_json = models.JSONField(default=dict, blank=True)
    result_json = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind}:{self.task_id} [{self.status}]"
