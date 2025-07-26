# marketplace/forms.py
from django.db.models import Sum
from django import forms
from .models import (
    Product, Review, WithdrawalRequest, Order, SupportTicket, Profile, Category,
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
                    initial=initial_filters.get(field_name)
                )

class ReviewForm(forms.ModelForm):
    RATING_CHOICES = [(i, str(i)) for i in reversed(range(1, 6))]
    rating = forms.ChoiceField(choices=RATING_CHOICES, widget=forms.RadioSelect(attrs={'class': 'rating-radio'}))
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = { 'comment': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}), }

class WithdrawalRequestForm(forms.ModelForm):
    class Meta:
        model = WithdrawalRequest
        fields = ['amount']
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.balance = kwargs.pop('balance', 0)
        super(WithdrawalRequestForm, self).__init__(*args, **kwargs)
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if self.balance is None: self.balance = 0
        if amount > self.balance:
            raise forms.ValidationError(f"Cannot withdraw more than your available balance of Rs{self.balance:.2f}.")
        if amount <= 0:
            raise forms.ValidationError("Withdrawal amount must be positive.")
        return amount

class SupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ['subject', 'message']

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