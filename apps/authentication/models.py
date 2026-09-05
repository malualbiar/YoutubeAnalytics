from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = 'SUPER_ADMIN', 'Super Admin'
        MANAGER = 'MANAGER', 'Manager'
        VIEWER = 'VIEWER', 'Viewer'

    email = models.EmailField(unique=True, help_text="User's unique email address")
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.VIEWER,
        help_text="Role-based access level"
    )
    profile_image = models.ImageField(upload_to='profiles/', null=True, blank=True)
    organization = models.CharField(max_length=255, blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')

    # Make email required for login
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        ordering = ['-date_joined']
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN or self.is_superuser

    @property
    def is_manager_or_above(self):
        return self.role in [self.Role.SUPER_ADMIN, self.Role.MANAGER] or self.is_superuser

    @property
    def can_manage_artists(self):
        return self.is_manager_or_above

    @property
    def can_manage_channels(self):
        return self.is_super_admin

    @property
    def can_edit_settings(self):
        return self.is_super_admin
