"""
Shared mixins for REST API tests.
"""
from django.core.cache import cache

from openedx.core.djangoapps.catalog.cache import PROGRAM_CACHE_KEY_TPL, PROGRAMS_BY_ORGANIZATION_CACHE_KEY_TPL
from openedx.core.djangolib.testing.utils import CacheIsolationMixin


class ProgramCacheMixin(CacheIsolationMixin):
    """
    Mixin for using program cache in tests
    """
    ENABLED_CACHES = ['default']

    def set_program_in_catalog_cache(self, program_uuid, program):
        cache.set(PROGRAM_CACHE_KEY_TPL.format(uuid=program_uuid), program, None)

    def set_org_in_catalog_cache(self, organization, program_uuids):
        cache.set(
            PROGRAMS_BY_ORGANIZATION_CACHE_KEY_TPL.format(org_key=organization.short_name),
            program_uuids,
        )
