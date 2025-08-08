from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import *
from .forms import *
from django.http import HttpResponse
from django.views.generic import TemplateView

from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect, render
from django.contrib import messages
from django.conf import settings
import boto3, os

from datetime import datetime


@login_required
def home(request):

    return render(request, 'home.html')


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created successfully. You can now log in.')
            return redirect('login')
    else:
        form = UserCreationForm()
    context = {'form': form, 'current_page': 'register'} 
    return render(request, 'registration/register.html', context)



@login_required
def profile(request):
    profile, created = PilotProfile.objects.get_or_create(user=request.user)

    # Handle form submissions
    if request.method == 'POST':
        if 'update_user' in request.POST:
            user_form = UserForm(request.POST, instance=request.user)
            form = PilotProfileForm(instance=profile)  # unchanged
            training_form = TrainingForm()  # unchanged

            if user_form.is_valid():
                user_form.save()
                messages.success(request, "User info updated.")
                return redirect('profile')

        elif 'update_profile' in request.POST:
            form = PilotProfileForm(request.POST, request.FILES, instance=profile)
            user_form = UserForm(instance=request.user)
            training_form = TrainingForm()

            if form.is_valid():
                form.save()
                messages.success(request, "Pilot credentials updated.")
                return redirect('profile')

        elif 'add_training' in request.POST:
            training_form = TrainingForm(request.POST, request.FILES)
            form = PilotProfileForm(instance=profile)
            user_form = UserForm(instance=request.user)

            if training_form.is_valid():
                training = training_form.save(commit=False)
                training.pilot = profile
                training.save()
                messages.success(request, "Training record added.")
                return redirect('profile')
    else:
        # Initial load
        form = PilotProfileForm(instance=profile)
        user_form = UserForm(instance=request.user)
        training_form = TrainingForm()

    # Filtering training list
    year_filter = request.GET.get('year')
    trainings = profile.trainings.all()
    if year_filter:
        trainings = trainings.filter(date_completed__year=year_filter)

    training_years = profile.trainings.dates('date_completed', 'year', order='DESC')

    context = {
        'profile': profile,
        'form': form,
        'user_form': user_form,
        'training_form': training_form,
        'trainings': trainings,
        'years': [y.year for y in training_years],
        'current_page': 'profile',
        'highest_altitude_flight': FlightLog.objects.order_by('-max_altitude_ft').first(),
        'fastest_speed_flight': FlightLog.objects.order_by('-max_speed_mph').first(),
        'longest_flight': FlightLog.objects.order_by('-max_distance_ft').first(),
    }
    return render(request, 'app/profile.html', context)


@login_required
def edit_profile(request):
    profile = get_object_or_404(PilotProfile, user=request.user)
    if request.method == 'POST':
        form = PilotProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('profile')
    else:
        form = PilotProfileForm(instance=profile)
    context = {'form': form, 'current_page': 'profile'} 
    return render(request, 'app/edit_profile.html', context)



@login_required
def delete_pilot_profile(request):
    profile = get_object_or_404(PilotProfile, user=request.user)
    if request.method == 'POST':
        user = profile.user
        profile.delete()
        user.delete()
        messages.success(request, "Your profile and account have been deleted.")
        return redirect('login')
    context = {'profile': profile, 'current_page': 'profile'}  # Breadcrumb for profile
    return render(request, 'app/pilot_profile_delete.html', context)


@login_required
def training_create(request):
    profile = get_object_or_404(PilotProfile, user=request.user)
    if request.method == 'POST':
        form = TrainingForm(request.POST, request.FILES)
        if form.is_valid():
            training = form.save(commit=False)
            training.pilot = profile
            training.save()
            return redirect('profile')
    else:
        form = TrainingForm()
    context = {'form': form, 'current_page': 'profile'}  # Breadcrumb for profile
    return render(request, 'app/training_form.html', context)



@login_required
def training_edit(request, pk):
    training = get_object_or_404(Training, pk=pk, pilot__user=request.user)
    form = TrainingForm(request.POST or None, request.FILES or None, instance=training)
    if form.is_valid():
        form.save()
        return redirect('profile')
    context = {'form': form, 'current_page': 'profile'}  # Breadcrumb for profile
    return render(request, 'app/training_form.html', context)



@login_required
def training_delete(request, pk):
    training = get_object_or_404(Training, pk=pk, pilot__user=request.user)
    if request.method == 'POST':
        training.delete()
        return redirect('profile')
    context = {'training': training, 'current_page': 'profile'}  # Breadcrumb for profile
    return render(request, 'app/training_confirm_delete.html', context)


# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=- Help

def help_getting_started(request):
    return render(request, 'help/help_getting_started.html')


def help_home(request):
    return render(request, 'help/help_home.html')


def help_pilot_profile(request):
    return render(request, 'help/help_pilot_profile.html')


def help_equipment(request):
    return render(request, 'help/help_equipment.html')


def help_flight_logs(request):
    return render(request, 'help/help_flight_logs.html')


def help_documents(request):
    return render(request, 'help/help_documents.html')
