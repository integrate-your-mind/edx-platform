"""
Fragment for rendering the course's sock and associated toggle button.
"""

import json

from django.template.loader import render_to_string
from web_fragments.fragment import Fragment

from course_modes.models import CourseMode
from lms.djangoapps.courseware.utils import verified_upgrade_deadline_link, verified_upgrade_link_is_valid
from openedx.core.djangoapps.plugin_api.views import EdxFragmentView
from openedx.core.djangoapps.verified_track_content.partition_scheme import EnrollmentTrackPartitionScheme
from openedx.features.discounts.utils import format_strikeout_price
from student.models import CourseEnrollment
from xmodule.partitions.partitions import ENROLLMENT_TRACK_PARTITION_ID
from xmodule.partitions.partitions_service import PartitionService


class CourseSockFragmentView(EdxFragmentView):
    """
    A fragment to provide extra functionality in a dropdown sock.
    """
    def render_to_fragment(self, request, course, **kwargs):
        """
        Render the course's sock fragment.
        """
        context = self.get_verification_context(request, course)
        html = render_to_string('course_experience/course-sock-fragment.html', context)
        return Fragment(html)

    @staticmethod
    def get_verification_context(request, course):
        partition_service = PartitionService(course.id)
        enrollment_track_partition = partition_service.get_user_partition(ENROLLMENT_TRACK_PARTITION_ID)
        group = EnrollmentTrackPartitionScheme.get_group_for_user(course.id, request.user, enrollment_track_partition)
        current_mode = None
        if group:
            current_mode = CourseMode.ALL_MODES[group.id-1]
        enrollment = CourseEnrollment.get_enrollment(request.user, course.id)
        upgradable_mode = not current_mode or current_mode in CourseMode.UPSELL_TO_VERIFIED_MODES
        show_course_sock = upgradable_mode and verified_upgrade_link_is_valid(enrollment)
        if show_course_sock:
            upgrade_url = verified_upgrade_deadline_link(request.user, course=course)
            course_price, _ = format_strikeout_price(request.user, course)
        else:
            upgrade_url = ''
            course_price = ''

        context = {
            'show_course_sock': show_course_sock,
            'course_price': course_price,
            'course_id': course.id,
            'upgrade_url': upgrade_url,
        }

        return context
