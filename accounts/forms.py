
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm
from .models import User


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your first name'
        })
    )

    last_name = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your last name'
        })
    )

    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Choose a username'
        })
    )

    phone_number = forms.CharField(
        max_length=15,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 0712345678'
        })
    )

    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address (optional)'
        })
    )

    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a password'
        })
    )

    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password'
        })
    )

    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'username',
            'phone_number',
            'email',
            'password1',
            'password2'
        ]

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number'].strip()

        if not phone.isdigit():
            raise forms.ValidationError(
                'Phone number must contain digits only.'
            )

        if len(phone) not in (10, 12):
            raise forms.ValidationError(
                'Enter a valid Kenyan phone number.'
            )

        if len(phone) == 10 and not phone.startswith('0'):
            raise forms.ValidationError(
                'Enter a valid Kenyan phone number.'
            )

        if len(phone) == 12 and not phone.startswith('254'):
            raise forms.ValidationError(
                'Use the format 254712345678.'
            )

        return phone


class LoginForm(forms.Form):
    username = forms.CharField(
        label='Username or Phone Number',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter username or phone number'
        })
    )

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your password'
        })
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()

        identifier = cleaned_data.get('username')
        password = cleaned_data.get('password')

        if identifier and password:
            user = User.objects.filter(
                phone_number=identifier
            ).first()

            username = user.username if user else identifier

            self.user = authenticate(
                request=self.request,
                username=username,
                password=password
            )

            if self.user is None:
                raise forms.ValidationError(
                    'Invalid username/phone number or password.'
                )

            if not self.user.is_active:
                raise forms.ValidationError(
                    'This account is inactive.'
                )

        return cleaned_data

    def get_user(self):
        return getattr(self, 'user', None)


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'username',
            'phone_number',
            'email',
            'profile_picture'
        ]

        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'username': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control'
            }),
            'profile_picture': forms.ClearableFileInput(attrs={
                'class': 'form-control'
            }),
        }

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number'].strip()

        if not phone.isdigit():
            raise forms.ValidationError(
                'Phone number must contain digits only.'
            )

        if len(phone) not in (10, 12):
            raise forms.ValidationError(
                'Enter a valid Kenyan phone number.'
            )

        if len(phone) == 10 and not phone.startswith('0'):
            raise forms.ValidationError(
                'Enter a valid Kenyan phone number.'
            )

        if len(phone) == 12 and not phone.startswith('254'):
            raise forms.ValidationError(
                'Use the format 254712345678.'
            )

        return phone
