"""Financial transaction models for AR management."""

from __future__ import annotations

from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from .base import BaseModel

__all__ = [
    "Invoice",
    "InvoicePayment",
    "Payment",
    "CreditMemo",
    "CreditNote",
    "CreditNoteApplication",
    "Deposit",
    "SalesReceipt",
    "ARAgingSummary",
    "ARAgingDetail",
    "ARAgingDetailInvoice",
]


class Invoice(BaseModel):
    """Enhanced Invoice model with AR management features.

    Field naming follows Merge SDK conventions for provider-agnostic integration.
    """

    # Basic invoice info
    company = models.ForeignKey("Company", on_delete=models.CASCADE)
    customer = models.ForeignKey(
        "Customer", on_delete=models.CASCADE, related_name="invoices"
    )
    customer_location = models.ForeignKey(
        "CustomerLocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    number = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Invoice number (not unique across companies)",
    )

    # === Merge SDK Integration Fields ===
    merge_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Merge UUID for this invoice (enables cross-referencing with PaymentLineItem.related_object_id)",
    )
    remote_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Third-party provider ID (e.g., QuickBooks invoice ID)",
    )
    remote_sync_token = models.CharField(max_length=64, blank=True)
    remote_updated_at = models.DateTimeField(
        null=True, blank=True, help_text="When updated in third-party system"
    )
    remote_was_deleted = models.BooleanField(
        default=False, help_text="Whether deleted in third-party platform"
    )
    remote_data = models.JSONField(
        default=list, blank=True, help_text="Raw provider data for debugging"
    )

    # Data provenance tracking
    data_source_type = models.CharField(
        max_length=20,
        blank=True,
        choices=[("accounting", "Accounting"), ("crm", "CRM"), ("email", "Email")],
    )
    data_source_name = models.CharField(max_length=50, blank=True)

    # Multi-source tracking (supports multiple integrations)
    data_sources = models.JSONField(
        default=list,
        blank=True,
        help_text='List of source systems this invoice exists in. Format: [{"type": "accounting", "name": "quickbooks", "remote_id": "123", "priority": 1, "last_synced": "2024-01-01T10:00:00Z", "is_primary": true}]',
    )

    # Invoice type (Merge SDK)
    type = models.CharField(
        max_length=30,
        default="ACCOUNTS_RECEIVABLE",
        choices=[
            ("ACCOUNTS_RECEIVABLE", "Accounts Receivable"),
            ("ACCOUNTS_PAYABLE", "Accounts Payable"),
        ],
        help_text="Invoice type per Merge SDK",
    )

    # Invoice details (Merge SDK naming)
    transaction_type = models.CharField(
        max_length=20,
        default="Invoice",
        choices=[
            ("invoice", "Invoice"),
            ("credit_memo", "Credit Memo"),
            ("payment", "Payment"),
            ("adjustment", "Adjustment"),
        ],
    )
    issue_date = models.DateField(
        null=True, blank=True, help_text="Date invoice was issued"
    )
    due_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date invoice is due. Null for invoices without payment terms; treated as current for aging.",
    )
    # Payment terms snapshots
    invoice_payment_terms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Canonical payment terms in days used for calculations",
    )
    invoice_payment_terms_source = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        choices=[
            ("qb", "QuickBooks"),
            ("calculated", "Calculated from dates"),
            ("customer_default", "Customer default"),
            ("unknown", "Unknown"),
        ],
        help_text="Source of invoice_payment_terms",
    )
    invoice_payment_terms_qb = models.IntegerField(
        null=True,
        blank=True,
        help_text="Raw payment terms days from QuickBooks SalesTermRef (if provided)",
    )
    invoice_payment_terms_qb_id = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="QuickBooks SalesTermRef ID for audit/debug",
    )
    invoice_payment_terms_calc = models.IntegerField(
        null=True,
        blank=True,
        help_text="Calculated as (due_date - issue_date) in days, clamped at >=0",
    )
    has_custom_payment_terms = models.BooleanField(
        default=False,
        help_text="True if invoice_payment_terms differs from customer's current default",
    )
    paid_on_date = models.DateField(
        null=True, blank=True, help_text="Date the invoice was fully paid"
    )

    # Financial amounts (Merge SDK)
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Total invoice amount after tax"
    )
    sub_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Amount before taxes",
    )
    total_tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total tax amount",
    )
    total_discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total discount applied",
    )
    paid_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Total amount paid",
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=False,
        default=0,
        help_text="Open balance sourced from accounting provider",
    )

    # Currency (Merge SDK)
    currency = models.CharField(
        max_length=10, default="USD", blank=True, help_text="Currency code (ISO 4217)"
    )
    exchange_rate = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Exchange rate for multi-currency",
    )
    inclusive_of_tax = models.BooleanField(
        default=False, help_text="Whether amounts are tax-inclusive"
    )

    # Line items and memo (Merge SDK)
    line_items = models.JSONField(
        default=list,
        blank=True,
        help_text="Invoice line items (Merge InvoiceLineItem format)",
    )
    tracking_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="Tracking categories (Merge format) — classes/departments associated with this invoice",
    )
    tracking_categories_by_type = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Tracking categories grouped by type. "
            'Format: {"CLASS": [{"merge_id": "...", "category_type": "CLASS", '
            '"name": "Sales", "tracking_category_id": "..."}]}. '
            "Keys are TrackingCategory.category_type values. "
            "Auto-populated during sync."
        ),
    )
    memo = models.TextField(blank=True, help_text="Private note/memo")

    # Merge status for sync (separate from app status)
    merge_status = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("PAID", "Paid"),
            ("DRAFT", "Draft"),
            ("SUBMITTED", "Submitted"),
            ("PARTIALLY_PAID", "Partially Paid"),
            ("OPEN", "Open"),
            ("VOID", "Void"),
        ],
        help_text="Status from Merge SDK for sync",
    )

    # Progress invoicing support
    is_progress_invoice = models.BooleanField(default=False)
    parent_invoice = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True
    )
    progress_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    # Status and aging - NEW STRUCTURE
    # Status field (lifecycle state)
    status = models.CharField(
        max_length=20,
        choices=[
            ("draft", "Draft"),
            ("current", "Current"),
            ("past_due_1_30", "Overdue 1-30"),
            ("past_due_31_60", "Overdue 31-60"),
            ("past_due_61_90", "Overdue 61-90"),
            ("past_due_90p", "Overdue >90"),
            ("closed_paid", "Closed — Paid"),
            ("closed_overpaid", "Closed — Overpaid"),
            ("closed_credit_memo", "Closed — Credit Memo"),
            ("closed_written_off", "Closed — Written Off"),
            ("closed_voided", "Closed — Voided"),
        ],
        default="draft",
    )

    # Payment state removed - now calculated on frontend from paid_amount/total_amount
    # See migration 0052_simplify_status_remove_payment_state

    days_outstanding = models.IntegerField(default=0)
    aging_bucket = models.CharField(
        max_length=20,
        choices=[
            ("current", "Current (not past due)"),
            ("1_30", "1-30 days past due"),
            ("31_60", "31-60 days past due"),
            ("61_90", "61-90 days past due"),
            ("91_over", "91+ days past due"),
        ],
        default="current",
    )

    # Tracking
    last_communication_date = models.DateTimeField(null=True, blank=True)
    next_follow_up_date = models.DateField(null=True, blank=True)

    # Disposition tracking (risk-based progression)
    disposition = models.CharField(
        max_length=20,
        choices=[
            ("working", "Working"),  # Actively working to collect payment
            ("collections", "Collections"),  # Escalated to collections/legal
            ("closed", "Closed"),  # Invoice closed (exited or written off)
        ],
        default="working",
        blank=True,
    )
    disposition_subtype = models.CharField(
        max_length=100,
        blank=True,
        help_text="Subtype: regular, dispute, payment_plan, promise, legal, exited, write_off",
    )
    disposition_updated_at = models.DateTimeField(null=True, blank=True)
    disposition_updated_by = models.CharField(
        max_length=100, blank=True, help_text="User ID who updated disposition"
    )
    disposition_note = models.TextField(
        blank=True, help_text="Note explaining disposition change"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_status(self):
        """Calculate status based on lifecycle and balance.

        Returns the appropriate status code based on invoice state.
        Distinguishes between overpaid (refund due) and credit memos.

        Priority order:
        1. merge_status VOID/DRAFT — authoritative from accounting system
        2. Disposition-based (write-off)
        3. Balance-based closed statuses (paid, overpaid, credit memo)
        4. Aging-based open statuses (current, past_due_*)
        """
        # Authoritative statuses from accounting system (via Merge sync)
        # These override all balance/aging logic — the provider's word is final.
        if self.merge_status == "VOID":
            return "closed_voided"
        if self.merge_status == "DRAFT":
            return "draft"

        # Note: PAID, OPEN, PARTIALLY_PAID, SUBMITTED are NOT overrides here.
        # Those fall through to balance/aging math below, which is more precise —
        # e.g., Merge calls both "paid" and "overpaid" as PAID, but balance math
        # distinguishes closed_paid vs closed_overpaid vs closed_credit_memo.
        # Only VOID and DRAFT need overrides because no balance math can detect them.

        # If balance <= 0, determine closed status
        if self.balance <= 0:
            # Check if written off via disposition first
            if self.disposition == "closed" and self.disposition_subtype == "write_off":
                return "closed_written_off"

            # Fully paid normally
            paid = self.computed_paid_amount
            if self.total_amount == paid and self.total_amount > 0:
                return "closed_paid"

            # Overpaid - customer paid MORE than invoice amount (refund may be due)
            if paid > self.total_amount and self.total_amount > 0:
                return "closed_overpaid"

            # Credit memo - invoice itself is negative (customer has credit)
            if self.total_amount < 0:
                return "closed_credit_memo"

            # Other scenarios where balance is 0 or negative (adjustments, etc.)
            return "closed_credit_memo"

        # Draft if not sent or no issue date
        if not self.issue_date:
            return "draft"

        # Calculate days past due
        today = timezone.now().date()

        if not self.due_date or self.due_date >= today:
            return "current"

        days_past_due = (today - self.due_date).days

        if days_past_due <= 30:
            return "past_due_1_30"
        elif days_past_due <= 60:
            return "past_due_31_60"
        elif days_past_due <= 90:
            return "past_due_61_90"
        else:
            return "past_due_90p"

    @property
    def computed_paid_amount(self):
        """Total amount paid, computed from linked InvoicePayment records."""
        if not self.pk:
            return Decimal("0")
        return self.payment_applications.aggregate(total=Sum("applied_amount"))[
            "total"
        ] or Decimal("0")

    def get_payment_progress_percentage(self):
        """Calculate payment progress as a percentage (0-100).

        Returns the percentage of the invoice that has been paid.
        Used for display purposes only (not stored in DB).
        """
        if self.total_amount <= 0:
            return 0

        progress = (self.computed_paid_amount / self.total_amount) * 100
        return min(100, max(0, progress))  # Clamp between 0 and 100

    def get_status_display(self):
        """Get formatted status with payment progress for display.

        Returns status with payment percentage appended if partially paid,
        or refund amount for overpaid invoices.
        E.g., "Overdue (45% paid)" or "Closed — Overpaid ($500 refund due)"
        """
        # For overpaid invoices, show refund amount
        if self.status == "closed_overpaid":
            refund_amount = abs(self.balance)  # Balance is negative, so abs it
            return f"Closed — Overpaid (${refund_amount:,.2f} refund due)"

        # For credit memos, optionally show credit amount
        if self.status == "closed_credit_memo" and self.balance < 0:
            credit_amount = abs(self.balance)
            return f"Closed — Credit Memo (${credit_amount:,.2f})"

        # Simplify past_due_* statuses to just "Overdue"
        if self.status.startswith("past_due_"):
            progress = self.get_payment_progress_percentage()
            if 0 < progress < 100:
                return f"Overdue ({round(progress)}% paid)"
            return "Overdue"

        # Format other statuses (convert snake_case to Title Case)
        status_display = self.status.replace("_", " ").title()

        # Add payment progress if partially paid
        progress = self.get_payment_progress_percentage()
        if 0 < progress < 100:
            return f"{status_display} ({round(progress)}% paid)"

        return status_display

    def _parse_payment_terms_days(self, terms_str: str) -> int | None:
        """Parse payment terms string like 'Net 30' to integer days."""
        if not terms_str:
            return None

        terms_lower = terms_str.lower().strip()

        # Handle "Due on Receipt" variants
        if "receipt" in terms_lower or "immediate" in terms_lower:
            return 0

        import re

        match = re.search(r"(\d+)", terms_str)
        return int(match.group(1)) if match else None

    def save(self, *args, **kwargs):
        # Snapshot payment terms
        # 1) Calculate from dates
        calc_terms = None
        if self.issue_date and self.due_date:
            calc_terms = max(0, (self.due_date - self.issue_date).days)
        self.invoice_payment_terms_calc = calc_terms

        # 2) Canonical selection: QB > calculated > customer default
        # Customer has default_payment_terms (string like "Net 30"), parse to days
        customer_terms_parsed = None
        if self.customer and self.customer.default_payment_terms:
            customer_terms_parsed = self._parse_payment_terms_days(
                self.customer.default_payment_terms
            )

        if self.invoice_payment_terms_qb is not None:
            self.invoice_payment_terms = max(0, self.invoice_payment_terms_qb)
            self.invoice_payment_terms_source = "qb"
        elif calc_terms is not None:
            self.invoice_payment_terms = calc_terms
            self.invoice_payment_terms_source = "calculated"
        elif customer_terms_parsed is not None:
            self.invoice_payment_terms = customer_terms_parsed
            self.invoice_payment_terms_source = "customer_default"
        else:
            self.invoice_payment_terms = 0
            self.invoice_payment_terms_source = "unknown"

        # 3) Flag if invoice terms differ from customer's current default
        self.has_custom_payment_terms = (
            self.invoice_payment_terms is not None
            and customer_terms_parsed is not None
            and self.invoice_payment_terms != customer_terms_parsed
        )

        # Calculate days outstanding and aging bucket
        if self.due_date:
            days_diff = (timezone.now().date() - self.due_date).days
            self.days_outstanding = max(0, days_diff)

            # 5-bucket aging: current (0), 1-30, 31-60, 61-90, 91+
            if self.days_outstanding == 0:
                self.aging_bucket = "current"
            elif self.days_outstanding <= 30:
                self.aging_bucket = "1_30"
            elif self.days_outstanding <= 60:
                self.aging_bucket = "31_60"
            elif self.days_outstanding <= 90:
                self.aging_bucket = "61_90"
            else:
                self.aging_bucket = "91_over"
        else:
            self.days_outstanding = 0
            self.aging_bucket = "current"

        # Always recalculate status from current state.
        # calculate_status() has the full priority chain (VOID/DRAFT overrides,
        # disposition write-off, balance-based closed, aging-based open).
        # Pass skip_auto_calc=True to bypass (e.g., bulk imports, data migrations).
        skip_auto_calc = kwargs.pop("skip_auto_calc", False)
        if not skip_auto_calc:
            self.status = self.calculate_status()

        # Aging buckets are meaningful for open AR only.
        # Normalize all closed lifecycle statuses to a neutral bucket.
        if self.status and self.status.startswith("closed_"):
            self.aging_bucket = "current"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Invoice {self.number} - {self.customer.customer_company_name}"

    class Meta:
        verbose_name = "📊 Raw Data - Invoice"
        verbose_name_plural = "📊 Raw Data - Invoices"
        ordering = ["-issue_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["merge_id", "company"],
                condition=Q(merge_id__isnull=False),
                name="ar_invoice_merge_id_company_uniq",
            ),
        ]
        indexes = [
            # Primary lookup patterns
            models.Index(
                fields=["company", "customer"],
                name="ar_inv_co_cust_idx",
            ),
            # Open-balance lookups (customer list rollups, with_open_balance)
            models.Index(
                fields=["company", "customer"],
                name="ar_inv_open_co_cust_idx",
                condition=Q(balance__gt=0),
            ),
            models.Index(
                fields=["company", "balance"],
                name="ar_inv_co_balance_idx",
            ),
            # Aging and due date queries
            models.Index(
                fields=["company", "due_date"],
                name="ar_inv_co_due_idx",
            ),
            models.Index(
                fields=["customer", "-due_date"],
                name="ar_inv_cust_due_desc_idx",
            ),
            # Disposition filtering (used in breakdown calculations)
            models.Index(
                fields=["company", "disposition"],
                name="ar_inv_co_disp_idx",
            ),
            # Status filtering (overdue queries)
            models.Index(
                fields=["company", "status"],
                name="ar_inv_co_status_idx",
            ),
        ]


class InvoicePayment(BaseModel):
    """Tracks the applied amount of a Payment to a specific Invoice.

    A single payment can be split across multiple invoices, each with its own
    applied amount.
    """

    payment = models.ForeignKey(
        "Payment", on_delete=models.CASCADE, related_name="applications"
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="payment_applications"
    )
    applied_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Amount of the payment applied to this invoice",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Invoice Payment"
        verbose_name_plural = "Invoice Payments"
        unique_together = [("payment", "invoice")]
        indexes = [
            models.Index(
                fields=["invoice"],
                name="ar_invpay_invoice_idx",
            ),
        ]

    def __str__(self):
        return (
            f"${self.applied_amount} from Payment #{self.payment_id} "
            f"to Invoice #{self.invoice_id}"
        )


class Payment(BaseModel):
    """Payment records for invoices.

    Field naming follows Merge SDK conventions for provider-agnostic integration.
    """

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="payments"
    )
    invoices = models.ManyToManyField(
        Invoice,
        related_name="payments_m2m",
        through="InvoicePayment",
        blank=True,
    )
    company = models.ForeignKey("Company", on_delete=models.CASCADE)

    # App-specific payment type
    payment_type = models.CharField(
        max_length=20,
        choices=[
            ("initial_deposit", "Initial Deposit"),
            ("milestone", "Milestone Payment"),
            ("final", "Final Payment"),
            ("partial", "Partial Payment"),
            ("full", "Full Payment"),
        ],
    )

    # === Merge SDK Fields ===
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, help_text="Payment amount"
    )
    transaction_date = models.DateField(
        null=True, blank=True, help_text="Date of the payment transaction"
    )
    payment_method = models.CharField(
        max_length=50,
        blank=True,
        help_text="Payment method reference (Merge PaymentMethod ID or name)",
    )

    # Merge SDK type
    type = models.CharField(
        max_length=30,
        default="ACCOUNTS_RECEIVABLE",
        choices=[
            ("ACCOUNTS_RECEIVABLE", "Accounts Receivable"),
            ("ACCOUNTS_PAYABLE", "Accounts Payable"),
        ],
        help_text="Payment type per Merge SDK",
    )

    # Contact reference (customer/supplier)
    contact = models.JSONField(
        default=dict,
        blank=True,
        help_text="Customer/supplier reference (Merge Contact format)",
    )

    # Account reference
    account = models.CharField(
        max_length=255, blank=True, help_text="Account reference for the payment"
    )

    # Currency (Merge SDK)
    currency = models.CharField(
        max_length=10, default="USD", blank=True, help_text="Currency code (ISO 4217)"
    )
    exchange_rate = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Exchange rate for multi-currency",
    )

    # Applied to lines (Merge SDK)
    applied_to_lines = models.JSONField(
        default=list,
        blank=True,
        help_text="Invoice lines this payment applies to (Merge PaymentAppliedToLine format)",
    )

    # === Merge SDK Integration Fields ===
    merge_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Merge UUID for this payment",
    )
    remote_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Third-party provider ID (e.g., QuickBooks payment ID)",
    )
    remote_sync_token = models.CharField(max_length=64, blank=True)
    remote_updated_at = models.DateTimeField(
        null=True, blank=True, help_text="When updated in third-party system"
    )
    remote_was_deleted = models.BooleanField(
        default=False, help_text="Whether deleted in third-party platform"
    )
    remote_data = models.JSONField(
        default=list, blank=True, help_text="Raw provider data for debugging"
    )

    # External references (app-specific)
    transaction_id = models.CharField(max_length=100, blank=True)

    data_source_type = models.CharField(
        max_length=20,
        blank=True,
        choices=[("accounting", "Accounting"), ("crm", "CRM"), ("email", "Email")],
    )
    data_source_name = models.CharField(max_length=50, blank=True)

    # Multi-source tracking (supports multiple integrations)
    data_sources = models.JSONField(
        default=list,
        blank=True,
        help_text='List of source systems this payment exists in. Format: [{"type": "accounting", "name": "quickbooks", "remote_id": "123", "priority": 1, "last_synced": "2024-01-01T10:00:00Z", "is_primary": true}]',
    )

    # App-specific status (Merge doesn't have payment status)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("completed", "Completed"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        default="completed",
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment ${self.total_amount} for {self.invoice.number}"

    class Meta:
        verbose_name = "📊 Raw Data - Payment"
        verbose_name_plural = "📊 Raw Data - Payments"
        ordering = ["-transaction_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["merge_id", "company"],
                condition=Q(merge_id__isnull=False),
                name="ar_payment_merge_id_company_uniq",
            ),
            models.UniqueConstraint(
                fields=["remote_id", "company"],
                condition=Q(remote_id__isnull=False),
                name="ar_payment_remote_id_company_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["invoice"],
                name="ar_pay_invoice_idx",
            ),
            models.Index(
                fields=["company", "-transaction_date"],
                name="ar_pay_co_txdate_idx",
            ),
        ]


class CreditMemo(BaseModel):
    """QuickBooks credit memo representation."""

    STATUS_CHOICES = [
        ("open", "Open"),
        ("closed", "Closed"),
        ("voided", "Voided"),
    ]

    company = models.ForeignKey(
        "Company", on_delete=models.CASCADE, related_name="credit_memos"
    )
    customer = models.ForeignKey(
        "Customer", on_delete=models.CASCADE, related_name="credit_memos"
    )
    qb_credit_memo_id = models.CharField(max_length=100, unique=True)
    qb_sync_token = models.CharField(max_length=64, blank=True)
    credit_memo_number = models.CharField(max_length=50, blank=True)
    credit_memo_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    remaining_credit = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    memo = models.TextField(blank=True)
    private_note = models.TextField(blank=True)
    qb_last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Credit Memo"
        verbose_name_plural = "Credit Memos"
        indexes = [
            models.Index(fields=["qb_credit_memo_id"], name="ar_qbo_creditmemo_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"Credit Memo {self.credit_memo_number or self.qb_credit_memo_id}"


class CreditNote(BaseModel):
    """Credit note from Merge Accounting API.

    A credit note is a transaction issued to a customer indicating a reduction
    or cancellation of the amount owed. It can be applied to Accounts Receivable
    Invoices to decrease the overall amount of the Invoice.

    Field naming follows Merge SDK conventions for provider-agnostic integration.
    """

    STATUS_CHOICES = [
        ("submitted", "Submitted"),
        ("authorized", "Authorized"),
        ("paid", "Paid"),
    ]

    company = models.ForeignKey(
        "Company", on_delete=models.CASCADE, related_name="credit_notes"
    )
    customer = models.ForeignKey(
        "Customer",
        on_delete=models.CASCADE,
        related_name="credit_notes",
        null=True,
        blank=True,
    )
    invoices = models.ManyToManyField(
        Invoice,
        related_name="credit_notes",
        through="CreditNoteApplication",
        blank=True,
    )

    number = models.CharField(
        max_length=100, blank=True, help_text="Credit note number"
    )
    transaction_date = models.DateField(
        null=True, blank=True, help_text="Credit note transaction date"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="submitted"
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Credit note total amount",
    )
    remaining_credit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Remaining credit available to apply",
    )

    currency = models.CharField(
        max_length=10, default="USD", blank=True, help_text="Currency code (ISO 4217)"
    )
    exchange_rate = models.DecimalField(
        max_digits=15,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Exchange rate for multi-currency",
    )
    inclusive_of_tax = models.BooleanField(
        null=True,
        blank=True,
        help_text="True if amounts are inclusive of tax",
    )

    line_items = models.JSONField(
        default=list,
        blank=True,
        help_text="Credit note line items (Merge CreditNoteLineItem format)",
    )
    contact = models.JSONField(
        default=dict,
        blank=True,
        help_text="Customer/supplier reference (Merge Contact format)",
    )
    tracking_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="Tracking categories (Merge format)",
    )
    applied_to_lines = models.JSONField(
        default=list,
        blank=True,
        help_text="Raw Merge CreditNoteApplyLine data",
    )
    payments_data = models.JSONField(
        default=list,
        blank=True,
        help_text="Merge Payment IDs associated with this credit note",
    )
    applied_payments = models.JSONField(
        default=list,
        blank=True,
        help_text="Merge applied payments data (PaymentLineItem format)",
    )

    # === Merge SDK Integration Fields ===
    merge_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        help_text="Merge UUID for this credit note",
    )
    remote_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Third-party provider ID (e.g., QuickBooks credit note ID)",
    )
    remote_sync_token = models.CharField(max_length=64, blank=True)
    remote_updated_at = models.DateTimeField(
        null=True, blank=True, help_text="When updated in third-party system"
    )
    remote_was_deleted = models.BooleanField(
        default=False, help_text="Whether deleted in third-party platform"
    )
    remote_data = models.JSONField(
        default=list, blank=True, help_text="Raw provider data for debugging"
    )

    # Data provenance tracking
    data_source_type = models.CharField(
        max_length=20,
        blank=True,
        choices=[("accounting", "Accounting"), ("crm", "CRM"), ("email", "Email")],
    )
    data_source_name = models.CharField(max_length=50, blank=True)
    data_sources = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            'List of source systems. Format: [{"type": "accounting", '
            '"name": "quickbooks", "remote_id": "123", "priority": 1, '
            '"last_synced": "2024-01-01T10:00:00Z", "is_primary": true}]'
        ),
    )

    memo = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Credit Note {self.number or self.remote_id} — ${self.total_amount}"

    class Meta:
        verbose_name = "Credit Note"
        verbose_name_plural = "Credit Notes"
        ordering = ["-transaction_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["merge_id", "company"],
                condition=Q(merge_id__isnull=False),
                name="ar_creditnote_merge_id_company_uniq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["company", "-transaction_date"],
                name="ar_cn_co_txdate_idx",
            ),
            models.Index(
                fields=["customer"],
                name="ar_cn_customer_idx",
            ),
        ]


class CreditNoteApplication(BaseModel):
    """Tracks the applied amount of a CreditNote to a specific Invoice.

    A single credit note can be split across multiple invoices, each with its
    own applied amount and date.
    """

    credit_note = models.ForeignKey(
        "CreditNote", on_delete=models.CASCADE, related_name="applications"
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="credit_note_applications"
    )
    applied_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Amount of the credit note applied to this invoice",
    )
    applied_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date the credit note was applied to the invoice",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Credit Note Application"
        verbose_name_plural = "Credit Note Applications"
        unique_together = [("credit_note", "invoice")]
        indexes = [
            models.Index(
                fields=["invoice"],
                name="ar_cnapp_invoice_idx",
            ),
        ]

    def __str__(self):
        return (
            f"${self.applied_amount} from CreditNote #{self.credit_note_id} "
            f"to Invoice #{self.invoice_id}"
        )


class Deposit(BaseModel):
    """QuickBooks deposit representation."""

    company = models.ForeignKey(
        "Company", on_delete=models.CASCADE, related_name="deposits"
    )
    qb_deposit_id = models.CharField(max_length=100, unique=True)
    qb_sync_token = models.CharField(max_length=64, blank=True)
    deposit_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    deposit_to_account = models.CharField(max_length=255, blank=True)
    payment_method = models.CharField(max_length=100, blank=True)
    memo = models.TextField(blank=True)
    linked_payments = models.ManyToManyField(
        Payment, related_name="deposits", blank=True
    )
    qb_last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Deposit"
        verbose_name_plural = "Deposits"
        indexes = [
            models.Index(fields=["qb_deposit_id"], name="ar_qbo_deposit_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"Deposit {self.qb_deposit_id}"


class SalesReceipt(BaseModel):
    """QuickBooks sales receipt representation."""

    STATUS_CHOICES = [
        ("open", "Open"),
        ("closed", "Closed"),
        ("voided", "Voided"),
    ]

    company = models.ForeignKey(
        "Company", on_delete=models.CASCADE, related_name="sales_receipts"
    )
    customer = models.ForeignKey(
        "Customer", on_delete=models.CASCADE, related_name="sales_receipts"
    )
    qb_sales_receipt_id = models.CharField(max_length=100, unique=True)
    qb_sync_token = models.CharField(max_length=64, blank=True)
    sales_receipt_number = models.CharField(max_length=50, blank=True)
    transaction_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    payment_method = models.CharField(max_length=100, blank=True)
    deposit_to_account = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    memo = models.TextField(blank=True)
    private_note = models.TextField(blank=True)
    qb_last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sales Receipt"
        verbose_name_plural = "Sales Receipts"
        indexes = [
            models.Index(
                fields=["qb_sales_receipt_id"], name="ar_qbo_salesreceipt_idx"
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - human readable
        return f"Sales Receipt {self.sales_receipt_number or self.qb_sales_receipt_id}"


class ARAgingSummary(BaseModel):
    """Company-Level Aging Report Summary"""

    company = models.ForeignKey(
        "Company", on_delete=models.CASCADE, related_name="ar_aging_summary"
    )
    report_date = models.DateField(help_text="As of date for the aging report")

    # Company-wide aging buckets (matching QuickBooks format exactly)
    current = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="CURRENT (0 days)"
    )
    days_1_30 = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="1 - 30 days past due"
    )
    days_31_60 = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="31 - 60 days past due"
    )
    days_61_90 = models.DecimalField(
        max_digits=15, decimal_places=2, default=0, help_text="61 - 90 days past due"
    )
    days_91_over = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="91 AND OVER days past due",
    )
    total_ar = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Total accounts receivable",
    )
    current_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    days_1_30_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    days_31_60_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    days_61_90_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    days_91_over_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    overdue = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        help_text="Total overdue AR (all non-current buckets)",
    )
    overdue_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Company-wide summary metrics
    total_customers_with_balance = models.IntegerField(default=0)
    total_invoice_count = models.IntegerField(default=0)
    total_overdue_count = models.IntegerField(default=0)
    average_days_outstanding = models.DecimalField(
        max_digits=10, decimal_places=1, default=0
    )
    weighted_avg_ar_age = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
        help_text="Weighted average AR age - balance-weighted average days since invoice issued",
    )
    weighted_avg_payment_terms = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Weighted average payment terms (days) at this report date",
    )
    days_beyond_terms = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Weighted avg days past due for paid invoices: Sum(invoice.total_amount * (invoice.paid_on_date - invoice.due_date)) / Sum(invoice.total_amount)",
    )
    avg_days_delinquent = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
        help_text="Balance-weighted average days past due for currently overdue invoices",
    )
    top_customer_name = models.CharField(max_length=255, blank=True, default="")
    top_customer_balance = models.DecimalField(
        max_digits=15, decimal_places=2, default=0
    )
    top_customer_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )

    # Company-wide activity tracking
    last_payment_date = models.DateField(null=True, blank=True)
    last_communication_date = models.DateTimeField(null=True, blank=True)

    # Company-wide risk assessment
    overall_risk_score = models.IntegerField(
        default=0, help_text="0-100 company risk score"
    )
    high_risk_customer_count = models.IntegerField(default=0)
    critical_risk_customer_count = models.IntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AR Summary - {self.company.company_name} (${self.total_ar})"

    class Meta:
        verbose_name = "📊 Raw Data - AR Aging Summary"
        verbose_name_plural = "📊 Raw Data - AR Aging Summaries"


class ARAgingDetail(BaseModel):
    """Customer-Level Aging Details"""

    company = models.ForeignKey(
        "Company", on_delete=models.CASCADE, related_name="ar_aging_details"
    )
    customer = models.ForeignKey(
        "Customer", on_delete=models.CASCADE, related_name="ar_aging_detail"
    )
    customer_location = models.ForeignKey(
        "CustomerLocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ar_aging_detail",
    )
    aging_summary = models.ForeignKey(
        ARAgingSummary, on_delete=models.CASCADE, related_name="customer_details"
    )

    # Customer-specific aging buckets
    current = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    days_1_30 = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    days_31_60 = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    days_61_90 = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    days_91_over = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_ar = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    current_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    days_1_30_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    days_31_60_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    days_61_90_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    days_91_over_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )
    overdue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overdue_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    weighted_avg_ar_age = models.DecimalField(
        max_digits=10, decimal_places=1, default=0
    )
    weighted_avg_payment_terms = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
    )
    days_beyond_terms = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        null=True,
        blank=True,
    )
    avg_days_delinquent = models.DecimalField(
        max_digits=10,
        decimal_places=1,
        default=0,
    )

    # Customer-specific summary metrics
    invoice_count = models.IntegerField(default=0)
    overdue_count = models.IntegerField(default=0)

    # Risk assessment
    risk_score = models.IntegerField(default=0, help_text="0-100 customer risk score")
    risk_level = models.CharField(
        max_length=10,
        choices=[
            ("low", "Low Risk"),
            ("medium", "Medium Risk"),
            ("high", "High Risk"),
            ("critical", "Critical Risk"),
        ],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AR Detail: {self.customer.customer_company_name} (${self.total_ar})"

    class Meta:
        verbose_name = "AR Aging Detail"
        verbose_name_plural = "AR Aging Details"
        indexes = [
            models.Index(
                fields=["company", "customer"],
                name="ar_aging_co_cust_idx",
            ),
            models.Index(
                fields=["company", "risk_level"],
                name="ar_aging_co_risk_idx",
            ),
        ]


class ARAgingDetailInvoice(BaseModel):
    """Individual invoice lines that appear in the Aging Detail Report"""

    company = models.ForeignKey(
        "Company", on_delete=models.CASCADE, related_name="ar_aging_detail_invoices"
    )
    aging_summary = models.ForeignKey(
        ARAgingSummary, on_delete=models.CASCADE, related_name="invoice_details"
    )
    aging_detail = models.ForeignKey(
        ARAgingDetail, on_delete=models.CASCADE, related_name="invoice_lines"
    )
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="aging_lines"
    )

    # Snapshot of invoice data at report time
    invoice_number = models.CharField(max_length=50)
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    open_balance = models.DecimalField(max_digits=12, decimal_places=2)

    # Aging bucket placement
    aging_bucket = models.CharField(
        max_length=20,
        choices=[
            ("current", "Current"),
            ("1_30", "1-30 Days"),
            ("31_60", "31-60 Days"),
            ("61_90", "61-90 Days"),
            ("91_over", "91+ Days"),
        ],
    )
    days_outstanding = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Aging Line: {self.invoice_number} ({self.aging_bucket})"

    class Meta:
        verbose_name = "AR Aging Detail Invoice"
        verbose_name_plural = "AR Aging Detail Invoices"
