from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    # Profile
    path("profile/", views.profile_view, name="profile"),
    path("profile/update/", views.profile_update, name="profile_update"),
    # Settings
    path("settings/", views.settings_view, name="settings"),
    path("settings/update/", views.settings_update, name="settings_update"),
    path("settings/export/", views.data_export, name="data_export"),
]
