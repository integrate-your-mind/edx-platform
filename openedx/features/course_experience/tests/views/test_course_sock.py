"""
Tests for course verification sock
"""


import json
import mock
import six

import ddt
from django.urls import reverse

from course_modes.models import CourseMode
from lms.djangoapps.commerce.models import CommerceConfiguration
from openedx.core.djangoapps.waffle_utils.testutils import override_waffle_flag
from openedx.core.djangolib.markup import HTML
from openedx.features.course_experience import DISPLAY_COURSE_SOCK_FLAG
from student.roles import CourseStaffRole
from student.tests.factories import CourseEnrollmentFactory, UserFactory
from xmodule.partitions.partitions import ENROLLMENT_TRACK_PARTITION_ID
from xmodule.partitions.partitions_service import PartitionService
from xmodule.modulestore.tests.django_utils import SharedModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory

from .helpers import add_course_mode
from .test_course_home import course_home_url

TEST_PASSWORD = 'test'
TEST_VERIFICATION_SOCK_LOCATOR = '<div class="verification-sock"'


@ddt.ddt
class TestCourseSockView(SharedModuleStoreTestCase):
    """
    Tests for the course verification sock fragment view.
    """
    @classmethod
    def setUpClass(cls):
        super(TestCourseSockView, cls).setUpClass()

        # Create four courses
        cls.standard_course = CourseFactory.create()
        cls.verified_course = CourseFactory.create()
        cls.verified_course_update_expired = CourseFactory.create()
        cls.verified_course_already_enrolled = CourseFactory.create()

        # Assign each verifiable course an upgrade deadline
        add_course_mode(cls.verified_course, upgrade_deadline_expired=False)
        add_course_mode(cls.verified_course_update_expired, upgrade_deadline_expired=True)
        add_course_mode(cls.verified_course_already_enrolled, upgrade_deadline_expired=False)

    def setUp(self):
        super(TestCourseSockView, self).setUp()
        self.user = UserFactory.create()

        # Enroll the user in the four courses
        CourseEnrollmentFactory.create(user=self.user, course_id=self.standard_course.id)
        CourseEnrollmentFactory.create(user=self.user, course_id=self.verified_course.id)
        CourseEnrollmentFactory.create(user=self.user, course_id=self.verified_course_update_expired.id)
        CourseEnrollmentFactory.create(
            user=self.user, course_id=self.verified_course_already_enrolled.id, mode=CourseMode.VERIFIED
        )

        CommerceConfiguration.objects.create(enabled=True, checkout_on_ecommerce_service=True)

        # Log the user in
        self.client.login(username=self.user.username, password=TEST_PASSWORD)

    @override_waffle_flag(DISPLAY_COURSE_SOCK_FLAG, active=True)
    def test_standard_course(self):
        """
        Ensure that a course that cannot be verified does
        not have a visible verification sock.
        """
        response = self.client.get(course_home_url(self.standard_course))
        self.assert_verified_sock_is_not_visible(self.standard_course, response)

    @override_waffle_flag(DISPLAY_COURSE_SOCK_FLAG, active=True)
    def test_verified_course(self):
        """
        Ensure that a course that can be verified has a
        visible verification sock.
        """
        response = self.client.get(course_home_url(self.verified_course))
        self.assert_verified_sock_is_visible(self.verified_course, response)

    @override_waffle_flag(DISPLAY_COURSE_SOCK_FLAG, active=True)
    def test_verified_course_updated_expired(self):
        """
        Ensure that a course that has an expired upgrade
        date does not display the verification sock.
        """
        response = self.client.get(course_home_url(self.verified_course_update_expired))
        self.assert_verified_sock_is_not_visible(self.verified_course_update_expired, response)

    @override_waffle_flag(DISPLAY_COURSE_SOCK_FLAG, active=True)
    def test_verified_course_user_already_upgraded(self):
        """
        Ensure that a user that has already upgraded to a
        verified status cannot see the verification sock.
        """
        response = self.client.get(course_home_url(self.verified_course_already_enrolled))
        self.assert_verified_sock_is_not_visible(self.verified_course_already_enrolled, response)

    @override_waffle_flag(DISPLAY_COURSE_SOCK_FLAG, active=True)
    @mock.patch(
        'openedx.features.course_experience.views.course_sock.format_strikeout_price',
        mock.Mock(return_value=(HTML("<span>DISCOUNT_PRICE</span>"), True))
    )
    def test_upgrade_message_discount(self):
        response = self.client.get(course_home_url(self.verified_course))
        self.assertContains(response, "<span>DISCOUNT_PRICE</span>")

    def assert_verified_sock_is_visible(self, course, response):
        return self.assertContains(response, TEST_VERIFICATION_SOCK_LOCATOR, html=False)

    def assert_verified_sock_is_not_visible(self, course, response):
        return self.assertNotContains(response, TEST_VERIFICATION_SOCK_LOCATOR, html=False)


class TestCourseSockViewWithMasquerade(SharedModuleStoreTestCase):
    """
    Tests for the course verification sock fragment view while the user is being masqueraded.
    """
    @classmethod
    def setUpClass(cls):
        super(TestCourseSockViewWithMasquerade, cls).setUpClass()

        # Create four courses
        cls.verified_course = CourseFactory.create()
        cls.masters_course = CourseFactory.create()
        # Assign each verifiable course an upgrade deadline
        add_course_mode(cls.verified_course, upgrade_deadline_expired=False)
        add_course_mode(cls.masters_course, upgrade_deadline_expired=False)
        add_course_mode(cls.masters_course, mode_slug='masters', mode_display_name='Masters')

    def setUp(self):
        super(TestCourseSockViewWithMasquerade, self).setUp()
        self.course_staff = UserFactory.create()
        CourseStaffRole(self.verified_course.id).add_users(self.course_staff)
        CourseStaffRole(self.masters_course.id).add_users(self.course_staff)


        # Enroll the user in the four courses
        CourseEnrollmentFactory.create(user=self.course_staff, course_id=self.verified_course.id)
        CourseEnrollmentFactory.create(user=self.course_staff, course_id=self.masters_course.id)
        
        CommerceConfiguration.objects.create(enabled=True, checkout_on_ecommerce_service=True)
        # Log the user in
        self.client.login(username=self.course_staff.username, password=TEST_PASSWORD)

    def get_group_id_by_course_mode_name(self, course_id, mode_name):
        partition_service = PartitionService(course_id)
        enrollment_track_user_partition = partition_service.get_user_partition(ENROLLMENT_TRACK_PARTITION_ID)
        for group in enrollment_track_user_partition.groups:
            if group.name == mode_name:
                return group.id
        return None

    @override_waffle_flag(DISPLAY_COURSE_SOCK_FLAG, active=True)
    def test_masquerade_as_student(self):
        # Elevate the staff user to be student
        self.update_masquerade(role='student', course=self.verified_course)
        response = self.client.get(course_home_url(self.verified_course))
        self.assertContains(response, TEST_VERIFICATION_SOCK_LOCATOR, html=False)

    @override_waffle_flag(DISPLAY_COURSE_SOCK_FLAG, active=True)
    def test_masquerade_as_verified_student(self):
        user_group_id = self.get_group_id_by_course_mode_name(
            self.verified_course.id,
            'Verified Certificates'
        )
        self.update_masquerade(role='student', course=self.verified_course, group_id=user_group_id)
        response = self.client.get(course_home_url(self.verified_course))
        self.assertNotContains(response, TEST_VERIFICATION_SOCK_LOCATOR, html=False)

    @override_waffle_flag(DISPLAY_COURSE_SOCK_FLAG, active=True)
    def test_masquerade_as_masters_student(self):
        user_group_id = self.get_group_id_by_course_mode_name(
            self.masters_course.id,
            'Masters'
        )
        self.update_masquerade(role='student', course=self.masters_course, group_id=user_group_id)
        response = self.client.get(course_home_url(self.verified_course))
        self.assertNotContains(response, TEST_VERIFICATION_SOCK_LOCATOR, html=False)

    def update_masquerade(self, role, course, username=None, group_id=None):
        """
        Toggle masquerade state.
        """
        masquerade_url = reverse(
            'masquerade_update',
            kwargs={
                'course_key_string': six.text_type(course.id),
            }
        )
        response = self.client.post(
            masquerade_url,
            json.dumps({
                "role": role,
                "group_id": group_id,
                "user_name": username,
                "user_partition_id": ENROLLMENT_TRACK_PARTITION_ID
            }),
            "application/json"
        )
        self.assertEqual(response.status_code, 200)
        return response
