from django.test import TestCase
from django.urls import reverse

# Create your tests here.

class MarketplaceViewTests(TestCase):
    def test_homepage_loads_correctly(self):
        """Tests that the homepage returns a 200 status code and contains expected text."""
        
        # Get the URL for the homepage using its name from urls.py
        url = reverse('home') # I have corrected 'homepage' to 'home' to match your urls.py
        
        # Use the test client to "visit" the page
        response = self.client.get(url)
        
        # Check that the page was loaded successfully (HTTP 200 OK)
        self.assertEqual(response.status_code, 200)
        
        # Check that the page contains the main brand name from your base.html
        self.assertContains(response, "Gamer's Market")