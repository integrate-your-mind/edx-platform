"""
Tests for utility functions of V1 program enrollments REST API.
"""
from datetime import timedelta
import ddt
from django.utils import timezone
from freezegun import freeze_time
from opaque_keys.edx.keys import CourseKey

from lms.djangoapps.program_enrollments.tests.factories import ProgramCourseEnrollmentFactory, ProgramEnrollmentFactory
from openedx.core.djangoapps.catalog.tests.factories import (
    CourseFactory,
    CourseRunFactory,
    OrganizationFactory,
    ProgramFactory
)
from openedx.core.djangoapps.content.course_overviews.tests.factories import CourseOverviewFactory
from student.tests.factories import CourseEnrollmentFactory, UserFactory
from xmodule.modulestore.tests.django_utils import SharedModuleStoreTestCase
from course_modes.models import CourseMode

from ..utils import get_program_course_run_overviews
from .mixins import ProgramCacheMixin


class GetProgramCourseRunOverviewTests(ProgramCacheMixin, SharedModuleStoreTestCase):
    """
    Tests for `get_program_course_run_overviews`.
    """
    @classmethod
    def setUpClass(cls):
        super(GetProgramCourseRunOverviewTests, cls).setUpClass()

        cls.program_uuid = '00000000-1111-2222-3333-444444444444'
        cls.curriculum_uuid = 'aaaaaaaa-1111-2222-3333-444444444444'
        cls.other_curriculum_uuid = 'bbbbbbbb-1111-2222-3333-444444444444'

        cls.course_id = CourseKey.from_string('course-v1:edX+ToyX+Toy_Course')
        cls.course_run = CourseRunFactory.create(key=str(cls.course_id))
        cls.course = CourseFactory.create(course_runs=[cls.course_run])

        cls.password = 'password'
        cls.student = UserFactory.create(username='student', password=cls.password)

        # only freeze time when defining these values and not on the whole test case
        # as test_multiple_enrollments_all_enrolled relies on actual differences in modified datetimes
        with freeze_time('2019-01-01'):
            cls.yesterday = timezone.now() - timedelta(1)
            cls.tomorrow = timezone.now() + timedelta(1)

        cls.relative_certificate_download_url = '/download-the-certificates'
        cls.absolute_certificate_download_url = 'http://www.certificates.com/'

    def setUp(self):
        super(GetProgramCourseRunOverviewTests, self).setUp()

        # create program enrollment
        self.program_enrollment = ProgramEnrollmentFactory.create(
            program_uuid=self.program_uuid,
            curriculum_uuid=self.curriculum_uuid,
            user=self.student,
        )

        # create course overview
        self.course_overview = CourseOverviewFactory.create(
            id=self.course_id,
            start=self.yesterday,
            end=self.tomorrow,
        )

        # create course enrollment
        self.course_enrollment = CourseEnrollmentFactory.create(
            course=self.course_overview,
            user=self.student,
            mode=CourseMode.MASTERS,
        )

        # create program course enrollment
        self.program_course_enrollment = ProgramCourseEnrollmentFactory.create(
            program_enrollment=self.program_enrollment,
            course_enrollment=self.course_enrollment,
            course_key=self.course_id,
            status='active',
        )

        # create program
        catalog_org = OrganizationFactory(key='organization_key')
        self.program = ProgramFactory(
            uuid=self.program_uuid,
            authoring_organizations=[catalog_org],
        )
        self.program['curricula'][0]['courses'].append(self.course)
        self.set_program_in_catalog_cache(self.program_uuid, self.program)

    def _add_new_course_to_program(self, course_run_key, program):
        """
        Helper method to create another course, an overview for it,
        add it to the program, and re-load the cache.
        """
        other_course_run = CourseRunFactory.create(key=str(course_run_key))
        other_course = CourseFactory.create(course_runs=[other_course_run])
        program['courses'].append(other_course)
        self.set_program_in_catalog_cache(program['uuid'], program)
        CourseOverviewFactory.create(
            id=course_run_key,
            start=self.yesterday,
        )

    """
    @ddt.data(False, True)
    def test_multiple_enrollments_all_enrolled(self, other_enrollment_active):
        other_course_key = CourseKey.from_string('course-v1:edX+ToyX+Other_Course')
        self._add_new_course_to_program(other_course_key, self.program)

        # add a second course enrollment, which doesn't need a ProgramCourseEnrollment
        # to be returned.
        other_enrollment = CourseEnrollmentFactory.create(
            course_id=other_course_key,
            user=self.student,
            mode=CourseMode.VERIFIED,
        )
        if not other_enrollment_active:
            other_enrollment.deactivate()

        results = get_program_course_run_overviews
        actual_course_run_ids = {run['course_run_id'] for run in response.data['course_runs']}
        expected_course_run_ids = {text_type(self.course_id)}
        if other_enrollment_active:
            expected_course_run_ids.add(text_type(other_course_key))
        self.assertEqual(expected_course_run_ids, actual_course_run_ids)
    """

    def test_stuff(self):
        _ = get_program_course_run_overviews
