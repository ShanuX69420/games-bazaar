from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile


class ProfilePictureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="tester", password="pass")

    def test_profile_picture_persists_after_upload(self):
        self.client.login(username="tester", password="pass")

        image_content = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        uploaded = SimpleUploadedFile("avatar.gif", image_content, content_type="image/gif")

        url = reverse("public_profile", kwargs={"username": "tester"})
        self.client.post(url, {"image": uploaded})

        self.user.refresh_from_db()
        saved_path = self.user.profile.image.name
        self.assertNotEqual(saved_path, "profile_pics/default.jpg")

        response = self.client.get(url)
        self.assertContains(response, self.user.profile.image.url)
