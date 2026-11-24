
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import (
    SavingsGroup,
    GroupMembership,
    Contribution,
    RotationTurn,
    Payout,
    Notification,
)

from .forms import (
    SavingsGroupForm,
    AddMemberForm,
    ContributionForm,
)


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def get_user_membership(group, user):
    """
    Return the user's active membership in a particular group.
    """

    return get_object_or_404(
        GroupMembership,
        group=group,
        user=user,
        status="active",
    )


def is_group_admin(group, user):
    """
    Check whether the user is an active administrator
    of the specified group.
    """

    if not user.is_authenticated:
        return False

    return GroupMembership.objects.filter(
        group=group,
        user=user,
        role="admin",
        status="active",
    ).exists()


def get_contribution_totals(queryset):
    """
    Calculate paid, pending and failed contribution totals.
    """

    return {
        "total_paid": queryset.filter(
            status="paid"
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0,

        "total_pending": queryset.filter(
            status__in=["pending", "processing"]
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0,

        "total_failed": queryset.filter(
            status__in=["failed", "cancelled"]
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0,
    }


def get_unread_notification_count(user):
    """
    Return the number of unread notifications
    belonging to a particular user.
    """

    return Notification.objects.filter(
        user=user,
        is_read=False,
    ).count()


# ==================================================
# DASHBOARD
# ==================================================

@login_required
def dashboard_view(request):
    """
    Display the logged-in user's savings dashboard.
    """

    # Groups the user actively belongs to.
    groups = (
        GroupMembership.objects.filter(
            user=request.user,
            status="active",
        )
        .select_related("group", "user")
        .order_by("-joined_at")
    )

    total_groups = groups.count()

    # Contributions made by the logged-in user.
    user_contributions = (
        Contribution.objects.filter(
            membership__user=request.user,
            membership__status="active",
        )
    )

    # Total amount successfully contributed.
    total_contributions = (
        user_contributions.filter(
            status="paid"
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0
    )

    # Number of distinct members across the user's groups.
    total_members = (
        GroupMembership.objects.filter(
            group_id__in=groups.values("group_id"),
            status="active",
        )
        .values("user_id")
        .distinct()
        .count()
    )

    # Latest contributions made by the user.
    recent_contributions = (
        user_contributions
        .select_related(
            "group",
            "membership",
            "membership__user",
        )
        .order_by("-created_at")[:5]
    )

    # Upcoming payout turns belonging to the user.
    upcoming_turns = (
        RotationTurn.objects.filter(
            membership__user=request.user,
            membership__status="active",
            status="upcoming",
        )
        .select_related(
            "group",
            "membership",
            "membership__user",
        )
        .order_by("scheduled_date")[:5]
    )

    unread_notifications = get_unread_notification_count(
        request.user
    )

    # Latest notifications for the dashboard.
    notifications = (
        Notification.objects.filter(
            user=request.user,
        )
        .select_related("group")
        .order_by("-created_at")[:5]
    )

    context = {
        "groups": groups,
        "total_groups": total_groups,
        "total_contributions": total_contributions,
        "total_members": total_members,
        "recent_contributions": recent_contributions,
        "upcoming_turns": upcoming_turns,
        "notifications": notifications,
        "unread_notifications": unread_notifications,
    }

    return render(
        request,
        "dashboard.html",
        context,
    )


# ==================================================
# SAVINGS GROUPS
# ==================================================

@login_required
def create_group_view(request):
    """
    Allow an authenticated user to request creation
    of a savings group.

    The group remains pending until a platform
    administrator activates it.
    """

    if request.method == "POST":

        form = SavingsGroupForm(request.POST)

        if form.is_valid():

            with transaction.atomic():

                group = form.save(commit=False)

                group.creator = request.user
                group.status = "pending"

                group.save()

                # The creator becomes an administrator
                # of this particular group.
                GroupMembership.objects.create(
                    group=group,
                    user=request.user,
                    role="admin",
                    status="active",
                )

            messages.success(
                request,
                "Your group creation request has been submitted. "
                "The group will become active after administrator approval.",
            )

            return redirect(
                "savings:group_detail",
                pk=group.pk,
            )

    else:
        form = SavingsGroupForm()

    return render(
        request,
        "create_group.html",
        {
            "form": form,
            "unread_notifications": get_unread_notification_count(
                request.user
            ),
        },
    )


@login_required
def group_detail_view(request, pk):
    """
    Display details of a group the user belongs to.
    """

    group = get_object_or_404(
        SavingsGroup,
        pk=pk,
    )

    membership = get_user_membership(
        group,
        request.user,
    )

    members = (
        GroupMembership.objects.filter(
            group=group,
            status="active",
        )
        .select_related("user")
        .order_by("joined_at")
    )

    total_contributions = (
        Contribution.objects.filter(
            group=group,
            status="paid",
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0
    )

    next_turn = (
        RotationTurn.objects.filter(
            group=group,
            status="upcoming",
        )
        .select_related("membership__user")
        .order_by("turn_number")
        .first()
    )

    context = {
        "group": group,
        "membership": membership,
        "members": members,
        "member_count": members.count(),
        "total_contributions": total_contributions,
        "next_turn": next_turn,
        "is_admin": is_group_admin(group, request.user),
        "unread_notifications": get_unread_notification_count(
            request.user
        ),
    }

    return render(
        request,
        "group_detail.html",
        context,
    )


# ==================================================
# GROUP MEMBERS
# ==================================================

@login_required
def members_view(request, pk):
    """
    Display active members of a savings group.
    """

    group = get_object_or_404(
        SavingsGroup,
        pk=pk,
    )

    # Only active group members can access this page.
    get_user_membership(group, request.user)

    members = (
        GroupMembership.objects.filter(
            group=group,
            status="active",
        )
        .select_related("user")
        .order_by("joined_at")
    )

    context = {
        "group": group,
        "members": members,
        "member_count": members.count(),
        "is_admin": is_group_admin(group, request.user),
        "unread_notifications": get_unread_notification_count(
            request.user
        ),
    }

    return render(
        request,
        "members.html",
        context,
    )


@login_required
def add_member_view(request, pk):
    """
    Allow active group administrators to add members.
    """

    group = get_object_or_404(
        SavingsGroup,
        pk=pk,
    )

    # Confirm that the user is an administrator
    # of this particular group.
    if not is_group_admin(group, request.user):

        messages.error(
            request,
            "You are not authorized to add members to this group.",
        )

        return redirect(
            "savings:group_detail",
            pk=group.pk,
        )

    # Only active groups can accept new members.
    if group.status != "active":

        messages.warning(
            request,
            "You can only add members to an active savings group.",
        )

        return redirect(
            "savings:group_detail",
            pk=group.pk,
        )

    member_count = GroupMembership.objects.filter(
        group=group,
        status="active",
    ).count()

    if request.method == "POST":

        form = AddMemberForm(
            request.POST,
            group=group,
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "The member has been added successfully.",
            )

            return redirect(
                "savings:members",
                pk=group.pk,
            )

    else:

        form = AddMemberForm(
            group=group,
        )

    return render(
        request,
        "add_member.html",
        {
            "form": form,
            "group": group,
            "member_count": member_count,
            "is_admin": True,
            "unread_notifications": get_unread_notification_count(
                request.user
            ),
        },
    )


# ==================================================
# CONTRIBUTIONS
# ==================================================

@login_required
def contributions_view(request, pk):
    """
    Display contributions belonging to a savings group.
    """

    group = get_object_or_404(
        SavingsGroup,
        pk=pk,
    )

    # Only active group members can view contribution records.
    get_user_membership(group, request.user)

    contributions = (
        Contribution.objects.filter(
            group=group,
        )
        .select_related(
            "membership",
            "membership__user",
        )
        .order_by("-created_at")
    )

    context = {
        "group": group,
        "contributions": contributions,
        **get_contribution_totals(contributions),
        "is_admin": is_group_admin(group, request.user),
        "unread_notifications": get_unread_notification_count(
            request.user
        ),
    }

    return render(
        request,
        "contributions.html",
        context,
    )


@login_required
def make_contribution_view(request, pk):
    """
    Allow a member to create a contribution record
    only for their own membership.
    """

    group = get_object_or_404(
        SavingsGroup,
        pk=pk,
    )

    membership = get_user_membership(
        group,
        request.user,
    )

    if group.status != "active":

        messages.error(
            request,
            "Contributions are not currently open for this group.",
        )

        return redirect(
            "savings:group_detail",
            pk=group.pk,
        )

    if request.method == "POST":

        form = ContributionForm(
            request.POST,
            group=group,
        )

        # Restrict the membership field to the logged-in user.
        form.fields["membership"].queryset = (
            GroupMembership.objects.filter(
                pk=membership.pk,
                group=group,
                user=request.user,
                status="active",
            )
        )

        if form.is_valid():

            contribution = form.save()

            messages.success(
                request,
                "Your contribution record has been created. "
                "Payment is still pending.",
            )

            return redirect(
                "savings:payment_history",
            )

    else:

        form = ContributionForm(
            group=group,
        )

        form.fields["membership"].queryset = (
            GroupMembership.objects.filter(
                pk=membership.pk,
                group=group,
                user=request.user,
                status="active",
            )
        )

    return render(
        request,
        "make_contribution.html",
        {
            "form": form,
            "group": group,
            "unread_notifications": get_unread_notification_count(
                request.user
            ),
        },
    )


@login_required
def payment_history_view(request):
    """
    Display the logged-in user's contribution history.
    """

    contributions = (
        Contribution.objects.filter(
            membership__user=request.user,
        )
        .select_related(
            "group",
            "membership",
        )
        .order_by("-created_at")
    )

    context = {
        "contributions": contributions,
        **get_contribution_totals(contributions),
        "unread_notifications": get_unread_notification_count(
            request.user
        ),
    }

    return render(
        request,
        "payment_history.html",
        context,
    )


# ==================================================
# ROTATION SCHEDULE
# ==================================================

@login_required
def rotation_schedule_view(request, pk):
    """
    Display the rotation schedule of a group.
    """

    group = get_object_or_404(
        SavingsGroup,
        pk=pk,
    )

    get_user_membership(
        group,
        request.user,
    )

    rotation_turns = (
        RotationTurn.objects.filter(
            group=group,
        )
        .select_related(
            "membership__user",
        )
        .order_by("turn_number")
    )

    context = {
        "group": group,
        "rotation_turns": rotation_turns,
        "is_admin": is_group_admin(group, request.user),
        "unread_notifications": get_unread_notification_count(
            request.user
        ),
    }

    return render(
        request,
        "rotation_schedule.html",
        context,
    )


# ==================================================
# PAYOUTS
# ==================================================

@login_required
def payouts_view(request, pk):
    """
    Display payouts belonging to a savings group.
    """

    group = get_object_or_404(
        SavingsGroup,
        pk=pk,
    )

    get_user_membership(
        group,
        request.user,
    )

    payouts = (
        Payout.objects.filter(
            rotation_turn__group=group,
        )
        .select_related(
            "recipient",
            "rotation_turn",
            "approved_by",
        )
        .order_by("-created_at")
    )

    total_paid = (
        payouts.filter(
            status="paid",
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0
    )

    total_pending = (
        payouts.filter(
            status__in=["pending", "processing"],
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0
    )

    context = {
        "group": group,
        "payouts": payouts,
        "total_paid": total_paid,
        "total_pending": total_pending,
        "is_admin": is_group_admin(group, request.user),
        "unread_notifications": get_unread_notification_count(
            request.user
        ),
    }

    return render(
        request,
        "payouts.html",
        context,
    )


# ==================================================
# NOTIFICATIONS
# ==================================================

@login_required
def notifications_view(request):
    """
    Display all notifications belonging to the logged-in user.
    """

    notifications = (
        Notification.objects.filter(
            user=request.user,
        )
        .select_related("group")
        .order_by("-created_at")
    )

    unread_notifications = get_unread_notification_count(
        request.user
    )

    context = {
        "notifications": notifications,
        "unread_notifications": unread_notifications,
    }

    return render(
        request,
        "notifications.html",
        context,
    )


@login_required
@require_POST
def mark_notification_read_view(request, pk):
    """
    Mark only the logged-in user's notification as read.
    """

    notification = get_object_or_404(
        Notification,
        pk=pk,
        user=request.user,
    )

    if not notification.is_read:

        notification.is_read = True

        notification.save(
            update_fields=["is_read"],
        )

        messages.success(
            request,
            "Notification marked as read.",
        )

    return redirect(
        "savings:notifications",
    )
