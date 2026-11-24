
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from .forms import RegisterForm, LoginForm, ProfileUpdateForm


def register_view(request):
    """Register a new ordinary ChamaFlow user."""

    if request.user.is_authenticated:
        return redirect("savings:dashboard")

    if request.method == "POST":
        form = RegisterForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)

            # Every newly registered account starts as an ordinary user.
            user.is_staff = False
            user.is_superuser = False
            user.is_active = True

            user.save()

            messages.success(
                request,
                "Your account has been created successfully. "
                "You can now log in to ChamaFlow.",
            )

            return redirect("accounts:login")

    else:
        form = RegisterForm()

    return render(
        request,
        "register.html",
        {"form": form},
    )



def login_view(request):
    """Authenticate an existing ChamaFlow user."""

    if request.user.is_authenticated:
        return redirect("savings:dashboard")

    if request.method == "POST":
        form = LoginForm(request, request.POST)

        if form.is_valid():
            user = form.get_user()

            if user is not None and user.is_active:
                login(request, user)

                # Remember Me functionality
                if request.POST.get("remember_me"):
                    request.session.set_expiry(1209600)  # 14 days
                else:
                    request.session.set_expiry(0)  # Browser session

                messages.success(
                    request,
                    f"Welcome back, {user.first_name or user.username}!",
                )

                return redirect("savings:dashboard")

            messages.error(
                request,
                "Your account is inactive. Please contact the administrator.",
            )

    else:
        form = LoginForm()

    return render(
        request,
        "login.html",
        {"form": form},
    )


@login_required
@require_POST
def logout_view(request):
    """Log out the currently authenticated user."""

    logout(request)

    messages.success(
        request,
        "You have been logged out successfully.",
    )

    return redirect("accounts:login")


@login_required
def profile_view(request):
    """Display the authenticated user's profile."""

    return render(
        request,
        "profile.html",
        {"user": request.user},
    )


@login_required
def edit_profile_view(request):
    """Allow users to update their own profile."""

    if request.method == "POST":
        form = ProfileUpdateForm(
            request.POST,
            request.FILES,
            instance=request.user,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Your profile has been updated successfully.",
            )

            return redirect("accounts:profile")

    else:
        form = ProfileUpdateForm(instance=request.user)

    return render(
        request,
        "edit_profile.html",
        {"form": form},
    )
