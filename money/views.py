from django.views.generic import TemplateView, ListView, DetailView, UpdateView, DeleteView, CreateView
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.db.models import Sum, F, Value, DecimalField, ExpressionWrapper, Case, When
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from django.db.models.functions import ExtractYear
from django.views.generic.edit import UpdateView
from django.template.loader import get_template
from django.urls import reverse_lazy, reverse
from django.conf.urls.static import static
from django.utils.encoding import smart_str
from calendar import monthrange, month_name
from django.core.paginator import Paginator
from django.core.mail import EmailMessage
from django.utils.timezone import now
from django.db.models import Prefetch
from django.contrib import messages
from collections import defaultdict
from datetime import datetime, date
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from weasyprint import HTML, CSS
from decimal import Decimal
from pathlib import Path
import tempfile
import logging
import csv
import os

from flightplan.models import Equipment
from .models import *
from .forms import *


logger = logging.getLogger(__name__)




class Dashboard(LoginRequiredMixin, TemplateView):
    template_name = "money/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'dashboard'
        return context
    
    

# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->         T R A N S A C T I O N S 


ALLOWED_SORT_FIELDS = (
    "date",
    "trans_type",
    "transaction",
    "amount",
    "invoice_number",
    "event",
)


SORT_MAP = {
    "date": "date",
    "trans_type": "trans_type",
    "transaction": "transaction",
    "amount": "amount",
    "invoice_number": "invoice_number",
    "event": "event__title",
}


def _sanitize_sort(raw_sort: str) -> str:
    """Only allow ALLOWED_SORT_FIELDS (with optional '-'); fallback to '-date'."""
    if not raw_sort:
        return "-date"
    key = raw_sort.lstrip('-')
    return raw_sort if key in ALLOWED_SORT_FIELDS else "-date"


def _build_sort_state(current_sort: str, keys=None, default_key="-date"):
    """
    Backward-compatible:
      - If 'keys' is provided, build state for those keys (useful for tri-state toggling).
      - If 'keys' is None, use ALLOWED_SORT_FIELDS (Transactions template case).

    For each key, returns:
      {"is_asc": bool, "is_desc": bool, "next": <next sort token>}
    Next rule:
      - asc  -> desc  (e.g., 'date' -> '-date')
      - desc -> default_key if provided else key (tri-state support)
      - none -> asc
    """
    keys = list(keys) if keys else list(ALLOWED_SORT_FIELDS)
    state = {}
    for k in keys:
        is_asc = (current_sort == k)
        is_desc = (current_sort == f"-{k}")
        if is_asc:
            nxt = f"-{k}"
        elif is_desc:
            nxt = default_key if default_key else k
        else:
            nxt = k
        state[k] = {"is_asc": is_asc, "is_desc": is_desc, "next": nxt}
    return state


def _apply_ordering(qs, sort_param: str):
    sort = _sanitize_sort(sort_param)
    key = sort.lstrip('-')
    field = SORT_MAP.get(key, "date")
    if sort.startswith('-'):
        field = f"-{field}"
    return qs.order_by(field), sort


def _filtered_transactions(request):
    """
    Base filtered queryset for the current user, before ordering/pagination.
    """
    qs = (
        Transaction.objects
        .select_related('sub_cat__category', 'sub_cat', 'team', 'event')
        .filter(user=request.user)
    )

    event_id = request.GET.get('event')
    if event_id and Event.objects.filter(id=event_id).exists():
        qs = qs.filter(event__id=event_id)

    category_id = request.GET.get('category')
    if category_id and Category.objects.filter(id=category_id).exists():
        qs = qs.filter(sub_cat__category__id=category_id)

    sub_cat_id = request.GET.get('sub_cat')
    if sub_cat_id and SubCategory.objects.filter(id=sub_cat_id).exists():
        qs = qs.filter(sub_cat__id=sub_cat_id)

    year = request.GET.get('year')
    if year and year.isdigit() and 1900 <= int(year) <= 9999:
        qs = qs.filter(date__year=year)

    return qs



class Transactions(LoginRequiredMixin, ListView):
    model = Transaction
    template_name = "money/transactions.html"
    context_object_name = "transactions"
    paginate_by = 50

    def get_queryset(self):
        qs = _filtered_transactions(self.request)
        raw_sort = self.request.GET.get('sort', '-date')
        qs, self.current_sort = _apply_ordering(qs, raw_sort)
        return qs

    def get_context_data(self, **kwargs):
        from django.db.models import Q  
        ctx = super().get_context_data(**kwargs)

        ctx['events'] = (
            Event.objects.filter(transactions__user=self.request.user) 
            .distinct()
            .order_by('slug')
        )
        ctx['categories'] = (
            Category.objects.filter(subcategories__transaction__user=self.request.user)  
            .distinct()
            .order_by('category')
        )
        ctx['subcategories'] = (
            SubCategory.objects.filter(transaction__user=self.request.user) 
            .distinct()
            .order_by('sub_cat')
        )
        ctx['years'] = [
            str(y) for y in (
                Transaction.objects.filter(user=self.request.user)
                .annotate(year=ExtractYear('date'))
                .values_list('year', flat=True)
                .distinct()
                .order_by('-year')
            )
        ]

        ctx.update({
            'selected_event': self.request.GET.get('event', ''),
            'selected_category': self.request.GET.get('category', ''),
            'selected_sub_cat': self.request.GET.get('sub_cat', ''),
            'selected_year': self.request.GET.get('year', ''),
            'current_page': 'transactions',
            'current_sort': self.current_sort,
            'sort_state': _build_sort_state(self.current_sort),
        })
        return ctx


@login_required
def export_transactions_csv(request):
    qs = _filtered_transactions(request)
    raw_sort = request.GET.get('sort', '-date')
    qs, _ = _apply_ordering(qs, raw_sort)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename=transactions.csv'
    writer = csv.writer(response)

    writer.writerow([
        "Date",
        "Type",
        "Invoice #",
        "Event",
        "Description",
        "Amount",
    ])

    for t in qs:
        writer.writerow([
            smart_str(t.date.isoformat() if t.date else ""),
            smart_str(t.trans_type or ""),
            smart_str(t.invoice_number or ""),
            smart_str(t.event.title if getattr(t, "event", None) else ""),
            smart_str(t.transaction or ""),
            f"{(t.amount or Decimal('0')):.2f}",
        ])

    return response


class TransactionDetailView(LoginRequiredMixin, DetailView):
    model = Transaction
    template_name = 'money/transactions_detail_view.html'
    context_object_name = 'transaction'

    def get_queryset(self):
        return (
            Transaction.objects
            .select_related('sub_cat', 'sub_cat__category', 'team', 'event')
            .filter(user=self.request.user)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        t = context['transaction']

        matched_invoice = None
        if t.invoice_number:
            if t.event_id:
                matched_invoice = Invoice.objects.filter(
                    invoice_number=t.invoice_number,
                    event=t.event
                ).first()
            if not matched_invoice:
                matched_invoice = Invoice.objects.filter(
                    invoice_number=t.invoice_number
                ).first()

        context['matched_invoice'] = matched_invoice
        context['current_page'] = 'transactions'
        return context


class TransactionCreateView(LoginRequiredMixin, CreateView):
    model = Transaction
    form_class = TransForm
    template_name = 'money/transaction_add.html'
    success_url = reverse_lazy('add_transaction_success')

    def form_valid(self, form):
        form.instance.user = self.request.user

        sub_cat = form.cleaned_data.get('sub_cat')
        if sub_cat:
            form.instance.category = sub_cat.category

        try:
            with transaction.atomic():
                response = super().form_valid(form)
                messages.success(self.request, 'Transaction added successfully!')
                return response
        except Exception as e:
            logger.error(f"Error adding transaction for user {self.request.user.id}: {e}")
            messages.error(self.request, 'Error adding transaction. Please check the form.')
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'transactions'
        return context



class TransactionUpdateView(LoginRequiredMixin, UpdateView):
    model = Transaction
    form_class = TransForm
    template_name = 'money/transaction_edit.html'
    success_url = reverse_lazy('transactions')

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if form.is_bound:
            logger.info("Form is bound with data: %s", request.POST)
        else:
            logger.warning("Form is NOT bound!")
        if form.is_valid():
            logger.info("Form is valid, proceeding to save.")
            return self.form_valid(form)
        else:
            logger.warning("Form is invalid with errors: %s", form.errors)
            return self.form_invalid(form)

    def form_valid(self, form):
        try:
            with transaction.atomic():
                response = super().form_valid(form)
                messages.success(self.request, 'Transaction updated successfully!')
                return response
        except Exception as e:
            logger.error(f"Error updating transaction {self.get_object().id} for user {self.request.user.id}: {e}")
            messages.error(self.request, 'Error updating transaction. Please check the form.')
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'transactions'
        sub_cat = self.object.sub_cat
        if sub_cat:
            context['selected_category'] = sub_cat.category
        return context
    
    
class TransactionDeleteView(LoginRequiredMixin, DeleteView):
    model = Transaction
    template_name = "money/transaction_confirm_delete.html"
    success_url = reverse_lazy('transactions')

    def get_queryset(self):
        return Transaction.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                response = super().delete(request, *args, **kwargs)
                messages.success(self.request, "Transaction deleted successfully!")
                return response
        except models.ProtectedError:
            messages.error(self.request, "Cannot delete transaction due to related records.")
            return redirect('transactions')
        except Exception as e:
            logger.error(f"Error deleting transaction for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting transaction.")
            return redirect('transactions')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'transactions'
        return context


@login_required
def add_transaction_success(request):
    context = {'current_page': 'transactions'}
    return render(request, 'money/transaction_add_success.html', context)


# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->          I N V O I C E S


class InvoiceCreateView(LoginRequiredMixin, CreateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'money/invoice_add.html'
    success_url = reverse_lazy('invoice_list')

    def get_formset(self, data=None):
        return InvoiceItemFormSet(data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == 'POST':
            context['formset'] = self.get_formset(self.request.POST)
        else:
            context['formset'] = self.get_formset()
        context['current_page'] = 'invoices'
        return context
    
    def update_amount(self):
        self.amount = sum(item.total for item in self.items.all())
        self.save()

    def form_valid(self, form):
        formset = self.get_formset(self.request.POST)

        if not formset.is_valid():
            messages.error(self.request, "There were errors with the invoice items.")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        try:
            with transaction.atomic():
                invoice = form.save(commit=False)
                invoice.amount = 0  # will be recalculated
                invoice.save()

                for item_form in formset:
                    if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE', False):
                        item = item_form.save(commit=False)
                        item.invoice = invoice
                        item.save()

                invoice.update_amount()

                messages.success(self.request, f"Invoice created successfully.")
                return redirect(self.success_url)

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            messages.error(self.request, f"Error saving invoice: {e}")
            return self.form_invalid(form)




class InvoiceUpdateView(LoginRequiredMixin, UpdateView):
    model = Invoice
    form_class = InvoiceForm
    template_name = 'money/invoice_update.html'
    success_url = reverse_lazy('invoice_list')

    def get_formset(self, data=None):
        return InvoiceItemFormSet(data, instance=self.object)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['formset'] = self.get_formset(self.request.POST if self.request.method == 'POST' else None)
        context['invoice'] = self.object
        context['current_page'] = 'invoices'
        return context

    def form_valid(self, form):
        formset = self.get_formset(self.request.POST)

        if not formset.is_valid():
            messages.error(self.request, "There were errors in the invoice items.")
            return self.render_to_response(self.get_context_data(form=form, formset=formset))

        try:
            with transaction.atomic():
                invoice = form.save()
                formset.save()
                invoice.update_amount()
                messages.success(self.request, f"Invoice updated successfully.")
                return redirect(self.success_url)

        except Exception as e:
            import traceback
            print(traceback.format_exc())
            messages.error(self.request, "Error updating invoice. Please check the form.")
            return self.form_invalid(form)



class InvoiceListView(LoginRequiredMixin, ListView):
    model = Invoice
    template_name = "money/invoice_list.html"
    context_object_name = "invoices"
    paginate_by = 20

    def get_ordering(self):
        sort = self.request.GET.get('sort', 'invoice_number')
        direction = self.request.GET.get('direction', 'desc')

        valid_sort_fields = [
            'invoice_number',  
            'client__business',
            'event__title',
            'service__service',
            'amount',
            'date',
            'due',
            'paid_date',
        ]

        if sort not in valid_sort_fields:
            sort = 'invoice_number'

        return f"-{sort}" if direction == 'desc' else sort

    def get_queryset(self):
        ordering = self.get_ordering()

        queryset = Invoice.objects.select_related(
            'client', 'event', 'service'
        ).prefetch_related('items').order_by(ordering)

        search_query = self.request.GET.get('search', '')
        if search_query:
            search_query = search_query[:100]
            if hasattr(Invoice, 'search_vector'):
                queryset = queryset.filter(search_vector=search_query)
            else:
                queryset = queryset.filter(transaction__icontains=search_query)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'search_query': self.request.GET.get('search', ''),
            'current_sort': self.request.GET.get('sort', 'invoice_number'), 
            'current_direction': self.request.GET.get('direction', 'desc'),
            'current_page': 'invoices',
        })
        return context



class InvoiceDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'money/invoice_detail.html'
    context_object_name = 'invoice'

    def get_queryset(self):
        return Invoice.objects.select_related(
            'client', 'event', 'service'
        ).prefetch_related('items')

    @cached_property
    def logo_path(self):
        """Resolve the logo file path if available."""
        dirs = getattr(settings, 'STATICFILES_DIRS', [])
        for directory in dirs:
            potential_path = os.path.join(directory, 'images/logo2.png')
            if os.path.exists(potential_path):
                return f'file://{potential_path}'
        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'logo_path': self.logo_path,
            'rendering_for_pdf': self.request.GET.get('pdf', '').lower() in ['1', 'true'],
            'current_page': 'invoices',
        })
        return context




class InvoiceDeleteView(LoginRequiredMixin, DeleteView):
    model = Invoice
    template_name = "money/invoice_confirm_delete.html"
    success_url = reverse_lazy('invoice_list')

    def delete(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                response = super().delete(request, *args, **kwargs)
                messages.success(self.request, "Invoice deleted successfully.")
                return response
        except models.ProtectedError:
            messages.error(self.request, "Cannot delete invoice due to related records.")
            return redirect('invoice_list')
        except Exception as e:
            logger.error(f"Error deleting invoice for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting invoice.")
            return redirect('invoice_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'invoices'
        return context
    



@login_required
def invoice_review(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    transactions = (
        Transaction.objects
        .filter(event=invoice.event, invoice_number=invoice.invoice_number)
        .select_related('sub_cat__category')
    )

    try:
        rate = MileageRate.objects.first().rate if MileageRate.objects.exists() else Decimal("0.70")
    except Exception as e:
        logger.error(f"Error fetching mileage rate: {e}")
        rate = Decimal("0.70")

    mileage_entries = (
        Miles.objects
        .filter(
            user=request.user,
            invoice_number=invoice.invoice_number,
            tax__iexact="Yes",
            mileage_type="Taxable",
        )
        .annotate( 
            value=ExpressionWrapper(
                F('total') * Value(rate),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        )
        .order_by('date')
    )

    total_mileage_miles = mileage_entries.aggregate(Sum('total'))['total__sum'] or Decimal("0.00")
    mileage_dollars = round(total_mileage_miles * rate, 2)

    total_income = Decimal("0.00")
    total_expenses = Decimal("0.00")
    deductible_expenses = Decimal("0.00")

    for t in transactions:
        if t.trans_type == 'Income':
            total_income += t.amount
        elif t.trans_type == 'Expense':
            total_expenses += t.amount
            if t.sub_cat and t.sub_cat.slug == 'meals':
                deductible_expenses += t.deductible_amount
            elif t.sub_cat and t.sub_cat.slug == 'fuel' and t.transport_type == "personal_vehicle":
                continue 
            else:
                deductible_expenses += t.amount

    has_income_transaction = total_income > 0
    total_cost = total_expenses + mileage_dollars
    net_income = total_income - total_expenses if has_income_transaction else None
    taxable_income = total_income - deductible_expenses - mileage_dollars if has_income_transaction else None

    context = {
        'invoice': invoice,
        'transactions': transactions,
        'mileage_entries': mileage_entries,
        'mileage_rate': rate,
        'mileage_dollars': mileage_dollars,
        'invoice_amount': invoice.amount,
        'total_expenses': total_expenses,
        'deductible_expenses': deductible_expenses,
        'total_income': total_income,
        'net_income': net_income,
        'taxable_income': taxable_income,
        'total_cost': total_cost,
        'has_income_transaction': has_income_transaction,
        'now': now(),
        'current_page': 'invoices',
    }
    return render(request, 'money/invoice_review.html', context)




@login_required
def invoice_review_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    transactions = Transaction.objects.filter(
        event=invoice.event,
        invoice_number=invoice.invoice_number
    ).select_related('sub_cat__category')

    mileage_entries = Miles.objects.filter(
        invoice=invoice,
        user=request.user,
        tax__iexact="Yes",
        mileage_type="Taxable"
    )

    try:
        rate = MileageRate.objects.first().rate if MileageRate.objects.exists() else Decimal("0.70")
    except Exception:
        rate = Decimal("0.70")

    total_mileage_miles = mileage_entries.aggregate(Sum('total'))['total__sum'] or Decimal("0.00")
    mileage_dollars = round(total_mileage_miles * rate, 2)

    total_expenses = Decimal("0.00")
    deductible_expenses = Decimal("0.00")
    total_income = Decimal("0.00")

    for t in transactions:
        if t.trans_type == 'Income':
            total_income += t.amount
        elif t.trans_type == 'Expense':
            total_expenses += t.amount

            if t.sub_cat and t.sub_cat.slug == 'meals':
                deductible_expenses += t.deductible_amount
            elif t.sub_cat and t.sub_cat.slug == 'fuel' and t.transport_type == "personal_vehicle":
                continue  # Fuel not deductible
            else:
                deductible_expenses += t.amount

    net_income = total_income - total_expenses
    taxable_income = total_income - deductible_expenses - mileage_dollars
    total_cost = total_expenses + mileage_dollars
    has_income_transaction = total_income > 0

    context = {
        'invoice': invoice,
        'transactions': transactions,
        'mileage_entries': mileage_entries,
        'mileage_rate': rate,
        'mileage_dollars': mileage_dollars,
        'invoice_amount': invoice.amount,
        'total_expenses': total_expenses,
        'deductible_expenses': deductible_expenses,
        'total_income': total_income,
        'net_income': net_income,
        'taxable_income': taxable_income,
        'total_cost': total_cost,
        'has_income_transaction': has_income_transaction,
        'now': now(),
    }

    html_string = render_to_string('money/invoice_review_pdf.html', context)
    html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))

    pdf = html.write_pdf(stylesheets=[CSS(string='@page { size: A4; margin: 1in; }')])

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=invoice_{invoice.invoice_number}.pdf'
    return response



@login_required
def unpaid_invoices(request):
    invoices = Invoice.objects.filter(paid__iexact="No").select_related('client').order_by('due_date')
    context = {'invoices': invoices, 'current_page': 'invoices'}
    return render(request, 'money/unpaid_invoices.html', context)




@login_required
def export_invoices_csv(request):
    invoices = (
        Invoice.objects
        .select_related('client', 'event', 'service')
        .order_by('date')
    )

    year = request.GET.get('year')
    if year and year.isdigit():
        invoices = invoices.filter(date__year=year)

    if hasattr(Invoice, 'user'):
        invoices = invoices.filter(user=request.user)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="invoices.csv"'
    writer = csv.writer(response)

    writer.writerow([
        'Invoice #',
        'Client',
        'Event',
        'Location',
        'Service',
        'Amount',
        'Date',
        'Due Date',
        'Paid Date',
        'Status',
    ])

    for inv in invoices:
        writer.writerow([
            inv.invoice_number or '',                       
            str(inv.client) if getattr(inv, 'client', None) else '',
            str(inv.event) if getattr(inv, 'event', None) else '',
            getattr(inv, 'location', '') or '',
            str(inv.service) if getattr(inv, 'service', None) else '',
            f"{inv.amount:.2f}" if getattr(inv, 'amount', None) is not None else '',
            inv.date.strftime('%Y-%m-%d') if getattr(inv, 'date', None) else '',
            inv.due.strftime('%Y-%m-%d') if getattr(inv, 'due', None) else '',
            inv.paid_date.strftime('%Y-%m-%d') if getattr(inv, 'paid_date', None) else '',
            getattr(inv, 'status', '') or '',
        ])

    return response



# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->           C A T E G O R I E S 


class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = 'money/category_page.html'
    context_object_name = 'category'

    def get_queryset(self):
        return Category.objects.prefetch_related('subcategories').order_by('category')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context



class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "money/category_form.html"
    success_url = reverse_lazy('category_page')

    def form_valid(self, form):
        messages.success(self.request, "Category added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context




class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "money/category_form.html"
    success_url = reverse_lazy('category_page')

    def form_valid(self, form):
        messages.success(self.request, "Category updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context




class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    template_name = "money/category_confirm_delete.html"
    success_url = reverse_lazy('category_page')

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Category deleted successfully!")
            return response
        except models.ProtectedError:
            messages.error(self.request, "Cannot delete category due to related transactions.")
            return redirect('category_page')
        except Exception as e:
            logger.error(f"Error deleting category for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting category.")
            return redirect('category_page')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context




@login_required
def category_summary(request):
    year = request.GET.get('year')
    context = get_summary_data(request, year)
    context['available_years'] = [d.year for d in Transaction.objects.filter(
        user=request.user).dates('date', 'year', order='DESC').distinct()]
    context['current_page'] = 'reports'
    return render(request, 'money/category_summary.html', context)




@login_required
def category_summary_pdf(request):
    year = request.GET.get('year')
    context = get_summary_data(request, year)
    context['now'] = timezone.now()
    context['selected_year'] = year or timezone.now().year
    context['logo_url'] = request.build_absolute_uri('/static/img/logo.png')

    try:
        template = get_template('money/category_summary_pdf.html')
        html_string = template.render(context)
        html_string = "<style>@page { size: 8.5in 11in; margin: 1in; }</style>" + html_string

        if request.GET.get("preview") == "1":
            return HttpResponse(html_string)

        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(tmp.name)
            tmp.seek(0)
            response = HttpResponse(tmp.read(), content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename=\"category_summary.pdf\"'
            return response
    except Exception as e:
        logger.error(f"Error generating category summary PDF: {e}")
        messages.error(request, "Error generating PDF.")
        return redirect('category_summary')


# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->         S U B    C A T E G O R I E S 




class SubCategoryCreateView(LoginRequiredMixin, CreateView):
    model = SubCategory
    form_class = SubCategoryForm
    template_name = "money/sub_category_form.html"
    success_url = reverse_lazy('category_page')

    def form_valid(self, form):
        messages.success(self.request, "Sub-Category added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context



class SubCategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = SubCategory
    form_class = SubCategoryForm
    template_name = "money/sub_category_form.html"
    success_url = reverse_lazy('category_page')
    context_object_name = "sub_cat"

    def form_valid(self, form):
        messages.success(self.request, "Sub-Category updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context




class SubCategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = SubCategory
    template_name = "money/sub_category_confirm_delete.html"
    success_url = reverse_lazy('category_page')

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Sub-Category deleted successfully!")
            return response
        except models.ProtectedError:
            messages.error(self.request, "Cannot delete sub-category due to related transactions.")
            return redirect('category_page')
        except Exception as e:
            logger.error(f"Error deleting sub-category for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting sub-category.")
            return redirect('category_page')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'categories'
        return context

# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->           C L I E N T S



class ClientListView(LoginRequiredMixin, ListView):
    model = Client
    template_name = "money/client_list.html"
    context_object_name = "clients"
    ordering = ['business']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'clients'
        return context



class ClientCreateView(LoginRequiredMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = "money/client_form.html"
    success_url = reverse_lazy('client_list')

    def form_valid(self, form):
        messages.success(self.request, "Client added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'clients'
        return context



class ClientUpdateView(LoginRequiredMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = "money/client_form.html"
    success_url = reverse_lazy('client_list')

    def form_valid(self, form):
        messages.success(self.request, "Client updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'clients'
        return context



class ClientDeleteView(LoginRequiredMixin, DeleteView):
    model = Client
    template_name = "money/client_confirm_delete.html"
    success_url = reverse_lazy('client_list')

    def delete(self, request, *args, **kwargs):
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(self.request, "Client deleted successfully!")
            return response
        except models.ProtectedError:
            messages.error(self.request, "Cannot delete client due to related invoices.")
            return redirect('client_list')
        except Exception as e:
            logger.error(f"Error deleting client for user {request.user.id}: {e}")
            messages.error(self.request, "Error deleting client.")
            return redirect('client_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'clients'
        return context


# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->            R E P O R T S


def get_summary_data(request, year):
    EXCLUDED_INCOME_CATEGORIES = ['Equipment Sale']

    try:
        current_year = timezone.now().year
        selected_year = int(year) if year and str(year).isdigit() else current_year
    except ValueError:
        messages.error(request, "Invalid year selected.")
        selected_year = current_year

    transactions = Transaction.objects.filter(
        user=request.user,
        date__year=selected_year
    ).select_related('sub_cat__category')

    income_data = defaultdict(lambda: {
        'total': Decimal('0.00'),
        'subcategories': defaultdict(lambda: [Decimal('0.00'), None])
    })

    expense_data = defaultdict(lambda: {
        'total': Decimal('0.00'),
        'subcategories': defaultdict(lambda: [Decimal('0.00'), None])
    })

    for t in transactions:
        category = t.sub_cat.category if t.sub_cat and t.sub_cat.category else None
        sub_cat_name = t.sub_cat.sub_cat if t.sub_cat else "Uncategorized"
        cat_name = category.category if category else "Uncategorized"
        sched_line = category.schedule_c_line if category and category.schedule_c_line else None

        is_meals = t.sub_cat and t.sub_cat.slug == 'meals'
        is_fuel = t.sub_cat and t.sub_cat.slug == 'fuel'
        is_personal_vehicle = t.transport_type == "personal_vehicle"

        if is_meals:
            amount = round(t.amount * Decimal('0.5'), 2)
        elif is_fuel and is_personal_vehicle:
            amount = Decimal('0.00')
        else:
            amount = t.amount

        if t.trans_type == 'Income':
            if cat_name in EXCLUDED_INCOME_CATEGORIES:
                continue
            target_data = income_data
        else:
            target_data = expense_data

        target_data[cat_name]['total'] += amount
        target_data[cat_name]['subcategories'][sub_cat_name][0] += amount
        target_data[cat_name]['subcategories'][sub_cat_name][1] = sched_line

    def format_data(data_dict):
        return [
            {
                'category': cat,
                'total': values['total'],
                'subcategories': [(sub, amt_sched[0], amt_sched[1]) for sub, amt_sched in values['subcategories'].items()]
            }
            for cat, values in sorted(data_dict.items())
        ]

    income_category_totals = format_data(income_data)
    expense_category_totals = format_data(expense_data)

    income_total = sum(item['total'] for item in income_category_totals)
    expense_total = sum(item['total'] for item in expense_category_totals)

    try:
        rate = MileageRate.objects.first().rate if MileageRate.objects.exists() else Decimal("0.70")
    except Exception:
        rate = Decimal("0.70")

    total_mileage_miles = (
        Miles.objects.filter(
            user=request.user,
            tax__iexact="Yes",
            mileage_type="Taxable",
            date__year=selected_year,
        )
        .aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    )

    mileage_deduction_total = (total_mileage_miles * rate).quantize(Decimal('0.01'))

    net_profit = income_total - (expense_total + mileage_deduction_total)
    expense_total_with_mileage = expense_total + mileage_deduction_total


    available_years = Transaction.objects.filter(user=request.user).dates('date', 'year', order='DESC')

    return {
        'selected_year': selected_year,
        'income_category_totals': income_category_totals,
        'expense_category_totals': expense_category_totals,
        'income_category_total': income_total,
        'expense_category_total': expense_total,
        'expense_total_with_mileage': expense_total_with_mileage, 
        'mileage_deduction_total': mileage_deduction_total,
        'net_profit': net_profit,
        'available_years': [d.year for d in available_years],
    }




@login_required
def financial_statement(request):
    year = request.GET.get('year', str(timezone.now().year))
    context = get_summary_data(request, year)
    context['current_page'] = 'reports'
    return render(request, 'money/financial_statement.html', context)


@login_required
def financial_statement_pdf(request, year):
    try:
        selected_year = int(year)
    except ValueError:
        selected_year = timezone.now().year

    context = get_summary_data(request, selected_year)
    context['now'] = timezone.now()

    html_string = render_to_string('money/financial_statement_pdf.html', context)
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Financial_Statement_{selected_year}.pdf"'

    return response


def get_schedule_c_summary(transactions):
    line_summary = defaultdict(lambda: {'total': Decimal('0.00'), 'items': set()})

    for t in transactions:
        if not t.sub_cat or not t.sub_cat.category or not t.sub_cat.category.schedule_c_line:
            continue
        line = t.sub_cat.category.schedule_c_line
        amount = t.amount
        if t.trans_type == 'Expense':
            if t.sub_cat_id == 26:  # meals (50%)
                amount *= Decimal('0.5')
            elif t.sub_cat_id == 27 and t.transport_type == 'personal_vehicle':
                continue  # skip personal fuel
            amount = -abs(amount)
        line_summary[line]['total'] += amount
        line_summary[line]['items'].add(t.sub_cat.category.category)

    return [
        {'line': line, 'total': data['total'], 'categories': sorted(data['items'])}
        for line, data in sorted(line_summary.items())
    ]

    
    
@login_required
def schedule_c_summary(request):
    year = request.GET.get('year', timezone.now().year)
    transactions = Transaction.objects.filter(user=request.user, date__year=year).select_related('sub_cat__category')
    summary = get_schedule_c_summary(transactions)

    income_total = sum(t.amount for t in transactions if t.trans_type == 'Income')
    total_expenses = sum(row['total'] for row in summary if row['total'] < 0)
    net_profit = income_total + total_expenses

    return render(request, 'money/schedule_c_summary.html', {
        'summary': summary,
        'income_total': income_total,
        'net_profit': net_profit,
        'selected_year': year,
        'current_page': 'reports',
    })



@login_required
def schedule_c_summary_pdf(request, year):
    transactions = Transaction.objects.filter(user=request.user, date__year=year).select_related('sub_cat__category')
    summary = get_schedule_c_summary(transactions)
    income_total = sum(t.amount for t in transactions if t.trans_type == 'Income')
    total_expenses = sum(row['total'] for row in summary if row['total'] < 0)
    net_profit = income_total + total_expenses

    logo_url = request.build_absolute_uri(static('images/logo2.png'))

    html = render_to_string('money/schedule_c_summary_pdf.html', {
        'summary': summary,
        'income_total': income_total,
        'net_profit': net_profit,
        'selected_year': year,
        'logo_url': logo_url,
    })

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename=schedule_c_summary_{year}.pdf'
    HTML(string=html).write_pdf(response)
    return response



@login_required
def form_4797_view(request):
    sold_equipment = Equipment.objects.filter(date_sold__isnull=False, sale_price__isnull=False)
    report_data = []

    for item in sold_equipment:
        purchase_cost = Decimal('0.00') if item.deducted_full_cost else (item.purchase_price or Decimal('0.00'))
        gain = item.sale_price - item.purchase_cost

        report_data.append({
            'name': item.name,
            'date_sold': item.date_sold,
            'sale_price': item.sale_price,
            'purchase_cost': item.purchase_cost,
            'gain': gain,
        })

    context = {
        'report_data': report_data,
        'current_page': 'form_4797'
    }
    return render(request, 'money/form_4797.html', context)



@login_required
def form_4797_pdf(request):
    sold_equipment = Equipment.objects.filter(date_sold__isnull=False, sale_price__isnull=False)
    report_data = []

    for item in sold_equipment:
        basis = Decimal('0.00') if item.deducted_full_cost else (item.purchase_price or Decimal('0.00'))
        gain = item.sale_price - basis

        report_data.append({
            'name': item.name,
            'date_sold': item.date_sold,
            'sale_price': item.sale_price,
            'basis': basis,
            'gain': gain,
        })

    context = {
        'report_data': report_data,
        'company_name': "Airborne Images",
 
    }

    template = get_template('money/form_4797_pdf.html')
    html_string = template.render(context)

    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as output:
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(output.name)
        output.seek(0)
        pdf = output.read()

    preview = request.GET.get('preview') == '1'
    disposition = 'inline' if preview else 'attachment'
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'{disposition}; filename="form_4797.pdf"'
    return response




@login_required
def nhra_summary(request):
    current_year = timezone.now().year
    years = [current_year, current_year - 1, current_year - 2]
    excluded_ids = [35, 133, 34, 67, 100]

    summary_data = Transaction.objects.filter(
        user=request.user
    ).exclude(event__id__in=excluded_ids).filter(
        date__year__in=years, trans_type__isnull=False
    ).values('event__name', 'date__year', 'trans_type').annotate(
        total=Sum('amount')
    ).order_by('event__name', 'date__year')

    result = defaultdict(lambda: {y: {"income": 0, "expense": 0, "net": 0} for y in years})
    
    for item in summary_data:
        event = item['event__name']
        year = item['date__year']
        trans_type = item['trans_type'].lower()
        if event:
            result[event][year][trans_type] = item['total']
            result[event][year]['net'] = result[event][year]['income'] - result[event][year]['expense']

    result_dict = dict(result)

    logger.debug(f"NHRA summary data for user {request.user.id}: {result_dict}")

    context = {
        "years": years,
        "summary_data": result_dict,
        "urls": {
            "reports": "/money/"
        },
        'current_page': 'reports'
    }
    return render(request, "nhra/nhra_summary.html", context)





@login_required
def race_expense_report(request):
    current_year = now().year
    years = [current_year, current_year - 1, current_year - 2]

    include_meals = True
    
    travel_subcategories = [
        'Airfare',
        'Car Rental',
        'Fuel',
        'Hotels',
        'Other Travel',
    ]

    if include_meals:
        travel_subcategories.append('Meals')

    selected_event = request.GET.get('event', '').strip()

    base_qs = Transaction.objects.filter(
        user=request.user,
        trans_type='Expense',
        sub_cat__sub_cat__in=travel_subcategories,
        date__year__in=years
    ).select_related('event', 'sub_cat')

    all_events = (
        base_qs
        .filter(event__isnull=False)
        .values_list('event__title', flat=True)
        .distinct()
        .order_by('event__title')
    )

    if selected_event:
        base_qs = base_qs.filter(event__title=selected_event)

    summary_data = base_qs.values(
        'event__title', 'sub_cat__sub_cat', 'date__year'
    ).annotate(total=Sum('amount')).order_by('sub_cat__sub_cat', 'date__year')

    result = defaultdict(lambda: defaultdict(lambda: {y: Decimal('0.00') for y in years}))
    event_totals = defaultdict(lambda: {y: Decimal('0.00') for y in years})
    yearly_totals = {y: Decimal('0.00') for y in years}

    for item in summary_data:
        event = item['event__title'] or 'Unspecified'
        subcategory = item['sub_cat__sub_cat']
        year = item['date__year']
        amount = item['total'] or Decimal('0.00')

        result[event][subcategory][year] = amount
        event_totals[event][year] += amount
        yearly_totals[year] += amount

    context = {
        'years': years,
        'events': all_events,
        'selected_event': selected_event,
        'summary_data': dict(result),
        'event_totals': dict(event_totals),
        'yearly_totals': yearly_totals,
        'travel_subcategories': travel_subcategories,
        'current_page': 'reports',
    }

    return render(request, 'nhra/race_expense_report.html', context)




@login_required
def travel_expense_analysis(request):
    current_year = now().year
    available_years = list(range(2023, current_year + 1))

    selected_year = int(request.GET.get('year', current_year))

    income_subcat_id = 19
    expense_subcat_ids = [100, 23, 24, 27, 25, 26, 28]

    income_total = Transaction.objects.filter(
        user=request.user,
        date__year=selected_year,
        trans_type='Income',
        sub_cat_id=income_subcat_id
    ).aggregate(total=Sum('amount'))['total'] or 0

    expenses_qs = Transaction.objects.filter(
        user=request.user,
        date__year=selected_year,
        trans_type='Expense',
        sub_cat_id__in=expense_subcat_ids
    ).values('sub_cat__sub_cat', 'sub_cat_id') \
     .annotate(total=Sum('amount')).order_by('sub_cat__sub_cat')

    expense_data = []
    total_expense = sum(row['total'] for row in expenses_qs)

    for row in expenses_qs:
        amount = row['total']
        percentage = (amount / total_expense) * 100 if total_expense else 0
        expense_data.append({
            'name': row['sub_cat__sub_cat'],
            'amount': amount,
            'percentage': round(percentage, 2)
        })

    context = {
        'selected_year': selected_year,
        'available_years': available_years,
        'income_total': income_total,
        'expense_data': expense_data,
        'total_expense': total_expense,
        'current_page': 'reports',
    }

    return render(request, 'nhra/travel_expense_analysis.html', context)



@login_required
def travel_expense_analysis_pdf(request):
    selected_year = int(request.GET.get('year', now().year))

    income_subcat_id = 19
    expense_subcat_ids = [100, 23, 24, 27, 25, 26, 28]

    income_total = Transaction.objects.filter(
        user=request.user,
        date__year=selected_year,
        trans_type='Income',
        sub_cat_id=income_subcat_id
    ).aggregate(total=Sum('amount'))['total'] or 0

    expenses_qs = Transaction.objects.filter(
        user=request.user,
        date__year=selected_year,
        trans_type='Expense',
        sub_cat_id__in=expense_subcat_ids
    ).values('sub_cat__sub_cat', 'sub_cat_id') \
     .annotate(total=Sum('amount')).order_by('sub_cat__sub_cat')

    expense_data = []
    total_expense = sum(row['total'] for row in expenses_qs)

    for row in expenses_qs:
        amount = row['total']
        percentage = (amount / total_expense) * 100 if total_expense else 0
        expense_data.append({
            'name': row['sub_cat__sub_cat'],
            'amount': amount,
            'percentage': round(percentage, 2)
        })

    html_string = render_to_string('money/travel_expense_analysis_pdf.html', {
        'selected_year': selected_year,
        'income_total': income_total,
        'expense_data': expense_data,
        'total_expense': total_expense,
    })

    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    pdf_file = html.write_pdf()

    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename="Travel_Expense_Report_{selected_year}.pdf"'
    return response


@login_required
def race_expense_report_pdf(request):
    current_year = now().year
    years = [current_year, current_year - 1, current_year - 2]
    travel_subcategories = [
        'Travel: Car Rental', 'Travel: Flights', 'Travel: Fuel',
        'Travel: Hotel', 'Travel: Meals', 'Travel: Miscellaneous'
    ]
    transactions = Transaction.objects.filter(
        user=request.user,
        trans_type='Expense',
        sub_cat__sub_cat__in=travel_subcategories,
        date__year__in=years
    ).select_related('event', 'sub_cat')
    summary_data = transactions.values(
        'event__name', 'sub_cat__sub_cat', 'date__year'
    ).annotate(total=Sum('amount')).order_by('event__name', 'sub_cat__sub_cat', 'date__year')
    result = defaultdict(lambda: defaultdict(lambda: {y: 0 for y in years}))
    for item in summary_data:
        event = item['event__name'] or 'Unspecified'
        subcategory = item['sub_cat__sub_cat']
        year = item['date__year']
        result[event][subcategory][year] = item['total']
    event_totals = defaultdict(lambda: {y: 0 for y in years})
    yearly_totals = {y: 0 for y in years}
    for event, subcats in result.items():
        for subcat, year_data in subcats.items():
            for year, amount in year_data.items():
                event_totals[event][year] += amount
                yearly_totals[year] += amount
    context = {
        'years': years,
        'summary_data': dict(result),
        'event_totals': dict(event_totals),
        'yearly_totals': yearly_totals,
        'travel_subcategories': travel_subcategories,
        'current_page': 'reports'
    }
    try:
        template = get_template('money/race_expense_report.html')
        html_string = template.render(context)
        html_string = "<style>@page { size: 8.5in 11in; margin: 1in; }</style>" + html_string
        with tempfile.NamedTemporaryFile(delete=True) as output:
            HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(output.name)
            output.seek(0)
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="race_expense_report.pdf"'
            response.write(output.read())
        return response
    except Exception as e:
        logger.error(f"Error generating PDF for user {request.user.id}: {e}")
        messages.error(request, "Error generating PDF.")
        return redirect('race_expense_report')



@login_required
def reports_page(request):
    context = {'current_page': 'reports'}
    return render(request, 'money/reports.html', context)


# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->           E M A I L S


@require_POST
def send_invoice_email(request, invoice_id):
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    try:
        # Generate invoice HTML and PDF
        html_string = render_to_string('money/invoice_detail.html', {
            'invoice': invoice,
            'current_page': 'invoices'
        })
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf_file = html.write_pdf()

        # Email content
        subject = f"Invoice #{invoice.invoice_numb} from Airborne Images"
        body = f"""
        Hi {invoice.client.first},<br><br>
        Attached is your invoice for the event: <strong>{invoice.event}</strong>.<br><br>
        Let me know if you have any questions!<br><br>
        Thank you!,<br>
        <strong>Tom Stout</strong><br>
        Airborne Images<br>
        <a href="http://www.airborneimages.com" target="_blank">www.AirborneImages.com</a><br>
        "Views From Above!"<br>
        """

        from_email = "tom@tom-stout.com"
        recipient = [invoice.client.email or getattr(settings, 'DEFAULT_EMAIL', None)]
        if not recipient[0]:
            raise ValueError("No valid email address provided.")

        # Construct and send email with BCC
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=recipient,
            bcc=["tom@tom-stout.com"]
        )
        email.content_subtype = 'html'
        email.attach(f"Invoice_{invoice.invoice_numb}.pdf", pdf_file, "application/pdf")
        email.send()

        return JsonResponse({'status': 'success', 'message': 'Invoice emailed successfully!'})
    except Exception as e:
        logger.error(f"Error sending email for invoice {invoice_id} by user {request.user.id}: {e}")
        return JsonResponse({'status': 'error', 'message': 'Failed to send email'}, status=500)
    

# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->           M I L E A G E


def get_mileage_context(request):
    try:
        rate = MileageRate.objects.first().rate if MileageRate.objects.exists() else 0.70
    except Exception as e:
        logger.error(f"Error fetching mileage rate: {e}")
        rate = 0.70
        messages.error(request, "Error fetching mileage rate. Using default rate.")

    year = datetime.now().year
    entries = Miles.objects.filter(user=request.user, date__year=year)
    paginator = Paginator(entries, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    taxable = entries.filter(mileage_type='Taxable')
    total_miles = taxable.aggregate(Sum('total'))['total__sum'] or 0

    return {
        'mileage_list': page_obj,
        'page_obj': page_obj,
        'total_miles': total_miles,
        'taxable_dollars': total_miles * Decimal(str(rate)),
        'current_year': year,
        'mileage_rate': rate,
        'current_page': 'mileage'
    }



def _get_mileage_rate():
    """Return the active mileage rate (Decimal). Falls back to 0.70."""
    fallback = Decimal("0.70")
    try:
        obj = MileageRate.objects.first()
        if not obj or obj.rate is None:
            return fallback
        return Decimal(str(obj.rate))
    except Exception as e:
        return fallback

def _build_sort_state(current_sort, keys, default_key="-date"):
    """
    Build a sort_state dict compatible with your template usage:
      sort_state.<key>.is_asc / is_desc / next
    """
    state = {}
    for k in keys:
        asc = k
        desc = f"-{k}"
        is_asc = current_sort == asc
        is_desc = current_sort == desc
        if is_asc:
            nxt = desc
        elif is_desc:
            nxt = default_key
        else:
            nxt = asc
        state[k] = type("S", (), {"is_asc": is_asc, "is_desc": is_desc, "next": nxt})
    return state


SORT_MAP = {
    "date": "date",
    "-date": "-date",
    "event": "event__title",
    "-event": "-event__title",
    "invoice_number": "invoice_number",
    "-invoice_number": "-invoice_number",
    "mileage_type": "mileage_type",
    "-mileage_type": "-mileage_type",
    "begin": "begin",
    "-begin": "-begin",
    "end": "end",
    "-end": "-end",
    "total": "total",
    "-total": "-total",
    "amount": "amount",
    "-amount": "-amount",
}

SORT_KEYS = [
    "date", "event", "invoice_number", "mileage_type",
    "begin", "end", "total", "amount",
]


from django.db.models.functions import ExtractYear

@login_required
def mileage_log(request):
    # Available years for this user (DESC)
    years_qs = (
        Miles.objects
        .filter(user=request.user)
        .annotate(y=ExtractYear('date'))
        .values_list('y', flat=True)
        .distinct()
        .order_by('-y')
    )
    years = list(years_qs)

    # Parse ?year=YYYY (fallback to latest available or current year)
    try:
        year = int(request.GET.get("year")) if request.GET.get("year") else None
    except (TypeError, ValueError):
        year = None
    if not year:
        year = (years[0] if years else datetime.now().year)

    rate = _get_mileage_rate()

    qs = (
        Miles.objects
        .select_related("event", "client")
        .filter(user=request.user, date__year=year)
    )

    amount_expr = ExpressionWrapper(
        F("total") * rate,
        output_field=DecimalField(max_digits=10, decimal_places=2)
    )
    qs = qs.annotate(
        amount=Case(
            When(mileage_type="Taxable", then=amount_expr),
            default=Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )
    )

    current_sort = request.GET.get("sort") or "-date"
    order_by = SORT_MAP.get(current_sort, "-date")
    qs = qs.order_by(order_by)

    taxable = qs.filter(mileage_type="Taxable")
    total_miles = taxable.aggregate(total=Sum("total"))["total"] or 0
    taxable_dollars = (Decimal(str(total_miles)) * rate).quantize(Decimal("0.01"))

    paginator = Paginator(qs, 50)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    sort_state = _build_sort_state(current_sort, SORT_KEYS, default_key="-date")

    context = {
        "mileage_list": page_obj,
        "page_obj": page_obj,
        "total_miles": total_miles,
        "taxable_dollars": taxable_dollars,
        "current_year": year,
        "mileage_rate": rate,
        "current_page": "mileage",
        "sort_state": sort_state,
        "years": years,  # 👈 add to context
    }
    return render(request, "money/mileage_log.html", context)




class MileageCreateView(LoginRequiredMixin, CreateView):
    model = Miles
    form_class = MileageForm
    template_name = 'money/mileage_form.html'
    success_url = reverse_lazy('mileage_log')

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Mileage entry added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'mileage'
        return context


class MileageUpdateView(LoginRequiredMixin, UpdateView):
    model = Miles
    form_class = MileageForm
    template_name = 'money/mileage_form.html'
    success_url = reverse_lazy('mileage_log')

    def get_queryset(self):
        return Miles.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Mileage entry updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'mileage'
        return context


class MileageDeleteView(LoginRequiredMixin, DeleteView):
    model = Miles
    template_name = 'money/mileage_confirm_delete.html'
    success_url = reverse_lazy('mileage_log')

    def get_queryset(self):
        return Miles.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Mileage entry deleted successfully!")
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'mileage'
        return context



@login_required
def update_mileage_rate(request):
    mileage_rate = MileageRate.objects.first() or MileageRate(rate=0.70)
    if request.method == 'POST':
        form = MileageRateForm(request.POST, instance=mileage_rate)
        if form.is_valid():
            form.save()
            messages.success(request, "Mileage rate updated successfully!")
            return redirect('mileage_log')
        else:
            messages.error(request, "Error updating mileage rate. Please check the form.")
    else:
        form = MileageRateForm(instance=mileage_rate)
    context = {'form': form, 'current_page': 'mileage'}
    return render(request, 'money/update_mileage_rate.html', context)


@login_required
def export_mileage_csv(request):
    miles_entries = Miles.objects.filter(user=request.user).select_related('client')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="mileage.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Date',
        'Invoice #',
        'Event',
        'Client',
        'Start Odometer',
        'End Odometer',
        'Total Miles',
        'Tax Deductible',
        'Vehicle',
        'Mileage Type',
    ])

    for entry in miles_entries:
        writer.writerow([
            entry.date,
            entry.invoice_number if entry.invoice_number else '',
            entry.event if entry.event else '',
            str(entry.client) if entry.client else '',
            entry.begin,
            entry.end,
            entry.total,
            entry.tax,
            entry.vehicle or '',
            entry.mileage_type,
        ])

    return response


# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->            E V E N T S 


class EventListView(LoginRequiredMixin, ListView):
    model = Event
    template_name = 'nhra/event_list.html'
    context_object_name = 'events'
    paginate_by = 25

    def get_queryset(self):
        queryset = Event.objects.all().order_by('title')
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query) |
                Q(location_city__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'events'
        context['query'] = self.request.GET.get('q', '')
        return context



class EventCreateView(LoginRequiredMixin, CreateView):
    model = Event
    form_class = EventForm
    template_name = 'money/event_form.html'
    success_url = reverse_lazy('event_list')

    def form_valid(self, form):
        messages.success(self.request, "event added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'events'
        return context


class EventUpdateView(LoginRequiredMixin, UpdateView):
    model = Event
    form_class = EventForm
    template_name = 'money/event_form.html'
    success_url = reverse_lazy('event_list')

    def form_valid(self, form):
        messages.success(self.request, "Event updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'events'
        return context
    

class EventDetailView(LoginRequiredMixin, DetailView):
    model = Event
    template_name = 'money/event_detail.html'
    context_object_name = 'event'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'events'
        return context



class EventDeleteView(LoginRequiredMixin, DeleteView):
    model = Event
    template_name = 'money/event_confirm_delete.html'
    success_url = reverse_lazy('event_list')

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Event deleted successfully!")
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'events'
        return context

# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->          R E C U R R I N G   T R A N S 


class RecurringTransactionListView(LoginRequiredMixin, ListView):
    model = RecurringTransaction
    template_name = 'money/recurring_list.html'
    context_object_name = 'recurring_transactions'

    def get_queryset(self):
        return RecurringTransaction.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'recurring transactions'
        return context



class RecurringTransactionCreateView(LoginRequiredMixin, CreateView):
    model = RecurringTransaction
    form_class = RecurringTransactionForm
    template_name = 'money/recurring_form.html'
    success_url = reverse_lazy('recurring_transaction_list')
    context = { 'current_page': 'recurring transactions', }

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, "Recurring transaction added successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'recurring_transactions'
        return context


class RecurringTransactionUpdateView(LoginRequiredMixin, UpdateView):
    model = RecurringTransaction
    form_class = RecurringTransactionForm
    template_name = 'money/recurring_form.html'
    success_url = reverse_lazy('recurring_transaction_list')
    context = { 'current_page': 'recurring transactions', }

    def get_queryset(self):
        return RecurringTransaction.objects.filter(user=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Recurring transaction updated successfully!")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'recurring_transactions'
        return context


class RecurringTransactionDeleteView(LoginRequiredMixin, DeleteView):
    model = RecurringTransaction
    template_name = 'money/recurring_confirm_delete.html'
    success_url = reverse_lazy('recurring_transaction_list')
    context = { 'current_page': 'recurring transactions', }

    def get_queryset(self):
        return RecurringTransaction.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "Recurring transaction deleted successfully!")
        return super().delete(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_page'] = 'recurring_transactions'
        return context


@staff_member_required
def recurring_report_view(request):
    year = int(request.GET.get('year', now().year))
    months = range(1, 13)

    templates = RecurringTransaction.objects.filter(user=request.user).order_by('transaction')

    transactions = Transaction.objects.filter(
        recurring_template__in=templates,
        date__year=year
    ).values('recurring_template_id', 'date__month').annotate(total_amount=Sum('amount'))

    amount_map = {(t['recurring_template_id'], t['date__month']): t['total_amount'] for t in transactions}

    data = []
    for template in templates:
        row = {
            'template': template,
            'monthly_amounts': [
                amount_map.get((template.id, month), None) for month in months
            ]
        }
        data.append(row)

    context = {
        'data': data,
        'months': [month_name[m] for m in months],
        'year': year,
        'current_page': 'recurring_transactions'
    }
    return render(request, 'money/recurring_report.html', context)



@staff_member_required
def run_monthly_recurring_view(request):
    today = now().date()
    created = 0
    skipped = 0

    try:
        with transaction.atomic():
            recurrences = RecurringTransaction.objects.filter(active=True, user=request.user)
            for r in recurrences:
                exists = Transaction.objects.filter(
                    user=r.user,
                    transaction=r.transaction,
                    date__year=today.year,
                    date__month=today.month
                ).exists()
                if exists:
                    skipped += 1
                    continue

                Transaction.objects.create(
                    date=today,
                    trans_type=r.trans_type,
                    category=r.category,
                    sub_cat=r.sub_cat,
                    amount=r.amount,
                    transaction=r.transaction,
                    team=r.team,
                    event=r.event,
                    tax=r.tax,
                    user=r.user,
       
                )
                created += 1

        messages.success(request, f"{created} recurring transactions created, {skipped} skipped.")
        return redirect('recurring_transaction_list')

    except Exception as e:
        logger.error(f"Error running monthly recurring for user {request.user.id}: {e}")
        messages.error(request, "Error running monthly recurring.")
        return redirect('recurring_transaction_list')



# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=->            R E C E I P T S


@login_required
def receipts_list(request):
    query = request.GET.get('search', '')
    receipts = Transaction.objects.filter(user=request.user, receipt__isnull=False)

    if query:
        receipts = receipts.filter(
            Q(invoice_numb__icontains=query) |
            Q(transaction__icontains=query)
        )

    receipts = receipts.order_by('-date')
    paginator = Paginator(receipts, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'receipts': page_obj.object_list,
        'page_obj': page_obj,
        'request': request,
    }
    return render(request, 'money/receipts_list.html', context)


@login_required
def receipt_detail(request, pk):
    receipt = get_object_or_404(Transaction, pk=pk, user=request.user, receipt__isnull=False)
    return render(request, 'money/receipt_detail.html', {'receipt': receipt})