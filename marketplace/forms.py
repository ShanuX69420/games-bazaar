# marketplace/forms.py
from django.db.models import Sum
from django import forms
from .models import (
    Product, Review, ReviewReply, WithdrawalRequest, Order, SupportTicket, Profile, Category,
    Filter, FilterOption, GameCategory, ProductImage
)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
import re

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
            'stock': forms.NumberInput(attrs={'class': 'form-control'}),
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
        super().__init__(*args, **kwargs)

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

    def clean_stock(self):
        stock = self.cleaned_data.get('stock')
        if stock is not None and stock == 0:
            raise forms.ValidationError("Stock cannot be 0. Leave empty if stock is not applicable, or enter a positive number.")
        return stock

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
        ('', 'Select Payment Method'),
        ('easypaisa', 'EasyPaisa'),
        ('jazzcash', 'JazzCash'),
        ('bank_transfer', 'Bank Transfer'),
    ]
    
    payment_method = forms.ChoiceField(
        choices=PAYMENT_METHOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_payment_method'}),
        required=True
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
    
    account_number = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter account number',
            'id': 'id_account_number'
        }),
        required=False
    )
    
    iban = forms.CharField(
        max_length=24,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter IBAN (24 digits)',
            'id': 'id_iban'
        }),
        required=False
    )

    class Meta:
        model = WithdrawalRequest
        fields = ['amount', 'payment_method', 'account_title', 'account_number', 'iban']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'})
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.balance = kwargs.pop('balance', 0)
        super(WithdrawalRequestForm, self).__init__(*args, **kwargs)
    
    def clean_payment_method(self):
        payment_method = self.cleaned_data.get('payment_method')
        if not payment_method:
            raise forms.ValidationError("Please select a payment method.")
        return payment_method
    
    def clean_account_title(self):
        account_title = self.cleaned_data.get('account_title')
        payment_method = self.cleaned_data.get('payment_method')
        
        if payment_method and not account_title:
            raise forms.ValidationError("Account title is required.")
        
        if account_title and len(account_title.strip()) < 2:
            raise forms.ValidationError("Account title must be at least 2 characters long.")
        
        return account_title.strip() if account_title else account_title
    
    def clean_account_number(self):
        account_number = self.cleaned_data.get('account_number')
        payment_method = self.cleaned_data.get('payment_method')
        
        if payment_method in ['easypaisa', 'jazzcash'] and not account_number:
            raise forms.ValidationError("Account number is required for mobile wallet payments.")
        
        if account_number:
            # Basic validation for mobile numbers (11 digits starting with 03)
            if payment_method in ['easypaisa', 'jazzcash']:
                if not account_number.isdigit() or len(account_number) != 11 or not account_number.startswith('03'):
                    raise forms.ValidationError("Please enter a valid mobile number (11 digits starting with 03).")
        
        return account_number
    
    def clean_iban(self):
        iban = self.cleaned_data.get('iban')
        payment_method = self.cleaned_data.get('payment_method')
        
        if payment_method == 'bank_transfer' and not iban:
            raise forms.ValidationError("IBAN is required for bank transfers.")
        
        if iban:
            # Basic IBAN validation for Pakistan (PK followed by 22 digits)
            iban_clean = iban.replace(' ', '').upper()
            if not iban_clean.startswith('PK') or len(iban_clean) != 24 or not iban_clean[2:].isdigit():
                raise forms.ValidationError("Please enter a valid Pakistani IBAN (24 characters starting with PK).")
        
        return iban
    
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