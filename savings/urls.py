
from django.urls import path
from . import views

app_name = "savings"

urlpatterns = [

    # ==================================================
    # DASHBOARD
    # ==================================================

    path(
        "",
        views.dashboard_view,
        name="dashboard",
    ),

    # ==================================================
    # SAVINGS GROUPS
    # ==================================================

    path(
        "groups/create/",
        views.create_group_view,
        name="create_group",
    ),

    path(
        "groups/<int:pk>/",
        views.group_detail_view,
        name="group_detail",
    ),

    # ==================================================
    # GROUP MEMBERS
    # ==================================================

    path(
        "groups/<int:pk>/members/",
        views.members_view,
        name="members",
    ),

    path(
        "groups/<int:pk>/members/add/",
        views.add_member_view,
        name="add_member",
    ),

    # ==================================================
    # CONTRIBUTIONS
    # ==================================================

    path(
        "groups/<int:pk>/contributions/",
        views.contributions_view,
        name="contributions",
    ),

    path(
        "groups/<int:pk>/contribute/",
        views.make_contribution_view,
        name="make_contribution",
    ),

    path(
        "payment-history/",
        views.payment_history_view,
        name="payment_history",
    ),

    # ==================================================
    # ROTATION SCHEDULE
    # ==================================================

    path(
        "groups/<int:pk>/rotation/",
        views.rotation_schedule_view,
        name="rotation_schedule",
    ),

    # ==================================================
    # PAYOUTS
    # ==================================================

    path(
        "groups/<int:pk>/payouts/",
        views.payouts_view,
        name="payouts",
    ),

    # ==================================================
    # NOTIFICATIONS
    # ==================================================

    path(
        "notifications/",
        views.notifications_view,
        name="notifications",
    ),

    path(
        "notifications/<int:pk>/read/",
        views.mark_notification_read_view,
        name="mark_notification_read",
    ),

]
