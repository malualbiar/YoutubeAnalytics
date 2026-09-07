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

    def test_users_manage_view_access_control(self):
        from django.urls import reverse
        admin = User.objects.create_superuser(
            username='admin_user_mgr',
            email='admin_mgr@test.com',
            password='password123',
            role=User.Role.SUPER_ADMIN
        )
        viewer = User.objects.create_user(
            username='viewer_user_mgr',
            email='viewer_mgr@test.com',
            password='password123',
            role=User.Role.VIEWER
        )

        # Superadmin allowed
        self.client.force_login(admin)
        response = self.client.get(reverse('users_manage'))
        self.assertEqual(response.status_code, 200)

        # Viewer denied
        self.client.force_login(viewer)
        response = self.client.get(reverse('users_manage'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))
