from __future__ import unicode_literals

import django
from django.test import TransactionTestCase


class TestSeedManifest(TransactionTestCase):
    """Tests functions in the manifest module."""

    def setUp(self):
        django.setup()
