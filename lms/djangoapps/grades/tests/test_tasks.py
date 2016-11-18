"""
Tests for the functionality and infrastructure of grades tasks.
"""

from collections import OrderedDict
from contextlib import contextmanager
import ddt
from django.conf import settings
from django.db.utils import IntegrityError
from mock import patch
from unittest import skip

from student.models import anonymous_id_for_user
from student.tests.factories import UserFactory
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory, check_mongo_calls

from lms.djangoapps.grades.config.models import PersistentGradesEnabledFlag
from lms.djangoapps.grades.signals.signals import PROBLEM_SCORE_CHANGED
from lms.djangoapps.grades.tasks import recalculate_subsection_grade


@patch.dict(settings.FEATURES, {'PERSISTENT_GRADES_ENABLED_FOR_ALL_TESTS': False})
@ddt.ddt
class RecalculateSubsectionGradeTest(ModuleStoreTestCase):
    """
    Ensures that the recalculate subsection grade task functions as expected when run.
    """
    def setUp(self):
        super(RecalculateSubsectionGradeTest, self).setUp()
        self.user = UserFactory()
        PersistentGradesEnabledFlag.objects.create(enabled_for_all_courses=True, enabled=True)

    def set_up_course(self, enable_subsection_grades=True):
        """
        Configures the course for this test.
        """
        # pylint: disable=attribute-defined-outside-init,no-member
        self.course = CourseFactory.create(
            org='edx',
            name='course',
            run='run',
        )
        if not enable_subsection_grades:
            PersistentGradesEnabledFlag.objects.create(enabled=False)

        self.chapter = ItemFactory.create(parent=self.course, category="chapter", display_name="Chapter")
        self.sequential = ItemFactory.create(parent=self.chapter, category='sequential', display_name="Open Sequential")
        self.problem = ItemFactory.create(parent=self.sequential, category='problem', display_name='problem')

        self.problem_score_changed_kwargs = OrderedDict([
            ('points_earned', 1.0),
            ('points_possible', 2.0),
            ('user_id', self.user.id),
            ('course_id', unicode(self.course.id)),
            ('usage_id', unicode(self.problem.location)),
            ('only_if_higher', None),
        ])

        self.recalculate_subsection_grade_kwargs = OrderedDict([
            ('user_id', self.user.id),
            ('course_id', unicode(self.course.id)),
            ('usage_id', unicode(self.problem.location)),
            ('only_if_higher', None),
            ('raw_earned', 1.0),
            ('raw_possible', 2.0),
            ('score_deleted', False),
        ])

        # this call caches the anonymous id on the user object, saving 4 queries in all happy path tests
        _ = anonymous_id_for_user(self.user, self.course.id)
        # pylint: enable=attribute-defined-outside-init,no-member

    @contextmanager
    def mock_get_score(self, score=(1.0, 2.0)):
        """
        Mocks the scores needed by the SCORE_PUBLISHED signal
        handler. By default, sets the returned score to 1/2.
        """
        with patch("lms.djangoapps.grades.tasks.get_score", return_value=score):
            yield

    def test_problem_score_changed_queues_task(self):
        """
        Ensures that the PROBLEM_SCORE_CHANGED signal enqueues the correct task.
        """
        self.set_up_course()
        send_args = self.problem_score_changed_kwargs
        with self.mock_get_score() and patch(
            'lms.djangoapps.grades.tasks.recalculate_subsection_grade.apply_async',
            return_value=None
        ) as mock_task_apply:
            PROBLEM_SCORE_CHANGED.send(sender=None, **send_args)
            mock_task_apply.assert_called_once_with(kwargs=self.recalculate_subsection_grade_kwargs)

    @patch('lms.djangoapps.grades.signals.signals.SUBSECTION_SCORE_CHANGED.send')
    def test_subsection_update_triggers_course_update(self, mock_course_signal):
        """
        Ensures that the subsection update operation also updates the course grade.
        """
        self.set_up_course()
        self._apply_recalculate_subsection_grade()
        self.assertTrue(mock_course_signal.called)

    @ddt.data(
        (ModuleStoreEnum.Type.mongo, 1),
        (ModuleStoreEnum.Type.split, 0),
    )
    @ddt.unpack
    def test_subsection_grade_updated(self, default_store, added_queries):
        with self.store.default_store(default_store):
            self.set_up_course()
            self.assertTrue(PersistentGradesEnabledFlag.feature_enabled(self.course.id))
            with check_mongo_calls(2) and self.assertNumQueries(20 + added_queries):
                self._apply_recalculate_subsection_grade()

    def test_single_call_to_create_block_structure(self):
        self.set_up_course()
        self.assertTrue(PersistentGradesEnabledFlag.feature_enabled(self.course.id))
        with patch(
            'openedx.core.lib.block_structure.factory.BlockStructureFactory.create_from_cache',
            return_value=None,
        ) as mock_block_structure_create:
            self._apply_recalculate_subsection_grade()
            self.assertEquals(mock_block_structure_create.call_count, 1)

    @ddt.data(
        (ModuleStoreEnum.Type.mongo, 1),
        (ModuleStoreEnum.Type.split, 0),
    )
    @ddt.unpack
    def test_query_count_does_not_change_with_more_problems(self, default_store, added_queries):
        with self.store.default_store(default_store):
            self.set_up_course()
            self.assertTrue(PersistentGradesEnabledFlag.feature_enabled(self.course.id))
            ItemFactory.create(parent=self.sequential, category='problem', display_name='problem2')
            ItemFactory.create(parent=self.sequential, category='problem', display_name='problem3')
            with check_mongo_calls(2) and self.assertNumQueries(20 + added_queries):
                self._apply_recalculate_subsection_grade()

    @ddt.data(ModuleStoreEnum.Type.mongo, ModuleStoreEnum.Type.split)
    def test_subsection_grades_not_enabled_on_course(self, default_store):
        with self.store.default_store(default_store):
            self.set_up_course(enable_subsection_grades=False)
            self.assertFalse(PersistentGradesEnabledFlag.feature_enabled(self.course.id))
            with check_mongo_calls(2) and self.assertNumQueries(0):
                self._apply_recalculate_subsection_grade()

    @skip("Pending completion of TNL-5089")
    @ddt.data(
        (ModuleStoreEnum.Type.mongo, True),
        (ModuleStoreEnum.Type.split, True),
        (ModuleStoreEnum.Type.mongo, False),
        (ModuleStoreEnum.Type.split, False),
    )
    @ddt.unpack
    def test_query_counts_with_feature_flag(self, default_store, feature_flag):
        PersistentGradesEnabledFlag.objects.create(enabled=feature_flag)
        with self.store.default_store(default_store):
            self.set_up_course()
            with check_mongo_calls(0) and self.assertNumQueries(3 if feature_flag else 2):
                recalculate_subsection_grade.apply(kwargs=self.recalculate_subsection_grade_kwargs)

    @patch('lms.djangoapps.grades.tasks.recalculate_subsection_grade.retry')
    @patch('lms.djangoapps.grades.new.subsection_grade.SubsectionGradeFactory.update')
    def test_retry_subsection_update_on_integrity_error(self, mock_update, mock_retry):
        """
        Ensures that tasks will be retried if IntegrityErrors are encountered.
        """
        self.set_up_course()
        mock_update.side_effect = IntegrityError("WHAMMY")
        self._apply_recalculate_subsection_grade()
        self._assert_retry_called(mock_retry)

    @patch('lms.djangoapps.grades.tasks.recalculate_subsection_grade.retry')
    def test_retry_subsection_grade_on_update_not_complete(self, mock_retry):
        self.set_up_course()
        self._apply_recalculate_subsection_grade(mock_score=(0.5, 3.0))
        self._assert_retry_called(mock_retry)

    @patch('lms.djangoapps.grades.tasks.recalculate_subsection_grade.retry')
    def test_retry_subsection_grade_on_no_score(self, mock_retry):
        self.set_up_course()
        self._apply_recalculate_subsection_grade(mock_score=None)
        self._assert_retry_called(mock_retry)

    @patch('lms.djangoapps.grades.signals.signals.SUBSECTION_SCORE_CHANGED.send')
    @patch('lms.djangoapps.grades.new.subsection_grade.SubsectionGradeFactory.update')
    def test_retry_first_time_only(self, mock_update, mock_course_signal):
        """
        Ensures that a task retry completes after a one-time failure.
        """
        self.set_up_course()
        mock_update.side_effect = [IntegrityError("WHAMMY"), None]
        self._apply_recalculate_subsection_grade()
        self.assertEquals(mock_course_signal.call_count, 1)

    def _apply_recalculate_subsection_grade(self, mock_score=(1.0, 2.0)):
        """
        Calls the recalculate_subsection_grade task with necessary
        mocking in place.
        """
        with self.mock_get_score(mock_score):
            recalculate_subsection_grade.apply(kwargs=self.recalculate_subsection_grade_kwargs)

    def _assert_retry_called(self, mock_retry):
        """
        Verifies the task was retried and with the correct
        number of arguments.
        """
        self.assertTrue(mock_retry.called)
        self.assertEquals(len(mock_retry.call_args[1]['kwargs']), len(self.recalculate_subsection_grade_kwargs))
