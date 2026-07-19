from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from core.models import Device, AppConfig, Fingerprint, VisitorRecord, Comment, VisitorRecordStatus


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
        self.assertTrue(config.show_distance_on_failure)

    def test_singleton_constraint(self):
        AppConfig.objects.create()
        with self.assertRaises(ValidationError):
            config2 = AppConfig()
            config2.full_clean()
            config2.save()


class VisitorRecordStatusTests(TestCase):
    def test_status_choices(self):
        record = VisitorRecord.objects.create(
            request_id='req_status_001',
            timestamp=1234567890000,
            updated_at=1234567890000,
            status=VisitorRecordStatus.SUCCESS,
        )
        self.assertEqual(record.status, VisitorRecordStatus.SUCCESS)
        self.assertEqual(record.get_status_display(), '成功')

    def test_default_status_is_unknown_error(self):
        record = VisitorRecord.objects.create(
            request_id='req_status_002',
            timestamp=1234567890001,
            updated_at=1234567890001,
        )
        self.assertEqual(record.status, VisitorRecordStatus.UNKNOWN_ERROR)


class CommentModelTests(TestCase):
    def setUp(self):
        self.fingerprint = Fingerprint.objects.create(visitor_fingerprint='fp_test')
        self.record = VisitorRecord.objects.create(
            request_id='req_001',
            fingerprint=self.fingerprint,
            timestamp=1234567890000,
            updated_at=1234567890000,
            status=VisitorRecordStatus.SUCCESS,
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
            updated_at=1234567890000,
            status=VisitorRecordStatus.SUCCESS,
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
            updated_at=1234567890001,
            status=VisitorRecordStatus.DEVICE_TOO_FAR,
        )
        count = VisitorRecord.objects.filter(
            fingerprint=self.fingerprint,
            status=VisitorRecordStatus.SUCCESS,
        ).count()
        self.assertEqual(count, 1)


class HistoryApiSerializationTests(TestCase):
    def setUp(self):
        self.fingerprint = Fingerprint.objects.create(visitor_fingerprint='fp_history')
        self.record = VisitorRecord.objects.create(
            request_id='req_history_001',
            fingerprint=self.fingerprint,
            timestamp=1234567890000,
            updated_at=1234567890000,
            status=VisitorRecordStatus.DEVICE_TOO_FAR,
        )

    async def test_history_returns_status_field(self):
        from api.views import get_history
        from django.test import AsyncRequestFactory
        import json
        factory = AsyncRequestFactory()
        request = factory.get('/api/app/history/', {'module': 'tracking', 'last_updated_at': '0', 'limit': '100'})
        response = await get_history(request)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('records', data)
        self.assertIn('has_more', data)
        self.assertIn('max_updated_at', data)
        self.assertEqual(len(data['records']), 1)
        self.assertIn('Status', data['records'][0])
        self.assertNotIn('IsSuccess', data['records'][0])
        self.assertEqual(data['records'][0]['Status'], VisitorRecordStatus.DEVICE_TOO_FAR)


class VerifyVisitorClickTests(TestCase):
    def setUp(self):
        from django.test import AsyncRequestFactory
        self.factory = AsyncRequestFactory()

    @patch('api.views._get_online_device_id', return_value=None)
    async def test_device_offline_creates_record(self, mock_online):
        from api.views import verify_visitor_click
        from channels.db import database_sync_to_async
        import json
        request = self.factory.post(
            '/api/visitor/verify/',
            data=json.dumps({'latitude': 39.9, 'longitude': 116.4, 'fingerprint': 'fp_offline'}),
            content_type='application/json',
        )
        response = await verify_visitor_click(request)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.content)
        self.assertEqual(body['status'], 'fail')
        record = await database_sync_to_async(VisitorRecord.objects.first)()
        self.assertIsNotNone(record)
        self.assertEqual(record.status, VisitorRecordStatus.DEVICE_OFFLINE)
