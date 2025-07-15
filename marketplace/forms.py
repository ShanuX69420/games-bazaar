# marketplace/forms.py
from django.db.models import Sum
from django import forms
from .models import Product, Review, WithdrawalRequest, Order, SupportTicket, Profile


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        # We remove 'game' and 'category' because they will be set automatically
        fields = ['listing_title', 'description', 'price', 'image']

class ReviewForm(forms.ModelForm):
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]
    rating = forms.ChoiceField(
        choices=RATING_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'rating-radio'})
    )

    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 4}),
        }


# marketplace/forms.py

class WithdrawalRequestForm(forms.ModelForm):
    class Meta:
        model = WithdrawalRequest
        fields = ['amount']

    def __init__(self, *args, **kwargs):
        # We get the user and balance passed from the view
        self.user = kwargs.pop('user', None)
        self.balance = kwargs.pop('balance', 0)
        super(WithdrawalRequestForm, self).__init__(*args, **kwargs)

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')

        if self.balance is None:
            self.balance = 0

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