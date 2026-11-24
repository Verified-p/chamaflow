
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import (
    SavingsGroup,
    GroupMembership,
    Contribution,
    RotationTurn,
    Payout,
    Notification,
)

from .services.rotation import (
    generate_rotation_schedule as build_rotation_schedule,
)


@admin.register(SavingsGroup)
class SavingsGroupAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "creator",
        "contribution_amount",
        "contribution_frequency",
        "start_date",
        "status",
        "active_member_count",
        "rotation_turn_count",
        "created_at",
    )

    list_filter = (
        "status",
        "contribution_frequency",
        "created_at",
    )

    search_fields = (
        "name",
        "creator__username",
        "creator__phone_number",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)

    actions = (
        "activate_and_generate_rotation",
        "generate_rotation_for_active_groups",
    )

    @admin.display(description="Active Members")
    def active_member_count(self, obj):
        return GroupMembership.objects.filter(
            group=obj,
            status="active",
        ).count()

    @admin.display(description="Rotation Turns")
    def rotation_turn_count(self, obj):
        return RotationTurn.objects.filter(
            group=obj,
        ).count()

    def save_model(self, request, obj, form, change):
        """
        Automatically generate a rotation schedule when a group
        changes from a non-active status to active.
        """

        previous_status = None

        if change and obj.pk:
            previous_status = SavingsGroup.objects.filter(
                pk=obj.pk
            ).values_list(
                "status",
                flat=True,
            ).first()

        super().save_model(request, obj, form, change)

        if (
            obj.status == "active"
            and previous_status != "active"
        ):
            try:
                build_rotation_schedule(obj)

                self.message_user(
                    request,
                    f"Rotation schedule generated successfully for {obj.name}.",
                    level=messages.SUCCESS,
                )

            except ValidationError as error:
                self.message_user(
                    request,
                    (
                        f"{obj.name} was saved as active, but its rotation "
                        f"schedule could not be generated: {error}"
                    ),
                    level=messages.WARNING,
                )

    @admin.action(
        description="Activate selected groups and generate rotation schedules"
    )
    def activate_and_generate_rotation(self, request, queryset):
        successful = 0
        failed = 0

        for selected_group in queryset:
            try:
                with transaction.atomic():
                    group = SavingsGroup.objects.select_for_update().get(
                        pk=selected_group.pk
                    )

                    if group.status != "active":
                        group.status = "active"
                        group.save(
                            update_fields=[
                                "status",
                                "updated_at",
                            ]
                        )

                    build_rotation_schedule(group)

                successful += 1

            except ValidationError as error:
                failed += 1

                self.message_user(
                    request,
                    f"{selected_group.name}: {error}",
                    level=messages.WARNING,
                )

        if successful:
            self.message_user(
                request,
                (
                    f"Successfully activated and generated rotation "
                    f"schedules for {successful} group(s)."
                ),
                level=messages.SUCCESS,
            )

        if failed:
            self.message_user(
                request,
                f"Could not generate schedules for {failed} group(s).",
                level=messages.ERROR,
            )

    @admin.action(
        description="Generate missing rotation schedules for active groups"
    )
    def generate_rotation_for_active_groups(self, request, queryset):
        successful = 0
        failed = 0

        active_groups = queryset.filter(status="active")

        for selected_group in active_groups:
            try:
                with transaction.atomic():
                    group = SavingsGroup.objects.select_for_update().get(
                        pk=selected_group.pk
                    )

                    build_rotation_schedule(group)

                successful += 1

            except ValidationError as error:
                failed += 1

                self.message_user(
                    request,
                    f"{selected_group.name}: {error}",
                    level=messages.WARNING,
                )

        if successful:
            self.message_user(
                request,
                (
                    f"Successfully processed rotation schedules for "
                    f"{successful} active group(s)."
                ),
                level=messages.SUCCESS,
            )

        if failed:
            self.message_user(
                request,
                f"Could not generate schedules for {failed} group(s).",
                level=messages.ERROR,
            )

        if not active_groups.exists():
            self.message_user(
                request,
                "No active groups were selected.",
                level=messages.WARNING,
            )


@admin.register(GroupMembership)
class GroupMembershipAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "group",
        "role",
        "status",
        "joined_at",
    )

    list_filter = (
        "role",
        "status",
        "joined_at",
    )

    search_fields = (
        "user__username",
        "user__phone_number",
        "group__name",
    )

    readonly_fields = (
        "joined_at",
    )

    ordering = ("-joined_at",)


@admin.register(Contribution)
class ContributionAdmin(admin.ModelAdmin):

    list_display = (
        "membership",
        "group",
        "amount",
        "due_date",
        "status",
        "mpesa_receipt_number",
        "paid_at",
    )

    list_filter = (
        "status",
        "due_date",
        "paid_at",
    )

    search_fields = (
        "membership__user__username",
        "membership__user__phone_number",
        "group__name",
        "mpesa_receipt_number",
        "checkout_request_id",
    )

    readonly_fields = (
        "merchant_request_id",
        "checkout_request_id",
        "mpesa_receipt_number",
        "result_code",
        "result_description",
        "paid_at",
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)


@admin.register(RotationTurn)
class RotationTurnAdmin(admin.ModelAdmin):

    list_display = (
        "group",
        "membership",
        "turn_number",
        "scheduled_date",
        "expected_amount",
        "status",
    )

    list_filter = (
        "status",
        "scheduled_date",
    )

    search_fields = (
        "group__name",
        "membership__user__username",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = (
        "group",
        "turn_number",
    )


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):

    list_display = (
        "recipient",
        "rotation_turn",
        "amount",
        "phone_number",
        "status",
        "transaction_reference",
        "paid_at",
    )

    list_filter = (
        "status",
        "paid_at",
        "created_at",
    )

    search_fields = (
        "recipient__username",
        "recipient__phone_number",
        "transaction_reference",
    )

    readonly_fields = (
        "transaction_reference",
        "paid_at",
        "created_at",
        "updated_at",
    )

    ordering = ("-created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "user",
        "group",
        "notification_type",
        "is_read",
        "created_at",
    )

    list_filter = (
        "notification_type",
        "is_read",
        "created_at",
    )

    search_fields = (
        "title",
        "message",
        "user__username",
        "group__name",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = ("-created_at",)
