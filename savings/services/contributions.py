
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from savings.models import (
    SavingsGroup,
    GroupMembership,
    Contribution,
)


@transaction.atomic
def create_contribution(group, membership, due_date=None, phone_number=None):
    """
    Create a pending contribution for an active group member.
    """

    group = SavingsGroup.objects.select_for_update().get(
        pk=group.pk
    )

    membership = GroupMembership.objects.select_for_update().get(
        pk=membership.pk
    )

    if group.status != "active":
        raise ValidationError(
            "Contributions are not open for this savings group."
        )

    if membership.group_id != group.id:
        raise ValidationError(
            "This member does not belong to the selected savings group."
        )

    if membership.status != "active":
        raise ValidationError(
            "Only active members can make contributions."
        )

    due_date = due_date or date.today()

    if Contribution.objects.filter(
        membership=membership,
        due_date=due_date,
    ).exists():
        raise ValidationError(
            "A contribution record already exists for this member on this date."
        )

    phone_number = phone_number or membership.user.phone_number

    contribution = Contribution.objects.create(
        group=group,
        membership=membership,
        amount=group.contribution_amount,
        due_date=due_date,
        phone_number=phone_number,
        status="pending",
    )

    return contribution


@transaction.atomic
def generate_group_contributions(group, due_date=None):
    """
    Generate pending contribution records for all active group members.

    Existing contribution records are skipped.
    """

    group = SavingsGroup.objects.select_for_update().get(
        pk=group.pk
    )

    if group.status != "active":
        raise ValidationError(
            "The savings group must be active."
        )

    due_date = due_date or date.today()

    memberships = GroupMembership.objects.filter(
        group=group,
        status="active",
    ).select_related("user")

    created_contributions = []

    for membership in memberships:

        contribution, created = Contribution.objects.get_or_create(
            membership=membership,
            due_date=due_date,
            defaults={
                "group": group,
                "amount": group.contribution_amount,
                "phone_number": membership.user.phone_number,
                "status": "pending",
            },
        )

        if created:
            created_contributions.append(contribution)

    return created_contributions


def get_member_contributions(membership):
    """Retrieve all contributions belonging to a group member."""

    return Contribution.objects.filter(
        membership=membership
    ).select_related(
        "group"
    ).order_by("-due_date", "-created_at")


def get_outstanding_contributions(membership):
    """Retrieve unpaid contributions belonging to a member."""

    return Contribution.objects.filter(
        membership=membership,
        status__in=["pending", "failed", "cancelled"],
    ).select_related(
        "group"
    ).order_by("due_date")


def get_group_contributions(group):
    """Retrieve all contributions belonging to a savings group."""

    return Contribution.objects.filter(
        group=group
    ).select_related(
        "membership__user"
    ).order_by("-created_at")


def get_group_contribution_summary(group):
    """Calculate contribution statistics for a savings group."""

    contributions = Contribution.objects.filter(
        group=group
    )

    total_collected = contributions.filter(
        status="paid"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    total_pending = contributions.filter(
        status__in=["pending", "processing"]
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")

    return {
        "total_contributions": contributions.count(),
        "paid_contributions": contributions.filter(
            status="paid"
        ).count(),
        "pending_contributions": contributions.filter(
            status__in=["pending", "processing"]
        ).count(),
        "failed_contributions": contributions.filter(
            status="failed"
        ).count(),
        "total_collected": total_collected,
        "total_pending": total_pending,
    }


@transaction.atomic
def mark_contribution_as_paid(
    contribution_id,
    mpesa_receipt_number,
    result_code="0",
    result_description="Payment completed successfully.",
):
    """
    Confirm a contribution after successful M-Pesa callback verification.

    IMPORTANT:
    This function must only be called by a trusted payment service
    after verifying the callback and matching the transaction.
    """

    if str(result_code) != "0":
        raise ValidationError(
            "Only successful payment transactions can be confirmed."
        )

    if not mpesa_receipt_number:
        raise ValidationError(
            "An M-Pesa receipt number is required."
        )

    contribution = Contribution.objects.select_for_update().get(
        pk=contribution_id
    )

    if contribution.status == "paid":
        if contribution.mpesa_receipt_number == mpesa_receipt_number:
            return contribution

        raise ValidationError(
            "This contribution has already been paid using another receipt."
        )

    if contribution.status not in ["pending", "processing"]:
        raise ValidationError(
            "This contribution cannot be marked as paid."
        )

    if Contribution.objects.filter(
        mpesa_receipt_number=mpesa_receipt_number
    ).exclude(pk=contribution.pk).exists():
        raise ValidationError(
            "This M-Pesa receipt has already been used."
        )

    contribution.status = "paid"
    contribution.mpesa_receipt_number = mpesa_receipt_number
    contribution.result_code = str(result_code)
    contribution.result_description = result_description
    contribution.paid_at = timezone.now()

    contribution.save(
        update_fields=[
            "status",
            "mpesa_receipt_number",
            "result_code",
            "result_description",
            "paid_at",
            "updated_at",
        ]
    )

    return contribution




