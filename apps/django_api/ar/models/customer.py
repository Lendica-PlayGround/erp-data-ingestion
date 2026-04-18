"""Customer-related models for AR management."""

from decimal import Decimal

from django.db import models
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce

from .base import BaseModel
from .company import Company, CompanyContact

__all__ = [
    "Customer",
    "CustomerLocation",
    "CustomerContact",
]


class CustomerQuerySet(models.QuerySet):
    def with_open_balance(self, company_id=None):
        """Annotate each customer with the sum of its open invoice balances.

        When ``company_id`` is set, only invoice rows for that company are
        included in the aggregate.
        """
        invoice_filter = Q(invoices__balance__gt=0)
        if company_id is not None:
            invoice_filter &= Q(invoices__company_id=company_id)

        return self.annotate(
            open_balance=Coalesce(
                Sum("invoices__balance", filter=invoice_filter),
                Value(Decimal("0")),
                output_field=DecimalField(),
            )
        )


class Customer(BaseModel):
    """Customer companies for AR management"""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="customers"
    )
    customer_company_name = models.CharField(max_length=200)
    description = models.TextField(
        blank=True,
        help_text="Customer background, industry notes, relationship history",
    )

    # Customer details
    industry = models.CharField(max_length=100, blank=True)
    # Address information
    address_line1 = models.CharField(max_length=200, blank=True)
    address_line2 = models.CharField(max_length=200, blank=True)
    address_city = models.CharField(max_length=100, blank=True)
    address_state = models.CharField(max_length=50, blank=True)
    address_zipcode = models.CharField(max_length=20, blank=True)
    address_country = models.CharField(max_length=100, default="United States")

    customer_status = models.CharField(
        max_length=20,
        choices=[
            ("active", "Active"),
            ("inactive", "Inactive"),
            ("suspended", "Suspended"),
            ("prospect", "Prospect"),
        ],
        default="active",
    )

    # Payment terms and preferences
    default_payment_terms = models.CharField(max_length=20, default="", blank=True)
    credit_limit = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    preferred_communication_method = models.CharField(
        max_length=20,
        choices=[
            ("email", "Email"),
            ("phone", "Phone"),
            ("mail", "Mail"),
            ("portal", "Customer Portal"),
        ],
        default="email",
    )

    # === Merge SDK Integration Fields ===
    merge_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Merge UUID for this customer",
    )
    remote_data = models.JSONField(
        default=list, blank=True, help_text="Raw provider data for debugging"
    )
    is_person = models.BooleanField(
        blank=True,
        null=True,
        help_text="Whether the remote customer is a person/individual (provider-specific)",
    )

    # Data provenance tracking
    data_source_type = models.CharField(
        max_length=20,
        blank=True,
        choices=[("accounting", "Accounting"), ("crm", "CRM"), ("email", "Email")],
        help_text="Type of source system (accounting > CRM > email priority)",
    )
    data_source_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Specific source name (e.g., quickbooks, hubspot, gmail)",
    )
    created_by_source = models.CharField(
        max_length=50,
        blank=True,
        help_text="Source that originally created this record",
    )
    last_updated_by_source = models.CharField(
        max_length=50, blank=True, help_text="Source that last updated this record"
    )
    source_priority = models.IntegerField(
        default=3, help_text="Source priority: 1=accounting, 2=CRM, 3=email"
    )

    # Multi-source tracking (new approach - supports multiple integrations)
    data_sources = models.JSONField(
        default=list,
        blank=True,
        help_text='List of source systems this customer exists in. Format: [{"type": "accounting", "name": "netsuite", "remote_id": "123", "priority": 1, "last_synced": "2024-01-01T10:00:00Z", "is_primary": true}]',
    )

    # Account disposition tracking (risk-based progression)
    account_disposition = models.CharField(
        max_length=20,
        choices=[
            ("working", "Working"),  # Actively working to collect payment
            ("collections", "Collections"),  # Escalated to collections/legal
            ("closed", "Closed"),  # Account closed (exited or written off)
        ],
        default="working",
        blank=True,
    )
    account_disposition_subtype = models.CharField(
        max_length=100,
        blank=True,
        help_text="Subtype: regular, dispute, payment_plan, promise, legal, exited, write_off",
    )
    account_disposition_source = models.CharField(
        max_length=20,
        choices=[("derived", "Derived from invoices"), ("manual", "Manual override")],
        default="derived",
        blank=True,
    )
    account_disposition_updated_at = models.DateTimeField(null=True, blank=True)
    account_disposition_updated_by = models.CharField(
        max_length=100, blank=True, help_text="User ID who updated account disposition"
    )
    account_disposition_note = models.TextField(
        blank=True, help_text="Note explaining account disposition change"
    )

    # Ownership
    ar_owner = models.ForeignKey(
        CompanyContact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ar_customers",
        help_text="AR team member responsible for collections on this customer",
    )
    sales_owner = models.ForeignKey(
        CompanyContact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_customers",
        help_text="Salesperson / AE who owns the commercial relationship",
    )
    last_contact_date = models.DateTimeField(
        null=True, blank=True, help_text="Most recent communication timestamp"
    )
    internal_notes = models.TextField(
        blank=True, help_text="Internal team notes separate from disposition notes"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomerQuerySet.as_manager()

    @property
    def open_balance(self) -> Decimal:
        """Total open invoice balance for this customer.

        Returns the annotated value when loaded via
        ``Customer.objects.with_open_balance()`` or
        ``with_open_balance(company_id=...)``, otherwise falls back to a
        single aggregate query.
        """
        if "open_balance" in self.__dict__:
            return self.__dict__["open_balance"]
        from .financial import Invoice

        return Invoice.objects.filter(customer=self, balance__gt=0).aggregate(
            total=Coalesce(
                Sum("balance"), Value(Decimal("0")), output_field=DecimalField()
            )
        )["total"]

    @open_balance.setter
    def open_balance(self, value):
        self.__dict__["open_balance"] = value

    def __str__(self):
        return f"{self.customer_company_name} ({self.company.company_name})"

    def calculate_account_disposition(self):
        """Calculate account disposition from open invoices using severity ladder.

        Returns tuple: (disposition, source)
        - If manual override exists, returns (manual_disposition, 'manual')
        - Otherwise, derives from open invoices using severity ladder

        Severity ladder (highest to lowest):
        Closed > Collections > Working
        """
        # If manual override, respect it
        if self.account_disposition_source == "manual":
            return (self.account_disposition, "manual")

        # Define severity ladder (risk-based progression)
        severity_order = ["closed", "collections", "working"]

        # Get open invoices (exclude VOID/DRAFT — not real receivables; only AR)
        open_invoices = (
            self.invoices.filter(balance__gt=0, type="ACCOUNTS_RECEIVABLE")
            .exclude(status="paid")
            .exclude(merge_status__in=["VOID", "DRAFT"])
        )

        # Find highest severity disposition
        highest_disposition = "working"
        highest_severity = len(severity_order)

        for invoice in open_invoices:
            disposition = invoice.disposition or "working"
            try:
                severity = severity_order.index(disposition)
                if severity < highest_severity:
                    highest_severity = severity
                    highest_disposition = disposition
            except ValueError:
                # Unknown disposition, skip
                continue

        return (highest_disposition, "derived")

    class Meta:
        verbose_name = "📊 Raw Data - Customer"
        verbose_name_plural = "📊 Raw Data - Customers"
        constraints = [
            models.UniqueConstraint(
                fields=["merge_id", "company"],
                condition=Q(merge_id__isnull=False),
                name="ar_customer_merge_id_company_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["company", "account_disposition"],
                name="ar_cust_co_disp_idx",
            ),
            models.Index(
                fields=["company", "customer_status"],
                name="ar_cust_co_status_idx",
            ),
            models.Index(
                fields=["company", "-id"],
                name="ar_cust_co_id_desc_idx",
            ),
        ]


class CustomerLocation(BaseModel):
    """Customer locations for multi-location customers"""

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="locations"
    )
    location_name = models.CharField(
        max_length=200, blank=True, help_text="e.g., 'Main Office', 'Warehouse'"
    )

    # Location address
    address_line1 = models.CharField(max_length=200)
    address_line2 = models.CharField(max_length=200, blank=True)
    address_city = models.CharField(max_length=100)
    address_state = models.CharField(max_length=50)
    address_zipcode = models.CharField(max_length=20)
    address_country = models.CharField(max_length=100, default="United States")

    # Location-specific settings
    is_primary = models.BooleanField(default=False)
    is_billing_address = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.location_name:
            return f"{self.customer.customer_company_name}:{self.location_name}"
        return f"{self.customer.customer_company_name}:{self.address_line1}"

    class Meta:
        verbose_name = "📊 Raw Data - Customer Location"
        verbose_name_plural = "📊 Raw Data - Customer Locations"


class CustomerContact(BaseModel):
    """Customer contacts for AR communication"""

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="contacts",
        null=True,
        blank=True,
    )
    contact_type = models.CharField(
        max_length=20,
        choices=[
            ("ap_manager", "AP Manager"),
            ("controller", "Controller"),
            ("cfo", "CFO"),
            ("procurement", "Procurement"),
            ("primary", "Primary Contact"),
        ],
    )
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    email_domain = models.CharField(
        max_length=255, blank=True, help_text="Domain extracted from email for matching"
    )
    phone = models.CharField(max_length=20, blank=True)
    title = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    # Data provenance tracking
    data_source_type = models.CharField(
        max_length=20,
        blank=True,
        choices=[("accounting", "Accounting"), ("crm", "CRM"), ("email", "Email")],
    )
    data_source_name = models.CharField(max_length=50, blank=True)

    # Multi-source tracking (new approach - supports multiple integrations)
    data_sources = models.JSONField(
        default=list,
        blank=True,
        help_text='List of source systems this contact exists in. Format: [{"type": "accounting", "name": "netsuite", "remote_id": "123", "priority": 1, "last_synced": "2024-01-01T10:00:00Z", "is_primary": true}]',
    )

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
        if self.customer:
            return f"{display_name} at {self.customer.customer_company_name}"
        return f"{display_name} (unassigned)"

    class Meta:
        verbose_name = "📊 Raw Data - Customer Contact"
        verbose_name_plural = "📊 Raw Data - Customer Contacts"
