
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from .forms import RegisterForm, LoginForm, ProfileUpdateForm

User = get_user_model()


class AccountsTestCase(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='andrew',
            first_name='Andrew',
            last_name='Otieno',
            phone_number='0712345678',
            email='andrew@example.com',
            password='StrongPass123!'
        )

    # Registration Tests

    def test_user_registration(self):
        form = RegisterForm(data={
            'first_name': 'John',
            'last_name': 'Doe',
            'username': 'johndoe',
            'phone_number': '0723456789',
            'email': 'john@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })

        self.assertTrue(form.is_valid(), form.errors)

        user = form.save()

        self.assertEqual(user.username, 'johndoe')
        self.assertTrue(user.check_password('StrongPass123!'))

    def test_duplicate_phone_number(self):
        form = RegisterForm(data={
            'first_name': 'Jane',
            'last_name': 'Doe',
            'username': 'janedoe',
            'phone_number': '0712345678',
            'email': 'jane@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })

        self.assertFalse(form.is_valid())
        self.assertIn('phone_number', form.errors)

    # Login Tests

    def test_login_with_username(self):
        form = LoginForm(data={
            'username': 'andrew',
            'password': 'StrongPass123!'
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.get_user(), self.user)

    def test_login_with_phone_number(self):
        form = LoginForm(data={
            'username': '0712345678',
            'password': 'StrongPass123!'
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.get_user(), self.user)

    def test_invalid_login(self):
        form = LoginForm(data={
            'username': 'andrew',
            'password': 'WrongPassword123!'
        })

        self.assertFalse(form.is_valid())

    # Profile Tests

    def test_profile_view_requires_login(self):
        response = self.client.get(
            reverse('accounts:profile')
        )

        self.assertEqual(response.status_code, 302)

    def test_authenticated_user_can_view_profile(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('accounts:profile')
        )

        self.assertEqual(response.status_code, 200)

    def test_profile_update(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('accounts:edit_profile'),
            {
                'first_name': 'Andrew Updated',
                'last_name': 'Otieno',
                'username': 'andrew',
                'phone_number': '0712345678',
                'email': 'updated@example.com',
            }
        )

        self.user.refresh_from_db()

        self.assertEqual(self.user.first_name, 'Andrew Updated')
        self.assertEqual(self.user.email, 'updated@example.com')

    # Logout Test

    def test_user_logout(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('accounts:logout')
        )

        self.assertRedirects(
            response,
            reverse('accounts:login')
        )

        self.assertNotIn(
            '_auth_user_id',
            self.client.session
        )
