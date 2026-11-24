
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


# =====================================================
# 1. SAVINGS GROUP
# =====================================================

class SavingsGroup(models.Model):

    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('suspended', 'Suspended'),
    ]

    name = models.CharField(max_length=150)

    description = models.TextField(blank=True)

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_savings_groups'
    )

    contribution_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    contribution_frequency = models.CharField(
        max_length=10,
        choices=FREQUENCY_CHOICES,
        default='monthly'
    )

    start_date = models.DateField()

    end_date = models.DateField(
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='pending'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


# =====================================================
# 2. GROUP MEMBERSHIP
# =====================================================

class GroupMembership(models.Model):

    ROLE_CHOICES = [
        ('admin', 'Group Admin'),
        ('member', 'Member'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('left', 'Left'),
        ('removed', 'Removed'),
    ]

    group = models.ForeignKey(
        SavingsGroup,
        on_delete=models.CASCADE,
        related_name='memberships'
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='savings_memberships'
    )

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='member'
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['joined_at']
        constraints = [
            models.UniqueConstraint(
                fields=['group', 'user'],
                name='unique_group_member'
            )
        ]

    def __str__(self):
        return f'{self.user.username} - {self.group.name}'


# =====================================================
# 3. CONTRIBUTIONS
# =====================================================

class Contribution(models.Model):

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    group = models.ForeignKey(
        SavingsGroup,
        on_delete=models.PROTECT,
        related_name='contributions'
    )

    membership = models.ForeignKey(
        GroupMembership,
        on_delete=models.PROTECT,
        related_name='contributions'
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    due_date = models.DateField()

    phone_number = models.CharField(
        max_length=15
    )

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # Safaricom Daraja transaction information
    merchant_request_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    checkout_request_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True
    )

    mpesa_receipt_number = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        unique=True
    )

    result_code = models.CharField(
        max_length=10,
        blank=True,
        null=True
    )

    result_description = models.TextField(blank=True)

    paid_at = models.DateTimeField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['membership', 'due_date'],
                name='unique_membership_contribution_date'
            )
        ]

    def __str__(self):
        return f'{self.membership.user.username} - KSh {self.amount}'

    def mark_as_paid(self):
        """
        Mark a contribution as paid after verifying
        a successful M-Pesa callback.
        """
        self.status = 'paid'
        self.paid_at = timezone.now()
        self.save(update_fields=['status', 'paid_at', 'updated_at'])


# =====================================================
# 4. ROTATION SCHEDULE
# =====================================================

class RotationTurn(models.Model):

    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('current', 'Current'),
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
    ]

    group = models.ForeignKey(
        SavingsGroup,
        on_delete=models.CASCADE,
        related_name='rotation_turns'
    )

    membership = models.ForeignKey(
        GroupMembership,
        on_delete=models.PROTECT,
        related_name='rotation_turns'
    )

    turn_number = models.PositiveIntegerField()

    scheduled_date = models.DateField()

    expected_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='upcoming'
    )

    completed_at = models.DateTimeField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['turn_number']
        constraints = [
            models.UniqueConstraint(
                fields=['group', 'turn_number'],
                name='unique_group_turn_number'
            ),
            models.UniqueConstraint(
                fields=['group', 'membership'],
                name='unique_group_rotation_member'
            )
        ]

    def __str__(self):
        return f'{self.group.name} - Turn {self.turn_number}'


# =====================================================
# 5. PAYOUTS
# =====================================================

class Payout(models.Model):

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    rotation_turn = models.OneToOneField(
        RotationTurn,
        on_delete=models.PROTECT,
        related_name='payout'
    )

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='received_payouts'
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    phone_number = models.CharField(
        max_length=15
    )

    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='pending'
    )

    transaction_reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='approved_payouts',
        blank=True,
        null=True
    )

    paid_at = models.DateTimeField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.recipient.username} - KSh {self.amount}'


# =====================================================
# 6. NOTIFICATIONS
# =====================================================

class Notification(models.Model):

    TYPE_CHOICES = [
        ('contribution', 'Contribution'),
        ('payout', 'Payout'),
        ('group', 'Group Update'),
        ('reminder', 'Reminder'),
        ('general', 'General'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='savings_notifications'
    )

    group = models.ForeignKey(
        SavingsGroup,
        on_delete=models.CASCADE,
        related_name='notifications',
        blank=True,
        null=True
    )

    title = models.CharField(max_length=150)

    message = models.TextField()

    notification_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='general'
    )

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} - {self.user.username}'
