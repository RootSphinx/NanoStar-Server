from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from core.models import Device, AppConfig, Fingerprint, VisitorRecord, Comment


class FingerprintModelTests(TestCase):
    def test_fingerprint_creation(self):
        fp = Fingerprint.objects.create(visitor_fingerprint='abc123')
        self.assertEqual(fp.visitor_fingerprint, 'abc123')
        self.assertIsNotNone(fp.first_seen)
        self.assertIsNotNone(fp.last_seen)


class AppConfigTests(TestCase):
    def test_default_values(self):
        config = AppConfig.objects.create()
        self.assertEqual(config.visit_cooldown_minutes, 30)
        self.assertEqual(config.max_comments_per_record, 3)
        self.assertTrue(config.show_past_comments)


class CommentModelTests(TestCase):
    def setUp(self):
        self.fingerprint = Fingerprint.objects.create(visitor_fingerprint='fp_test')
        self.record = VisitorRecord.objects.create(
            request_id='req_001',
            fingerprint=self.fingerprint,
            timestamp=1234567890000,
            is_success=True,
        )

    def test_comment_creation(self):
        comment = Comment.objects.create(
            visitor_record=self.record,
            fingerprint=self.fingerprint,
            content='Hello',
            timestamp=1234567890001,
        )
        self.assertEqual(comment.content, 'Hello')
        self.assertEqual(self.record.comments.count(), 1)

    def test_comment_ordering(self):
        Comment.objects.create(
            visitor_record=self.record,
            fingerprint=self.fingerprint,
            content='First',
            timestamp=1000,
        )
        Comment.objects.create(
            visitor_record=self.record,
            fingerprint=self.fingerprint,
            content='Second',
            timestamp=2000,
        )
        comments = list(self.record.comments.order_by('created_at'))
        self.assertEqual(comments[0].content, 'First')
        self.assertEqual(comments[1].content, 'Second')


class VisitorRecordQueryTests(TestCase):
    def setUp(self):
        self.fingerprint = Fingerprint.objects.create(visitor_fingerprint='fp_test')
        self.record = VisitorRecord.objects.create(
            request_id='req_002',
            fingerprint=self.fingerprint,
            timestamp=1234567890000,
            is_success=True,
        )

    def test_latest_record_within_cooldown(self):
        latest = VisitorRecord.objects.filter(
            fingerprint=self.fingerprint,
            created_at__gte=timezone.now() - timedelta(minutes=30)
        ).order_by('-created_at').first()
        self.assertEqual(latest, self.record)

    def test_successful_visit_count(self):
        VisitorRecord.objects.create(
            request_id='req_003',
            fingerprint=self.fingerprint,
            timestamp=1234567890001,
            is_success=False,
        )
        count = VisitorRecord.objects.filter(fingerprint=self.fingerprint, is_success=True).count()
        self.assertEqual(count, 1)
