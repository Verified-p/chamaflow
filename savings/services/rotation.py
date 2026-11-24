
import calendar

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from savings.models import (
    SavingsGroup,
    GroupMembership,
    RotationTurn,
)


# ==========================================================
# DATE CALCULATION
# ==========================================================

def add_months(original_date, months):
    """
    Add months to a date while handling different month lengths.

    Example:
    January 31 + 1 month = February 28 (or 29 in a leap year).
    """

    month_index = original_date.month - 1 + months

    year = original_date.year + month_index // 12
    month = month_index % 12 + 1

    last_day = calendar.monthrange(year, month)[1]
    day = min(original_date.day, last_day)

    return original_date.replace(
        year=year,
        month=month,
        day=day,
    )


def add_frequency_periods(start_date, frequency, periods):
    """
    Calculate a date after a specified number of contribution periods.

    Supported frequencies:
    - daily
    - weekly
    - monthly
    """

    if periods < 0:
        raise ValidationError(
            "The number of contribution periods cannot be negative."
        )

    if frequency == "daily":
        return start_date + timedelta(days=periods)

    if frequency == "weekly":
        return start_date + timedelta(weeks=periods)

    if frequency == "monthly":
        return add_months(start_date, periods)

    raise ValidationError(
        "Unsupported contribution frequency."
    )


# ==========================================================
# ROTATION VALIDATION
# ==========================================================

def validate_group_for_rotation(group):
    """
    Validate whether a savings group is ready for rotation.
    """

    if group.status != "active":
        raise ValidationError(
            "The savings group must be active before generating its rotation schedule."
        )

    if not group.start_date:
        raise ValidationError(
            "The savings group must have a start date."
        )

    if not group.contribution_amount or group.contribution_amount <= 0:
        raise ValidationError(
            "The contribution amount must be greater than zero."
        )

    if group.contribution_frequency not in (
        "daily",
        "weekly",
        "monthly",
    ):
        raise ValidationError(
            "The group has an unsupported contribution frequency."
        )


def get_active_group_memberships(group):
    """
    Retrieve all active members in a deterministic rotation order.

    The earliest active membership receives the first turn.
    """

    return list(
        GroupMembership.objects.filter(
            group=group,
            status="active",
        )
        .select_related("user")
        .order_by("joined_at", "id")
    )


# ==========================================================
# ROTATION SCHEDULE GENERATION
# ==========================================================

@transaction.atomic
def generate_rotation_schedule(group):
    """
    Generate one rotation turn for every active group member.

    Rotation rules:

    1. Every active member receives one turn.
    2. Every member contributes during each contribution period.
    3. The first payout is scheduled after one complete
       contribution cycle.
    4. Subsequent payouts are scheduled after another
       complete contribution cycle.
    5. The earliest active member receives the first turn.

    Expected payout:

        Contribution amount x Number of members x Number
        of contribution periods per turn

    Existing valid schedules are returned instead of duplicated.
    """

    # Lock the group to prevent simultaneous schedule generation.
    group = SavingsGroup.objects.select_for_update().get(
        pk=group.pk
    )

    validate_group_for_rotation(group)

    # Get active members.
    memberships = get_active_group_memberships(group)

    member_count = len(memberships)

    if member_count < 2:
        raise ValidationError(
            "At least two active members are required to generate a rotation schedule."
        )

    # Get any existing rotation turns.
    existing_turns = list(
        RotationTurn.objects.filter(
            group=group
        )
        .select_related("membership__user")
        .order_by("turn_number")
    )

    # Make generation safe to repeat.
    if existing_turns:

        existing_membership_ids = [
            turn.membership_id
            for turn in existing_turns
        ]

        current_membership_ids = [
            membership.id
            for membership in memberships
        ]

        # Return the existing schedule if it already matches
        # the current active membership list.
        if (
            len(existing_turns) == member_count
            and existing_membership_ids == current_membership_ids
        ):
            return existing_turns

        raise ValidationError(
            "A rotation schedule already exists, but its membership "
            "does not match the current active members. "
            "Review the existing schedule before making changes."
        )

    # Every member contributes once per contribution period.
    # One payout covers one complete contribution cycle.
    expected_payout = (
        group.contribution_amount
        * member_count
        * member_count
    )

    rotation_turns = []

    for index, membership in enumerate(memberships):

        # First payout occurs after member_count - 1 periods.
        # Each subsequent payout occurs after another full cycle.
        periods = (
            member_count - 1
            + (index * member_count)
        )

        scheduled_date = add_frequency_periods(
            group.start_date,
            group.contribution_frequency,
            periods,
        )

        rotation_turns.append(
            RotationTurn(
                group=group,
                membership=membership,
                turn_number=index + 1,
                scheduled_date=scheduled_date,
                expected_amount=expected_payout,
                status="upcoming",
            )
        )

    # Create all turns together.
    RotationTurn.objects.bulk_create(
        rotation_turns
    )

    # Return the generated schedule.
    return list(
        RotationTurn.objects.filter(
            group=group
        )
        .select_related("membership__user")
        .order_by("turn_number")
    )


# ==========================================================
# ROTATION LOOKUPS
# ==========================================================

def get_next_rotation_turn(group):
    """
    Get the next upcoming rotation turn.
    """

    return (
        RotationTurn.objects.filter(
            group=group,
            status="upcoming",
        )
        .select_related(
            "membership__user",
            "group",
        )
        .order_by(
            "turn_number"
        )
        .first()
    )


def get_current_rotation_turn(group):
    """
    Get the currently active rotation turn.
    """

    return (
        RotationTurn.objects.filter(
            group=group,
            status="current",
        )
        .select_related(
            "membership__user",
            "group",
        )
        .order_by(
            "turn_number"
        )
        .first()
    )


def get_completed_rotation_turns(group):
    """
    Return all completed rotation turns.
    """

    return (
        RotationTurn.objects.filter(
            group=group,
            status="completed",
        )
        .select_related(
            "membership__user"
        )
        .order_by(
            "turn_number"
        )
    )


# ==========================================================
# ROTATION SUMMARY
# ==========================================================

def get_group_rotation_summary(group):
    """
    Return rotation statistics for a savings group.
    """

    turns = RotationTurn.objects.filter(
        group=group
    )

    next_turn = get_next_rotation_turn(group)

    current_turn = get_current_rotation_turn(group)

    return {
        "total_turns": turns.count(),

        "completed_turns": turns.filter(
            status="completed"
        ).count(),

        "current_turn": current_turn,

        "upcoming_turns": turns.filter(
            status="upcoming"
        ).count(),

        "next_turn": next_turn,

        "is_schedule_generated": turns.exists(),

        "is_rotation_completed": (
            turns.exists()
            and not turns.filter(
                status__in=["upcoming", "current"]
            ).exists()
        ),
    }
