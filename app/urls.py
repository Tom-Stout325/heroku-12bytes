from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from django.contrib.auth.decorators import login_required
from .views import *
from flightplan import views as drone_views


urlpatterns = [
    path('', login_required(TemplateView.as_view(template_name='app/home.html')), name='home'),
    path('drone-portal/', drone_views.drone_portal, name='drone_portal'),
    path('profile/', profile, name='profile'),
    path('profile/edit/', edit_profile, name='edit_profile'),
    path('training/add/', training_create, name='training_create'),
    path('training/<int:pk>/edit/', training_edit, name='training_edit'),
    path('training/<int:pk>/delete/', training_delete, name='training_delete'),

    path('register/', register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('password_reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),
    
    path('help/', help_home, name='help_home'),
    path('help/pilot-profile/', help_pilot_profile, name='help_pilot_profile'),
    path('help/equipment/', help_equipment, name='help_equipment'),
    path('help/flight-logs/', help_flight_logs, name='help_flight_logs'),
    path('help/documents/', help_documents, name='help_documents'),
    path('help/getting-started/', help_getting_started, name='help_getting_started'),


]
