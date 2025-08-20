from django import forms
from django.forms import inlineformset_factory
from .models import *
from datetime import date
from datetime import datetime
from django.core.exceptions import ValidationError
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Row, Column
from django.core.exceptions import FieldError


class TransForm(forms.ModelForm):
    invoice_number = forms.CharField(
        label="Invoice Number (Optional)",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    event = forms.ModelChoiceField(
        queryset=Event.objects.order_by('title'),
        label='Event',
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False
    )

    sub_cat = forms.ModelChoiceField(
        queryset=SubCategory.objects.all().order_by('category__category', 'sub_cat'),
        label='Sub-Category',
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=False
    )

    class Meta:
        model = Transaction
        fields = (
            'invoice_number', 'date', 'trans_type', 'sub_cat', 'amount',
            'team', 'transaction', 'receipt', 'transport_type', 'event'
        )
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'transport_type': forms.Select(attrs={'class': 'form-control'}),
        }

    def clean_receipt(self):
        receipt = self.cleaned_data.get('receipt')
        if receipt and hasattr(receipt, 'content_type'):
            if receipt.content_type not in ['application/pdf', 'image/jpeg', 'image/png']:
                raise ValidationError("Only PDF, JPG, or PNG files are allowed.")
        return receipt

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('sub_cat'):
            cleaned_data['category'] = cleaned_data['sub_cat'].category
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.sub_cat:
            instance.category = instance.sub_cat.category
        if commit:
            instance.save()
        return instance



class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        exclude = ['amount']
        widgets = {
            'invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'client': forms.Select(attrs={'class': 'form-select'}),
            'event': forms.Select(attrs={'class': 'form-select'}),
            'service': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'paid_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }




class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ['description', 'qty', 'price']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'qty': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def clean_qty(self):
        qty = self.cleaned_data.get('qty')
        if qty is not None and qty <= 0:
            raise forms.ValidationError("Quantity must be greater than 0.")
        return qty

    def clean_price(self):
        price = self.cleaned_data.get('price')
        if price is not None and price < 0:
            raise forms.ValidationError("Price cannot be negative.")
        return price



InvoiceItemFormSet = inlineformset_factory(
    parent_model=Invoice,
    model=InvoiceItem,
    form=InvoiceItemForm,
    extra=2,  # Show 2 blank forms by default
    can_delete=True
)



class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['category'] 
        widgets = {
            'category': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter category name'
            }),
        }


class SubCategoryForm(forms.ModelForm):
    class Meta:
        model = SubCategory
        fields = ['sub_cat', 'category'] 
        widgets = {
            'sub_cat': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter sub-category name'
            }),
            'category': forms.Select(attrs={
                'class': 'form-control'
            }),
        }



class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['business', 'first', 'last', 'street', 'address2', 'email', 'phone']







class MileageForm(forms.ModelForm):
    class Meta:
        model = Miles
        exclude = ['user', 'total']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'begin': forms.NumberInput(attrs={'step': '0.1', 'class': 'form-control'}),
            'end': forms.NumberInput(attrs={'step': '0.1', 'class': 'form-control'}),
            'client': forms.Select(attrs={'class': 'form-control'}),
            'event': forms.Select(attrs={'class': 'form-control'}),  # dropdown of Events
            'invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'tax': forms.TextInput(attrs={'class': 'form-control'}),
            'vehicle': forms.TextInput(attrs={'class': 'form-control'}),
            'mileage_type': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['event'].required = False
        self.fields['event'].empty_label = '— No event —'

        try:
            self.fields['event'].queryset = Event.objects.order_by('-event_year', 'title')
        except FieldError:
            self.fields['event'].queryset = Event.objects.order_by('-id', 'title')



class MileageRateForm(forms.ModelForm):
    class Meta:
        model = MileageRate
        fields = ['rate']
        widgets = {
            'rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }



class RecurringTransactionForm(forms.ModelForm):
    class Meta:
        model = RecurringTransaction
        fields = [
            'user', 'trans_type', 'category', 'sub_cat', 'amount', 'transaction', 'day',
            'team', 'tax', 'receipt', 'active'
        ]
        widgets = {
            'day': forms.NumberInput(attrs={'min': 1, 'max': 28}),
        }



class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            'title',
            'event_type',
            'location_city',
            'location_address',
            'airspace',
            'waiver_approved',
            'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
            'waiver_approved': forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.label_class = 'fw-semibold'
        self.helper.layout = Layout(
            Row(
                Column('title', css_class='col-md-6'),
                Column('event_type', css_class='col-md-6'),
            ),
            Row(
                Column('location_city', css_class='col-md-6'),
                Column('airspace', css_class='col-md-6'),
            ),
            Row(
                Column('location_address', css_class='col-md-6'),
                Column('waiver_approved', css_class='col-md-6'),
            ),
            Row(
            'notes',
            ),
            Submit('submit', 'Save Event', css_class='btn btn-primary float-end')
        )