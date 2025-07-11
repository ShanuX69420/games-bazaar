# marketplace/forms.py
from django import forms
from .models import Product, Review

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        # Define the fields to show in the form
        fields = ['title', 'description', 'price', 'category', 'image']

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