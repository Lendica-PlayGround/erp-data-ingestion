"""Company and membership models for AR management."""

from datetime import time
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from .base import BaseModel

__all__ = [
    "Company",
    "CompanyMembership",
    "CompanyInvitation",
    "CompanyInvitationLog",
    "CompanyContact",
    "CompanyARPolicy",
]


def default_dunning_trigger_offsets() -> list[int]:
    """Legacy default kept for historical migration imports."""
    return [-3, -1, 0, 1, 3, 7]


class CompanyQuerySet(models.QuerySet):
    def with_total_balance(self):
        """Annotate each company with the sum of its open invoice balances."""
        return self.annotate(
            total_balance=Coalesce(
                Sum("invoice__balance", filter=Q(invoice__balance__gt=0)),
                Value(Decimal("0")),
                output_field=DecimalField(),
            )
        )


def default_dunning_allowed_weekdays() -> list[int]:
    """Legacy default kept for historical migration imports."""
    return [0, 1, 2, 3, 4, 5, 6]


def default_dunning_send_time() -> time:
    """Legacy default kept for historical migration imports."""
    return time(hour=9, minute=0)


class CompanyRole(models.IntegerChoices):
    OWNER = 1, "Owner"
    ADMIN = 2, "Admin"
    OPERATIONS = 3, "Operations"


class Company(BaseModel):
    """Company model for AR management"""

    # Basic company info
    company_name = models.CharField(max_length=200)
    monthly_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    ein = models.CharField(
        max_length=20, blank=True, help_text="Employer Identification Number (Tax ID)"
    )

    # Contact information
    email = models.EmailField()
    phone_number = models.CharField(max_length=20)

    # Address (full formatted address from Google Places)
    address = models.CharField(max_length=500, blank=True)

    # Company owner/primary contact
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)

    # User-defined template variable values (e.g. {"portal_url": "https://pay.acme.com"}).
    # Merged into snippet render context so they resolve across ALL snippets.
    custom_variables = models.JSONField(default=dict, blank=True)

    # Status and metadata
    status = models.IntegerField(default=2)  # 2 = approved
    is_test = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyQuerySet.as_manager()

    @property
    def total_balance(self) -> Decimal:
        """Total open invoice balance for this company.

        Returns the annotated value when loaded via
        ``Company.objects.with_total_balance()``, otherwise falls back to a
        single aggregate query.
        """
        if "total_balance" in self.__dict__:
            return self.__dict__["total_balance"]
        from .financial import Invoice

        return Invoice.objects.filter(company=self, balance__gt=0).aggregate(
            total=Coalesce(
                Sum("balance"), Value(Decimal("0")), output_field=DecimalField()
            )
        )["total"]

    @total_balance.setter
    def total_balance(self, value):
        self.__dict__["total_balance"] = value

    def __str__(self):
        return self.company_name

    class Meta:
        verbose_name = "📊 Raw Data - Company"
        verbose_name_plural = "📊 Raw Data - Companies"


class CompanyMembership(BaseModel):
    """Link a user to a company with an in-company role.

    This model enables multi-company support, allowing a single user to be
    associated with multiple companies with different roles in each.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_memberships",
    )
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="members_details"
    )

    role_type = models.IntegerField(
        choices=CompanyRole.choices, default=CompanyRole.OPERATIONS
    )
    is_active_in_company = models.BooleanField(
        default=True, help_text="Whether this membership is active"
    )

    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="User who created/modified this membership",
    )
    add_time = models.DateTimeField(auto_now_add=True)
    update_time = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "👥 Company Membership"
        verbose_name_plural = "👥 Company Memberships"
        ordering = ["-update_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "company"], name="unique_user_company"
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active_in_company"]),
            models.Index(fields=["company", "is_active_in_company"]),
        ]

    def __str__(self):
        try:
            user_str = self.user.username or self.user.email or f"User({self.user.id})"
            company_str = self.company.company_name or f"Company({self.company.id})"
            role_str = self.get_role_type_display()
            return f"{user_str} @ {company_str} ({role_str})"
        except Exception:
            return f"CompanyMembership({self.id})"


class CompanyInvitation(BaseModel):
    """Invitation sent to an email address for joining a company."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REVOKED = "revoked", "Revoked"
        EXPIRED = "expired", "Expired"

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="invitations"
    )
    email = models.EmailField()
    role_to_grant = models.IntegerField(
        choices=CompanyRole.choices, default=CompanyRole.OPERATIONS
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    token_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_company_invitations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_company_invitations",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    send_count = models.PositiveIntegerField(default=0)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Company Invitation"
        verbose_name_plural = "Company Invitations"
        ordering = ["-last_sent_at", "-expires_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "email"],
                condition=models.Q(status="pending"),
                name="ar_coinvite_co_email_pending_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["company", "status"],
                name="ar_coinvite_co_status_idx",
            ),
            models.Index(
                fields=["company", "email"],
                name="ar_coinvite_co_email_idx",
            ),
        ]

    def __str__(self) -> str:
        company_name = self.company.company_name if self.company_id else "Unknown"
        return f"{self.email} @ {company_name} ({self.status})"


class CompanyInvitationLog(BaseModel):
    """Audit log for invitation lifecycle actions."""

    class Action(models.TextChoices):
        SENT = "SENT", "Sent"
        RESENT = "RESENT", "Resent"
        ACCEPTED = "ACCEPTED", "Accepted"
        REVOKED = "REVOKED", "Revoked"

    invitation = models.ForeignKey(
        CompanyInvitation, on_delete=models.CASCADE, related_name="logs"
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_invitation_logs",
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Company Invitation Log"
        verbose_name_plural = "Company Invitation Logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(
                fields=["invitation", "-timestamp"],
                name="ar_coinvlog_inv_ts_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.action} ({self.invitation_id})"


class CompanyContact(BaseModel):
    """Internal company contacts for AR management"""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="ar_contacts"
    )
    contact_type = models.CharField(
        max_length=20,
        choices=[
            ("primary", "Primary Contact"),
            ("billing", "Billing Contact"),
            ("accounting", "Accounting Contact"),
            ("executive", "Executive Contact"),
        ],
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    email_domain = models.CharField(
        max_length=255, blank=True, help_text="Domain extracted from email for matching"
    )
    phone = models.CharField(max_length=20, blank=True)
    title = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=50, blank=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="company_contact",
        help_text="Linked Django auth user for this AR team member",
    )
    slack_handle = models.CharField(
        max_length=50, blank=True, help_text="Slack username (e.g., @john.doe)"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def full_name(self) -> str:
        """Return a display name only when a first name exists."""
        first_name = str(self.first_name or "").strip()
        last_name = str(self.last_name or "").strip()
        if not first_name:
            return ""
        return " ".join(part for part in (first_name, last_name) if part)

    def __str__(self):
        display_name = self.full_name or self.email
        return f"{display_name} ({self.company.company_name})"

    class Meta:
        verbose_name = "📊 Raw Data - Company Contact"
        verbose_name_plural = "📊 Raw Data - Company Contacts"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "email"],
                name="ar_companycontact_company_email_unique",
            )
        ]


class CompanyARPolicy(BaseModel):
    """Company's internal AR Standard Operating Procedures"""

    company = models.OneToOneField(
        Company, on_delete=models.CASCADE, related_name="ar_policy"
    )

    # Policy basics
    policy_name = models.CharField(
        max_length=200, default="AR Standard Operating Procedure"
    )
    version = models.CharField(max_length=20, default="1.0")
    effective_date = models.DateField()

    # Communication policies
    # Legacy milestone-style reminder fields kept for backwards compatibility.
    first_reminder_days = models.IntegerField(
        default=5, help_text="Days after due date for first reminder"
    )
    second_reminder_days = models.IntegerField(
        default=15, help_text="Days after due date for second reminder"
    )
    escalation_days = models.IntegerField(
        default=30, help_text="Days after due date for management escalation"
    )
    collections_referral_days = models.IntegerField(
        default=90, help_text="Days after due date for collections referral"
    )

    # Communication preferences
    preferred_communication_method = models.CharField(
        max_length=20,
        choices=[
            ("email", "Email"),
            ("phone", "Phone Call"),
            ("slack", "Slack Message"),
            ("mixed", "Mixed Approach"),
        ],
        default="email",
    )

    # Credit policies
    default_credit_limit = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    credit_check_required = models.BooleanField(default=True)

    # Late fee policies
    charges_late_fees = models.BooleanField(default=True)
    late_fee_rate = models.DecimalField(max_digits=5, decimal_places=2, default=1.5)
    late_fee_minimum = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    # Collection strategies
    collection_strategy = models.TextField(
        blank=True, help_text="Detailed collection strategy and procedures"
    )
    write_off_threshold = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AR Policy: {self.company.company_name} v{self.version}"

    class Meta:
        verbose_name = "Company AR Policy"
        verbose_name_plural = "Company AR Policies"
