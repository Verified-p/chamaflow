
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import SavingsGroup, GroupMembership, Contribution


User = get_user_model()


def validate_phone_number(value):
    """Validate Kenyan mobile phone numbers."""
    value = value.strip()

    if not (
        (len(value) == 10 and value.startswith(("07", "01")))
        or (len(value) == 12 and value.startswith("254"))
    ):
        raise ValidationError(
            "Enter a valid Kenyan phone number, e.g. 0712345678 or 254712345678."
        )

    return value


class SavingsGroupForm(forms.ModelForm):
    """Form for creating and updating savings groups."""

    class Meta:
        model = SavingsGroup
        fields = [
            "name",
            "description",
            "contribution_amount",
            "contribution_frequency",
            "start_date",
            "end_date",
        ]

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter group name",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Describe your savings group",
            }),
            "contribution_amount": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1",
                "step": "0.01",
            }),
            "contribution_frequency": forms.Select(attrs={
                "class": "form-select",
            }),
            "start_date": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
            "end_date": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
        }

    def clean_contribution_amount(self):
        amount = self.cleaned_data["contribution_amount"]

        if amount <= 0:
            raise ValidationError("Contribution amount must be greater than zero.")

        return amount

    def clean(self):
        cleaned_data = super().clean()

        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and end_date <= start_date:
            self.add_error(
                "end_date",
                "The end date must be later than the start date."
            )

        return cleaned_data


class AddMemberForm(forms.Form):
    """Form for adding an existing user to a savings group."""

    user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
        empty_label="Select a member",
    )

    def __init__(self, *args, group=None, **kwargs):
        self.group = group
        super().__init__(*args, **kwargs)

    def clean_user(self):
        user = self.cleaned_data["user"]

        if self.group and GroupMembership.objects.filter(
            group=self.group,
            user=user,
        ).exists():
            raise ValidationError(
                "This user already has a membership record in this group."
            )

        return user

    def save(self):
        if not self.group:
            raise ValueError("A savings group must be provided.")

        return GroupMembership.objects.create(
            group=self.group,
            user=self.cleaned_data["user"],
            role="member",
            status="active",
        )


class ContributionForm(forms.ModelForm):
    """Form for preparing a member's contribution payment."""

    class Meta:
        model = Contribution
        fields = [
            "membership",
            "due_date",
            "phone_number",
        ]

        widgets = {
            "membership": forms.Select(attrs={
                "class": "form-select",
            }),
            "due_date": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
            "phone_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "0712345678",
            }),
        }

    def __init__(self, *args, group=None, **kwargs):
        self.group = group
        super().__init__(*args, **kwargs)

        if group:
            self.fields["membership"].queryset = (
                GroupMembership.objects.filter(
                    group=group,
                    status="active",
                ).select_related("user")
            )
        else:
            self.fields["membership"].queryset = (
                GroupMembership.objects.none()
            )

    def clean_phone_number(self):
        return validate_phone_number(
            self.cleaned_data["phone_number"]
        )

    def clean(self):
        cleaned_data = super().clean()

        membership = cleaned_data.get("membership")
        due_date = cleaned_data.get("due_date")

        if membership and self.group:
            if membership.group_id != self.group.id:
                self.add_error(
                    "membership",
                    "The selected member does not belong to this group."
                )

            if membership.status != "active":
                self.add_error(
                    "membership",
                    "Only active members can make contributions."
                )

            if due_date and Contribution.objects.filter(
                membership=membership,
                due_date=due_date,
            ).exists():
                self.add_error(
                    "due_date",
                    "A contribution record already exists for this member on this date."
                )

        return cleaned_data

    def save(self, commit=True):
        contribution = super().save(commit=False)

        if not self.group:
            raise ValueError("A savings group must be provided.")

        contribution.group = self.group
        contribution.amount = self.group.contribution_amount
        contribution.status = "pending"

        if commit:
            contribution.save()

        return contribution
