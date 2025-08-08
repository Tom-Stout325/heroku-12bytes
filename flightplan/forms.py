from django import forms
from .models import DroneIncidentReport
from .models import *


#<---------------------------------------- INCIDENT REPORT FORM ---------------------------------------->

class GeneralInfoForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['report_date', 'reported_by', 'contact', 'role']
        widgets = {
            'report_date': forms.DateInput(attrs={'type': 'date'}),
        }

class EventDetailsForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['event_date', 'event_time', 'location', 'event_type', 'description',
                  'injuries', 'injury_details', 'damage', 'damage_cost', 'damage_desc']
        widgets = {
            'event_date': forms.DateInput(attrs={'type': 'date'}),
            'event_time': forms.TimeInput(attrs={'type': 'time'}),
        }

class EquipmentDetailsForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['drone_model', 'registration', 'controller', 'payload', 'battery', ]

class EnvironmentalConditionsForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['weather', 'wind', 'temperature', 'lighting']

class WitnessForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['witnesses', 'witness_details']

class ActionTakenForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['emergency', 'agency_response', 'scene_action', 'faa_report', 'faa_ref']

class FollowUpForm(forms.ModelForm):
    class Meta:
        model = DroneIncidentReport
        fields = ['cause', 'notes', 'signature', 'sign_date']
        widgets = {
            'sign_date': forms.DateInput(attrs={'type': 'date'}),
        }



#<---------------------------------------- GENERAL DOCs/SOP FORMS / SOPs ---------------------------------------->

class SOPDocumentForm(forms.ModelForm):
    class Meta:
        model = SOPDocument
        fields = ['title', 'description', 'file']


class GeneralDocumentForm(forms.ModelForm):
    class Meta:
        model = GeneralDocument
        fields = ['title', 'category', 'description', 'file']




#<---------------------------------------- FLIGHT LOG FORMS ---------------------------------------->


class FlightLogCSVUploadForm(forms.Form):
    csv_file = forms.FileField(label="Upload Flight Log CSV", widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))



#<---------------------------------------- EQUIPMENT FORMS ---------------------------------------->




class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = [  # Explicitly list fields
            'name', 'equipment_type', 'brand', 'model', 'serial_number',
            'faa_number', 'faa_certificate', 'purchase_date', 'purchase_cost',
            'receipt', 'date_sold', 'sale_price', 'deducted_full_cost',
            'notes', 'active'
        ]
        widgets = {
            'purchase_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_sold': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'brand': forms.TextInput(attrs={'class': 'form-control'}),
            'model': forms.TextInput(attrs={'class': 'form-control'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control'}),
            'faa_number': forms.TextInput(attrs={'class': 'form-control'}),
            'purchase_cost': forms.NumberInput(attrs={'class': 'form-control'}),
            'sale_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'equipment_type': forms.Select(attrs={'class': 'form-control'}),
            'deducted_full_cost': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


    def clean_faa_certificate(self):
        file = self.cleaned_data.get('faa_certificate')
        if file and hasattr(file, 'content_type'):
            allowed_types = ['application/pdf', 'image/jpeg', 'image/png']
            if file.content_type not in allowed_types:
                raise ValidationError("Only PDF, JPG, or PNG files are allowed.")
        return file

    def clean_receipt(self):
        file = self.cleaned_data.get('receipt')
        if file and hasattr(file, 'content_type'):
            allowed_types = ['application/pdf', 'image/jpeg', 'image/png']
            if file.content_type not in allowed_types:
                raise ValidationError("Only PDF, JPG, or PNG files are allowed.")
        return file



      


#<---------------------------------------- DRONE FORMS ---------------------------------------->

