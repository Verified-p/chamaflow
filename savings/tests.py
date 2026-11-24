
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    SavingsGroup,
    GroupMembership,
    Contribution,
    RotationTurn,
    Payout,
    Notification,
)

User = get_user_model()


class SavingsGroupModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="andrew",
            password="TestPassword123!",
            phone_number="0712345678",
        )

    def test_create_savings_group(self):
        group = SavingsGroup.objects.create(
            name="Developers Chama",
            creator=self.user,
            contribution_amount=Decimal("100.00"),
            contribution_frequency="daily",
            start_date=date.today(),
        )

        self.assertEqual(group.name, "Developers Chama")
        self.assertEqual(group.creator, self.user)
        self.assertEqual(group.status, "pending")

    def test_group_string_representation(self):
        group = SavingsGroup.objects.create(
            name="Students Chama",
            creator=self.user,
            contribution_amount=Decimal("200.00"),
            start_date=date.today(),
        )

        self.assertEqual(str(group), "Students Chama")


class GroupMembershipModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="member1",
            password="TestPassword123!",
            phone_number="0712345678",
        )

        self.group = SavingsGroup.objects.create(
            name="Test Chama",
            creator=self.user,
            contribution_amount=Decimal("100.00"),
            start_date=date.today(),
        )

    def test_create_group_membership(self):
        membership = GroupMembership.objects.create(
            group=self.group,
            user=self.user,
            role="admin",
            status="active",
        )

        self.assertEqual(membership.group, self.group)
        self.assertEqual(membership.user, self.user)
        self.assertEqual(membership.role, "admin")

    def test_duplicate_membership_is_rejected(self):
        GroupMembership.objects.create(
            group=self.group,
            user=self.user,
            status="active",
        )

        with self.assertRaises(Exception):
            GroupMembership.objects.create(
                group=self.group,
                user=self.user,
                status="active",
            )


class ContributionModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="contributor",
            password="TestPassword123!",
            phone_number="0712345678",
        )

        self.group = SavingsGroup.objects.create(
            name="Savings Group",
            creator=self.user,
            contribution_amount=Decimal("100.00"),
            start_date=date.today(),
            status="active",
        )

        self.membership = GroupMembership.objects.create(
            group=self.group,
            user=self.user,
            role="admin",
            status="active",
        )

    def test_create_pending_contribution(self):
        contribution = Contribution.objects.create(
            group=self.group,
            membership=self.membership,
            amount=Decimal("100.00"),
            due_date=date.today(),
            phone_number="0712345678",
        )

        self.assertEqual(contribution.status, "pending")
        self.assertEqual(contribution.amount, Decimal("100.00"))

    def test_contribution_can_be_marked_as_paid(self):
        contribution = Contribution.objects.create(
            group=self.group,
            membership=self.membership,
            amount=Decimal("100.00"),
            due_date=date.today(),
            phone_number="0712345678",
        )

        contribution.mark_as_paid()
        contribution.refresh_from_db()

        self.assertEqual(contribution.status, "paid")
        self.assertIsNotNone(contribution.paid_at)

    def test_duplicate_contribution_for_same_date_is_rejected(self):
        Contribution.objects.create(
            group=self.group,
            membership=self.membership,
            amount=Decimal("100.00"),
            due_date=date.today(),
            phone_number="0712345678",
        )

        with self.assertRaises(Exception):
            Contribution.objects.create(
                group=self.group,
                membership=self.membership,
                amount=Decimal("100.00"),
                due_date=date.today(),
                phone_number="0712345678",
            )


class RotationAndPayoutModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="recipient",
            password="TestPassword123!",
            phone_number="0712345678",
        )

        self.group = SavingsGroup.objects.create(
            name="Rotation Chama",
            creator=self.user,
            contribution_amount=Decimal("100.00"),
            start_date=date.today(),
        )

        self.membership = GroupMembership.objects.create(
            group=self.group,
            user=self.user,
            role="admin",
            status="active",
        )

    def test_create_rotation_turn(self):
        turn = RotationTurn.objects.create(
            group=self.group,
            membership=self.membership,
            turn_number=1,
            scheduled_date=date.today(),
            expected_amount=Decimal("500.00"),
        )

        self.assertEqual(turn.status, "upcoming")
        self.assertEqual(turn.turn_number, 1)

    def test_create_payout(self):
        turn = RotationTurn.objects.create(
            group=self.group,
            membership=self.membership,
            turn_number=1,
            scheduled_date=date.today(),
            expected_amount=Decimal("500.00"),
        )

        payout = Payout.objects.create(
            rotation_turn=turn,
            recipient=self.user,
            amount=Decimal("500.00"),
            phone_number="0712345678",
        )

        self.assertEqual(payout.status, "pending")
        self.assertEqual(payout.recipient, self.user)


class NotificationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="notificationuser",
            password="TestPassword123!",
            phone_number="0712345678",
        )

    def test_create_notification(self):
        notification = Notification.objects.create(
            user=self.user,
            title="Contribution Reminder",
            message="Your contribution is due today.",
            notification_type="reminder",
        )

        self.assertEqual(notification.title, "Contribution Reminder")
        self.assertFalse(notification.is_read)


class SavingsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="viewuser",
            password="TestPassword123!",
            phone_number="0712345678",
        )

        self.group = SavingsGroup.objects.create(
            name="View Test Chama",
            creator=self.user,
            contribution_amount=Decimal("100.00"),
            start_date=date.today(),
            status="active",
        )

        self.membership = GroupMembership.objects.create(
            group=self.group,
            user=self.user,
            role="admin",
            status="active",
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("savings:dashboard"))

        self.assertEqual(response.status_code, 302)

    def test_dashboard_for_logged_in_user(self):
        self.client.login(
            username="viewuser",
            password="TestPassword123!",
        )

        response = self.client.get(reverse("savings:dashboard"))

        self.assertEqual(response.status_code, 200)

    def test_group_detail_requires_membership(self):
        other_user = User.objects.create_user(
            username="outsider",
            password="TestPassword123!",
            phone_number="0712345679",
        )

        self.client.login(
            username="outsider",
            password="TestPassword123!",
        )

        response = self.client.get(
            reverse(
                "savings:group_detail",
                kwargs={"pk": self.group.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_group_creator_can_view_group(self):
        self.client.login(
            username="viewuser",
            password="TestPassword123!",
        )

        response = self.client.get(
            reverse(
                "savings:group_detail",
                kwargs={"pk": self.group.pk},
            )
        )

        self.assertEqual(response.status_code, 200)

    def test_notification_can_be_marked_as_read(self):
        notification = Notification.objects.create(
            user=self.user,
            title="Test Notification",
            message="Testing notification status.",
        )

        self.client.login(
            username="viewuser",
            password="TestPassword123!",
        )

        response = self.client.post(
            reverse(
                "savings:mark_notification_read",
                kwargs={"pk": notification.pk},
            )
        )

        self.assertEqual(response.status_code, 302)

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)


