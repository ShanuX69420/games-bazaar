# marketplace/forms.py
from django.db.models import Sum
from django import forms
from .models import (
    Product, Review, ReviewReply, WithdrawalRequest, DepositRequest, Order, SupportTicket, Profile, Category,
    Filter, FilterOption, GameCategory, ProductImage
)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from decimal import Decimal
import re
import os

# Custom form field to handle the display of filter options
class FilterOptionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.value

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'listing_title', 'description', 'post_purchase_message',
            'price', 'stock', 'automatic_delivery', 'stock_details'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'stock_details': forms.Textarea(attrs={'rows': 8, 'class': 'form-control'}),
            'listing_title': forms.TextInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
            'automatic_delivery': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'post_purchase_message': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
        }
        labels = {
            'listing_title': 'Title',
            'description': 'Detailed Description',
            'stock_details': 'Products for Automatic Delivery',
            'post_purchase_message': 'Message to the buyer after payment',
            'stock': 'In Stock',
        }
    
    def __init__(self, *args, **kwargs):
        game_category_link = kwargs.pop('game_category_link', None)
        commission_rate = kwargs.pop('commission_rate', None)
        super().__init__(*args, **kwargs)

        self.commission_rate = Decimal(str(commission_rate)) if commission_rate is not None else None

        price_field = self.fields.get('price')
        if price_field:
            price_field.label = 'Amount you will receive'
            if self.commission_rate is not None:
                price_field.help_text = (
                    f"You receive this amount. Buyers pay this plus {self.commission_rate}% marketplace fee."
                )
                price_field.widget.attrs['data-commission-rate'] = str(self.commission_rate)
            else:
                price_field.help_text = "You receive this amount per sale."
            price_field.widget.attrs.setdefault('min', '0')
            price_field.widget.attrs.setdefault('step', '0.01')

        stock_details_field = self.fields.get('stock_details')
        if stock_details_field:
            stock_details_field.widget.attrs.setdefault(
                'placeholder',
                "Example:\nCODE-1234-ABCD\nCODE-5678-EFGH\nCODE-9012-IJKL"
            )
            stock_details_field.help_text = "Automatic delivery pulls one line per buyer (top to bottom)."

        # Hide automatic_delivery field if category doesn't allow it
        if game_category_link and not game_category_link.allows_automated_delivery:
            self.fields.pop('automatic_delivery', None)

        if game_category_link:
            initial_filters = {}
            if self.instance and self.instance.pk:
                for option in self.instance.filter_options.all():
                    initial_filters[f'filter_{option.filter_id}'] = option

            for f in game_category_link.filters.all().prefetch_related('options'):
                field_name = f'filter_{f.id}'
                self.fields[field_name] = FilterOptionChoiceField(
                    label=f.name,
                    queryset=f.options.all(),
                    required=True,
                    widget=forms.Select(attrs={'class': 'form-select mb-3'}),
                    initial=initial_filters.get(field_name),
                    empty_label=f"Select {f.name}"
                )

        if self.errors:
            for field_name in self.errors:
                if field_name in self.fields:
                    widget = self.fields[field_name].widget
                    existing_classes = widget.attrs.get('class', '')
                    if 'is-invalid' not in existing_classes:
                        widget.attrs['class'] = (existing_classes + ' is-invalid').strip()

    def clean_stock(self):
        stock = self.cleaned_data.get('stock')
        if stock is not None and stock == 0:
            raise forms.ValidationError("Stock cannot be 0. Leave empty if stock is not applicable, or enter a positive number.")
        return stock

    def clean_listing_title(self):
        return (self.cleaned_data.get('listing_title') or '').strip()

    def clean_description(self):
        return (self.cleaned_data.get('description') or '').strip()

class ReviewForm(forms.ModelForm):
    RATING_CHOICES = [(i, str(i)) for i in reversed(range(1, 6))]
    rating = forms.ChoiceField(choices=RATING_CHOICES, widget=forms.RadioSelect(attrs={'class': 'rating-radio'}))
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = { 'comment': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}), }

class ReviewReplyForm(forms.ModelForm):
    class Meta:
        model = ReviewReply
        fields = ['reply_text']
        widgets = {
            'reply_text': forms.Textarea(attrs={
                'rows': 3, 
                'class': 'form-control', 
                'placeholder': 'Write your response to this review...',
                'maxlength': '1000'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reply_text'].label = 'Your Reply'

class WithdrawalRequestForm(forms.ModelForm):
    PAYMENT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('easypaisa', 'Easypaisa'),
        ('jazzcash', 'JazzCash'),
        ('sadapay', 'SadaPay'),
        ('nayapay', 'NayaPay'),
    ]

    payment_method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_payment_method'}),
        required=False,
        initial='bank_transfer'
    )

    account_title = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter account holder name',
            'id': 'id_account_title'
        }),
        required=False
    )

    bank_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter bank name (e.g. HBL, MCB)',
            'id': 'id_bank_name'
        }),
        required=False
    )

    account_identifier = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter account number or IBAN',
            'id': 'id_account_identifier'
        }),
        required=False
    )
    
    class Meta:
        model = WithdrawalRequest
        fields = ['amount', 'payment_method', 'account_title', 'bank_name']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'})
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.balance = kwargs.pop('balance', 0)
        super(WithdrawalRequestForm, self).__init__(*args, **kwargs)

        # Pre-fill identifier if editing an existing request
        if self.instance and self.instance.pk:
            if self.instance.iban:
                self.fields['account_identifier'].initial = self.instance.iban
            elif self.instance.account_number:
                self.fields['account_identifier'].initial = self.instance.account_number
    
    def clean_payment_method(self):
        payment_method = self.cleaned_data.get('payment_method') or 'bank_transfer'
        return payment_method
    
    def clean_account_title(self):
        account_title = self.cleaned_data.get('account_title')
        
        if not account_title:
            raise forms.ValidationError("Account title is required.")
        
        account_title = account_title.strip()
        if len(account_title) < 2:
            raise forms.ValidationError("Account title must be at least 2 characters long.")
        
        return account_title

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if self.balance is None: self.balance = 0
        
        # Get available balance (this will auto-release eligible funds)
        available_balance = self.user.profile.available_balance if self.user else 0
        
        if amount > available_balance:
            if not self.user.profile.is_verified_seller:
                raise forms.ValidationError(f"Cannot withdraw more than your available balance of Rs{available_balance:.2f}. Funds from recent sales are held for 72 hours each after order completion.")
            else:
                raise forms.ValidationError(f"Cannot withdraw more than your available balance of Rs{available_balance:.2f}.")
        if amount <= 0:
            raise forms.ValidationError("Withdrawal amount must be positive.")
        return amount

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method') or 'bank_transfer'
        identifier = (cleaned_data.get('account_identifier') or '').strip()
        bank_name = (cleaned_data.get('bank_name') or '').strip()

        account_number_value = ''
        iban_value = ''

        if identifier:
            identifier_normalized = identifier.replace(' ', '')
        else:
            identifier_normalized = ''
        cleaned_data['account_identifier'] = identifier_normalized

        if bank_name:
            bank_name = bank_name.strip()
            cleaned_data['bank_name'] = bank_name
        else:
            bank_name = ''
            cleaned_data['bank_name'] = ''

        if payment_method == 'bank_transfer':
            if not bank_name:
                self.add_error('bank_name', "Bank name is required for bank transfers.")

            if not identifier_normalized:
                self.add_error('account_identifier', "Provide your bank account number or IBAN.")
            else:
                identifier_upper = identifier_normalized.upper()
                if identifier_upper.startswith('PK'):
                    if len(identifier_upper) != 24 or not identifier_upper[2:].isdigit():
                        self.add_error('account_identifier', "Please enter a valid Pakistani IBAN (24 characters starting with PK).")
                    else:
                        iban_value = identifier_upper
                else:
                    if not re.fullmatch(r'^[0-9+\-]{6,32}$', identifier_normalized):
                        self.add_error('account_identifier', "Enter a valid bank account number (6-32 digits, optional + or -).")
                    else:
                        account_number_value = identifier_normalized

            # If we successfully parsed an IBAN, clear account number and vice versa
            if iban_value:
                account_number_value = ''
            elif account_number_value:
                iban_value = ''
        else:
            # Non-bank wallets require an account number and must not include an IBAN or bank name
            if not identifier_normalized:
                self.add_error('account_identifier', "Account or wallet number is required for this payment method.")
            elif not re.fullmatch(r'^\+?[0-9]{8,16}$', identifier_normalized):
                self.add_error('account_identifier', "Enter a valid wallet number (8-16 digits, optional leading +).")
            else:
                account_number_value = identifier_normalized
            iban_value = ''
            if bank_name:
                self.add_error('bank_name', "Bank name should only be provided for bank transfers.")
            cleaned_data['bank_name'] = ''

        cleaned_data['_account_number'] = account_number_value
        cleaned_data['_iban'] = iban_value
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        account_number_value = self.cleaned_data.get('_account_number', '').strip()
        iban_value = self.cleaned_data.get('_iban', '').strip()

        instance.account_number = account_number_value or None
        instance.iban = iban_value or None
        if instance.payment_method != 'bank_transfer':
            instance.bank_name = None

        if commit:
            instance.save()
        return instance

class DepositRequestForm(forms.ModelForm):
    """Form to capture manual deposit submissions with basic validation safeguards."""
    MINIMUM_AMOUNT = Decimal('1000.00')
    ALLOWED_MIME_TYPES = {
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
        'application/pdf',
    }
    MAX_UPLOAD_SIZE_MB = 10
    
    receipt = forms.FileField(
        label='Payment receipt',
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*,.pdf'
        }),
        help_text='Upload a clear screenshot or PDF of your bank transfer. Max 10MB.',
        required=True
    )
    
    class Meta:
        model = DepositRequest
        fields = ['amount', 'payment_reference', 'receipt', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '1000',
                'placeholder': 'Enter deposit amount (min Rs1000)'
            }),
            'payment_reference': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional bank reference / transaction ID'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional details for the finance team (optional)'
            }),
        }
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is None or amount <= 0:
            raise forms.ValidationError("Deposit amount must be greater than zero.")
        if amount < self.MINIMUM_AMOUNT:
            raise forms.ValidationError(f"Minimum deposit is Rs{self.MINIMUM_AMOUNT:.0f}.")
        return amount
    
    def clean_receipt(self):
        uploaded = self.cleaned_data.get('receipt')
        if not uploaded:
            raise forms.ValidationError("Please upload a receipt for your deposit.")
        
        max_size_bytes = self.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if uploaded.size > max_size_bytes:
            raise forms.ValidationError(f"Receipt file cannot exceed {self.MAX_UPLOAD_SIZE_MB}MB.")
        
        if uploaded.size < 512:
            raise forms.ValidationError("Receipt file appears to be empty. Please upload a valid screenshot or PDF.")
        
        # Basic filename sanitisation
        filename = os.path.basename(uploaded.name)
        if any(char in filename for char in ['..', '/', '\\']):
            raise forms.ValidationError("Invalid file name detected.")
        
        content_type = getattr(uploaded, 'content_type', None)
        if content_type and content_type.lower() not in self.ALLOWED_MIME_TYPES:
            raise forms.ValidationError("Unsupported file type. Please upload an image or PDF receipt.")
        
        # Fallback to extension check if content type missing
        if not content_type:
            _, ext = os.path.splitext(filename)
            allowed_ext = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf'}
            if ext.lower() not in allowed_ext:
                raise forms.ValidationError("Unsupported file format. Allowed: JPEG, PNG, GIF, WEBP, PDF.")
        
        return uploaded

class SupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ['user_type', 'issue_category', 'order_number', 'subject', 'message']
        widgets = {
            'user_type': forms.Select(attrs={
                'class': 'form-control',
                'id': 'id_user_type'
            }),
            'issue_category': forms.Select(attrs={
                'class': 'form-control',
                'id': 'id_issue_category'
            }),
            'order_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., ORD-123456',
                'id': 'id_order_number'
            }),
            'subject': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Brief description of your issue'
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Please describe your issue in detail...'
            })
        }
        labels = {
            'user_type': 'I am contacting as a',
            'issue_category': 'Issue Category',
            'order_number': 'Order Number (if applicable)',
            'subject': 'Subject',
            'message': 'Detailed Message'
        }

class ProfilePictureForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['image']

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['show_listings_on_site']
        widgets = { 'show_listings_on_site': forms.RadioSelect(attrs={'onchange': 'this.form.submit()'}) }

class CustomUserCreationForm(forms.ModelForm):
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'class': 'form-control', 'placeholder': 'Password'}),
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password')

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not re.match(r'^[a-zA-Z0-9]+$', username):
            raise forms.ValidationError("Username can only contain letters and numbers.")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with that username already exists.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("A user with that email already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")

        if len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters long.")

        if not any(char.isalpha() for char in password):
            raise forms.ValidationError("Password must contain at least one letter.")

        if not any(char.isdigit() for char in password):
            raise forms.ValidationError("Password must contain at least one number.")

        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user
