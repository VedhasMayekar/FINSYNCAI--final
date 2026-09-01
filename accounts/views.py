from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import SignupForm
from .models import UserProfile


def signup_view(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data["password"])
            user.save()
            login(request, user)
            return redirect("dashboard:index")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("dashboard:index")
        messages.error(request, "Invalid username or password.")
    return render(request, "accounts/login.html")


def logout_view(request):
    logout(request)
    return redirect("core:index")


# ==========================================================
# PROFILE
# ==========================================================

def _get_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


@login_required
def profile_view(request):
    profile = _get_profile(request.user)

    # Stats to render on the profile card.
    tx_count = 0
    joined_days = 0
    from datetime import date
    try:
        from transactions.models import Transaction
        tx_count = Transaction.objects.filter(user=request.user).count()
    except Exception:
        pass
    if request.user.date_joined:
        joined_days = (date.today() - request.user.date_joined.date()).days

    # Connected accounts (Google via allauth if any)
    connected_accounts = []
    try:
        from allauth.socialaccount.models import SocialAccount
        for sa in SocialAccount.objects.filter(user=request.user):
            connected_accounts.append({
                "provider": sa.provider.capitalize(),
                "uid": sa.uid,
                "date_joined": sa.date_joined,
            })
    except Exception:
        pass

    # Connected banks
    connected_banks = []
    try:
        from transactions.bankhub_client import BankHubClient  # noqa: F401
        # If your BankHub client exposes a list, integrate here. Left generic on purpose.
    except Exception:
        pass

    return render(request, "accounts/profile.html", {
        "active_page": "profile",
        "profile": profile,
        "tx_count": tx_count,
        "joined_days": joined_days,
        "connected_accounts": connected_accounts,
        "connected_banks": connected_banks,
    })


@login_required
@require_POST
def profile_update(request):
    profile = _get_profile(request.user)
    user = request.user

    user.first_name = request.POST.get("first_name", user.first_name).strip()
    user.last_name = request.POST.get("last_name", user.last_name).strip()
    new_email = request.POST.get("email", user.email).strip()
    if new_email and new_email != user.email:
        user.email = new_email
    user.save()

    profile.display_name = request.POST.get("display_name", profile.display_name).strip()
    profile.phone = request.POST.get("phone", profile.phone).strip()
    profile.bio = request.POST.get("bio", profile.bio).strip()

    if request.FILES.get("avatar"):
        profile.avatar = request.FILES["avatar"]

    profile.save()
    return JsonResponse({
        "success": True,
        "message": "Profile updated.",
        "avatar_url": profile.avatar.url if profile.avatar else "",
    })


# ==========================================================
# SETTINGS
# ==========================================================

@login_required
def settings_view(request):
    profile = _get_profile(request.user)

    connected_accounts = []
    try:
        from allauth.socialaccount.models import SocialAccount
        for sa in SocialAccount.objects.filter(user=request.user):
            connected_accounts.append({
                "provider": sa.provider.capitalize(),
                "uid": sa.uid,
            })
    except Exception:
        pass

    # Import history (last 20)
    imports = []
    try:
        from transactions.models import Transaction
        imports = (
            Transaction.objects
            .filter(user=request.user)
            .exclude(import_source="manual")
            .values("import_source")
            .distinct()
        )
    except Exception:
        pass

    return render(request, "accounts/settings.html", {
        "active_page": "settings",
        "profile": profile,
        "connected_accounts": connected_accounts,
        "imports": list(imports),
        "theme_choices": UserProfile.THEME_CHOICES,
        "currency_choices": UserProfile.CURRENCY_CHOICES,
        "language_choices": UserProfile.LANGUAGE_CHOICES,
    })


@login_required
@require_POST
def settings_update(request):
    """Generic settings updater. Accepts any subset of the profile fields."""
    profile = _get_profile(request.user)

    field_map = {
        "theme": str,
        "currency": str,
        "timezone": str,
        "language": str,
        "notify_spending_alerts": lambda v: v in ("1", "true", "on"),
        "notify_budget_alerts": lambda v: v in ("1", "true", "on"),
        "notify_ai_insights": lambda v: v in ("1", "true", "on"),
        "notify_monthly_reports": lambda v: v in ("1", "true", "on"),
        "notify_bank_sync": lambda v: v in ("1", "true", "on"),
    }

    updated = []
    for field, caster in field_map.items():
        if field in request.POST:
            setattr(profile, field, caster(request.POST[field]))
            updated.append(field)
    profile.save()

    return JsonResponse({
        "success": True,
        "updated": updated,
        "theme": profile.theme,
    })


@login_required
def data_export(request):
    """Export all of the user's data as JSON."""
    from django.http import HttpResponse
    import json

    payload = {
        "user": {
            "username": request.user.username,
            "email": request.user.email,
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "date_joined": request.user.date_joined.isoformat() if request.user.date_joined else None,
        },
        "transactions": [],
        "goals": [],
        "budgets": [],
        "holdings": [],
    }
    try:
        from transactions.models import Transaction
        for t in Transaction.objects.filter(user=request.user):
            payload["transactions"].append({
                "title": t.title,
                "merchant": t.merchant,
                "amount": float(t.amount),
                "type": t.transaction_type,
                "category": t.category.name if t.category else None,
                "date": t.transaction_date.isoformat(),
                "notes": t.notes,
            })
    except Exception:
        pass
    try:
        from goals.models import Goal
        for g in Goal.objects.filter(user=request.user):
            payload["goals"].append({
                "title": g.title,
                "target": float(g.target_amount),
                "current": float(g.current_amount),
                "deadline": g.deadline.isoformat(),
                "status": g.status,
            })
    except Exception:
        pass
    try:
        from budgets.models import Budget
        for b in Budget.objects.filter(user=request.user):
            payload["budgets"].append({
                "category": b.category.name if getattr(b, "category", None) else None,
                "amount": float(getattr(b, "amount", 0) or 0),
                "period": getattr(b, "period", ""),
            })
    except Exception:
        pass
    try:
        from investments.models import Holding
        for h in Holding.objects.filter(user=request.user):
            payload["holdings"].append({
                "symbol": h.symbol,
                "name": h.name,
                "quantity": float(h.quantity),
                "buy_price": float(h.buy_price),
                "current_price": float(h.current_price or 0),
                "asset_type": h.asset_type,
            })
    except Exception:
        pass

    body = json.dumps(payload, indent=2, default=str)
    resp = HttpResponse(body, content_type="application/json")
    resp["Content-Disposition"] = 'attachment; filename="finsync_export.json"'
    return resp
