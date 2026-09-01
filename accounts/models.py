from django.conf import settings
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """
    Extended profile info for the built-in User model.

    Everything here is optional so existing users continue to work.
    Created lazily via a post_save signal.
    """

    THEME_CHOICES = [
        ("dark", "Dark"),
        ("light", "Light"),
        ("system", "System"),
    ]

    CURRENCY_CHOICES = [
        ("INR", "₹ Indian Rupee"),
        ("USD", "$ US Dollar"),
        ("EUR", "€ Euro"),
        ("GBP", "£ British Pound"),
        ("AED", "د.إ UAE Dirham"),
        ("SGD", "S$ Singapore Dollar"),
    ]

    LANGUAGE_CHOICES = [
        ("en", "English"),
        ("hi", "हिन्दी"),
        ("mr", "मराठी"),
        ("ta", "தமிழ்"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
    )
    display_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    bio = models.TextField(blank=True, max_length=400)

    # Preferences
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default="dark")
    currency = models.CharField(max_length=8, choices=CURRENCY_CHOICES, default="INR")
    timezone = models.CharField(max_length=64, default="Asia/Kolkata")
    language = models.CharField(max_length=8, choices=LANGUAGE_CHOICES, default="en")

    # Notification preferences
    notify_spending_alerts = models.BooleanField(default=True)
    notify_budget_alerts = models.BooleanField(default=True)
    notify_ai_insights = models.BooleanField(default=True)
    notify_monthly_reports = models.BooleanField(default=False)
    notify_bank_sync = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile<{self.user.username}>"

    @property
    def full_name(self) -> str:
        u = self.user
        parts = [p for p in [u.first_name, u.last_name] if p]
        return " ".join(parts) or self.display_name or u.username


def _create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
