from django.db import models
from django.contrib.auth.models import AbstractUser

class Web3User(AbstractUser):
    """User model that includes an ethereum address field"""
    ethereum_address = models.CharField(max_length=42, unique=True, null=True, blank=True)
    nonce = models.CharField(max_length=32, blank=True)
    
    # Add related_name attributes to avoid clashes
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='web3user_set',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='web3user_set',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions',
    )

    def __str__(self):
        return self.username or self.ethereum_address