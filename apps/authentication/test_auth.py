from django.test import TestCase
from apps.authentication.models import User

class UserAuthenticationTests(TestCase):
    def test_user_creation_and_roles(self):
        admin = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='password123',
            role=User.Role.SUPER_ADMIN
        )
        self.assertTrue(admin.is_super_admin)
        self.assertTrue(admin.can_manage_channels)
        self.assertTrue(admin.can_manage_artists)
        self.assertTrue(admin.can_edit_settings)

        manager = User.objects.create_user(
            username='manager',
            email='manager@test.com',
            password='password123',
            role=User.Role.MANAGER
        )
        self.assertFalse(manager.is_super_admin)
        self.assertTrue(manager.can_manage_artists)
        self.assertFalse(manager.can_manage_channels)

        viewer = User.objects.create_user(
            username='viewer',
            email='viewer@test.com',
            password='password123',
            role=User.Role.VIEWER
        )
        self.assertFalse(viewer.can_manage_artists)
        self.assertFalse(viewer.can_manage_channels)
