
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import (
    SavingsGroup,
    GroupMembership,
    Contribution,
    Payout,
    Notification,
)


@receiver(post_save, sender=SavingsGroup)
def notify_group_creator(sender, instance, created, **kwargs):
    """Notify the creator when a savings group is created."""

    if created:
        Notification.objects.create(
            user=instance.creator,
            group=instance,
            title="Savings Group Created",
            message=(
                f"Your savings group '{instance.name}' "
                "has been created successfully."
            ),
            notification_type="group",
        )


@receiver(post_save, sender=GroupMembership)
def notify_new_member(sender, instance, created, **kwargs):
    """Notify a user when they are added to a savings group."""

    if created:
        Notification.objects.create(
            user=instance.user,
            group=instance.group,
            title="Group Membership",
            message=(
                f"You have been added to "
                f"'{instance.group.name}' as a "
                f"{instance.get_role_display()}."
            ),
            notification_type="group",
        )


@receiver(post_save, sender=Contribution)
def notify_successful_contribution(sender, instance, **kwargs):
    """Notify a member when their contribution is paid."""

    if instance.status == "paid":
        Notification.objects.get_or_create(
            user=instance.membership.user,
            group=instance.group,
            title="Contribution Successful",
            message=(
                f"Your contribution of KSh {instance.amount} "
                f"to '{instance.group.name}' was successful."
            ),
            notification_type="contribution",
        )


@receiver(post_save, sender=Payout)
def notify_successful_payout(sender, instance, **kwargs):
    """Notify a member when their payout is completed."""

    if instance.status == "paid":
        Notification.objects.get_or_create(
            user=instance.recipient,
            group=instance.rotation_turn.group,
            title="Payout Successful",
            message=(
                f"Your payout of KSh {instance.amount} "
                f"from '{instance.rotation_turn.group.name}' "
                "has been completed."
            ),
            notification_type="payout",
        )
