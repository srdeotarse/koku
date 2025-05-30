#
# Copyright 2021 Red Hat Inc.
# SPDX-License-Identifier: Apache-2.0
#
"""Tests the AWSProvider implementation for the Koku interface."""
import logging
from unittest.mock import Mock
from unittest.mock import patch
from uuid import uuid4

from botocore.exceptions import ClientError
from django.test import TestCase
from django.utils.translation import ugettext as _
from faker import Faker
from rest_framework.exceptions import ValidationError

from providers.aws.provider import _check_cost_report_access
from providers.aws.provider import _check_s3_access
from providers.aws.provider import _get_sts_access
from providers.aws.provider import AWSProvider
from providers.aws.provider import error_obj

FAKE = Faker()


def _mock_boto3_exception():
    """Raise boto3 exception for testing."""
    raise ClientError(operation_name="", error_response={})


def _mock_boto3_kwargs_exception(*args, **kwargs):
    """Raise boto3 exception for testing."""
    raise ClientError(operation_name="", error_response={})


class AWSProviderTestCase(TestCase):
    """Parent Class for AWSProvider test cases."""

    def test_get_name(self):
        """Get name of provider."""
        provider = AWSProvider()
        self.assertEqual(provider.name(), "AWS")

    def test_error_obj(self):
        """Test the error_obj method."""
        test_key = "tkey"
        test_message = "tmessage"
        expected = {test_key: [_(test_message)]}
        error = error_obj(test_key, test_message)
        self.assertEqual(error, expected)

    @patch("providers.aws.provider.boto3.client")
    def test_get_sts_access(self, mock_boto3_client):
        """Test _get_sts_access success."""
        expected_access_key = FAKE.md5()
        expected_secret_access_key = FAKE.md5()
        expected_session_token = FAKE.md5()

        assume_role = {
            "Credentials": {
                "AccessKeyId": expected_access_key,
                "SecretAccessKey": expected_secret_access_key,
                "SessionToken": expected_session_token,
            }
        }
        sts_client = Mock()
        sts_client.assume_role.return_value = assume_role
        mock_boto3_client.return_value = sts_client

        iam_arn = "arn:aws:s3:::my_s3_bucket"
        credentials = {"role_arn": iam_arn}
        aws_credentials = _get_sts_access(credentials)
        sts_client.assume_role.assert_called_with(RoleArn=iam_arn, RoleSessionName="AccountCreationSession")
        self.assertEqual(aws_credentials.get("aws_access_key_id"), expected_access_key)
        self.assertEqual(aws_credentials.get("aws_secret_access_key"), expected_secret_access_key)
        self.assertEqual(aws_credentials.get("aws_session_token"), expected_session_token)

    @patch("providers.aws.provider.boto3.client")
    def test_get_sts_access_with_external_id(self, mock_boto3_client):
        """Test _get_sts_access success."""
        expected_access_key = FAKE.md5()
        expected_secret_access_key = FAKE.md5()
        expected_session_token = FAKE.md5()

        assume_role = {
            "Credentials": {
                "AccessKeyId": expected_access_key,
                "SecretAccessKey": expected_secret_access_key,
                "SessionToken": expected_session_token,
            }
        }
        sts_client = Mock()
        sts_client.assume_role.return_value = assume_role
        mock_boto3_client.return_value = sts_client

        iam_arn = "arn:aws:s3:::my_s3_bucket"
        external_id = str(uuid4())
        credentials = {"role_arn": iam_arn, "external_id": external_id}
        aws_credentials = _get_sts_access(credentials)
        sts_client.assume_role.assert_called_with(
            RoleArn=iam_arn, RoleSessionName="AccountCreationSession", ExternalId=external_id
        )
        self.assertEqual(aws_credentials.get("aws_access_key_id"), expected_access_key)
        self.assertEqual(aws_credentials.get("aws_secret_access_key"), expected_secret_access_key)
        self.assertEqual(aws_credentials.get("aws_session_token"), expected_session_token)

    def test_get_sts_access_invalid_arn(self):
        """Test _get_sts_access with invalid arn."""
        iam_arn = "random_resource_name"
        credentials = {"role_arn": iam_arn}
        aws_credentials = _get_sts_access(credentials)
        self.assertIsNone(aws_credentials.get("aws_access_key_id"))
        self.assertIsNone(aws_credentials.get("aws_secret_access_key"))
        self.assertIsNone(aws_credentials.get("aws_session_token"))

    @patch("providers.aws.provider.boto3.client")
    def test_get_sts_access_fail(self, mock_boto3_client):
        """Test _get_sts_access fail."""
        logging.disable(logging.NOTSET)
        sts_client = Mock()
        sts_client.assume_role.side_effect = _mock_boto3_kwargs_exception
        mock_boto3_client.return_value = sts_client
        iam_arn = "arn:aws:s3:::my_s3_bucket"
        credentials = {"role_arn": iam_arn}
        with self.assertLogs(level=logging.CRITICAL):
            aws_credentials = _get_sts_access(credentials)
            self.assertIn("aws_access_key_id", aws_credentials)
            self.assertIn("aws_secret_access_key", aws_credentials)
            self.assertIn("aws_session_token", aws_credentials)
            self.assertIsNone(aws_credentials.get("aws_access_key_id"))
            self.assertIsNone(aws_credentials.get("aws_secret_access_key"))
            self.assertIsNone(aws_credentials.get("aws_session_token"))

    @patch("providers.aws.provider.boto3.client")
    def test_check_s3_access(self, mock_boto3_client):
        """Test _check_s3_access success."""
        s3_client = Mock()
        s3_client.head_bucket.return_value = True
        mock_boto3_client.return_value = s3_client
        s3_exists = _check_s3_access("bucket", {})
        self.assertTrue(s3_exists)

    @patch("providers.aws.provider.boto3.client")
    def test_check_s3_access_fail(self, mock_boto3_client):
        """Test _check_s3_access fail."""
        s3_client = Mock()
        s3_client.head_bucket.side_effect = _mock_boto3_kwargs_exception
        mock_boto3_client.return_value = s3_client
        s3_exists = _check_s3_access("bucket", {})
        self.assertFalse(s3_exists)

    @patch("providers.aws.provider.boto3.client", side_effect=AttributeError("Raised intentionally"))
    def test_check_s3_access_default_region(self, mock_boto3_client):
        """Test that the default region value is used"""
        expected_region_name = "us-east-1"
        with self.assertRaisesRegex(AttributeError, "Raised intentionally"):
            _check_s3_access("bucket", {})

        self.assertIn("region_name", mock_boto3_client.call_args.kwargs)
        self.assertEqual(expected_region_name, mock_boto3_client.call_args.kwargs.get("region_name"))

    @patch("providers.aws.provider.boto3.client", side_effect=AttributeError("Raised intentionally"))
    def test_check_s3_access_with_region(self, mock_boto3_client):
        """Test that the provided region value is used"""
        expected_region_name = "eu-south-2"
        with self.assertRaisesRegex(AttributeError, "Raised intentionally"):
            _check_s3_access("bucket", {}, region_name=expected_region_name)

        self.assertIn("region_name", mock_boto3_client.call_args.kwargs)
        self.assertEqual(expected_region_name, mock_boto3_client.call_args.kwargs.get("region_name"))

    @patch("providers.aws.provider.boto3.client")
    def test_check_cost_report_access(self, mock_boto3_client):
        """Test _check_cost_report_access success."""
        s3_client = Mock()
        s3_client.describe_report_definitions.return_value = {
            "ReportDefinitions": [
                {
                    "ReportName": FAKE.word(),
                    "TimeUnit": "HOURLY",
                    "Format": "textORcsv",
                    "Compression": "GZIP",
                    "AdditionalSchemaElements": ["RESOURCES"],
                    "S3Bucket": FAKE.word(),
                    "S3Prefix": FAKE.word(),
                    "S3Region": "us-east-1",
                    "AdditionalArtifacts": [],
                    "RefreshClosedReports": True,
                    "ReportVersioning": "CREATE_NEW_REPORT",
                }
            ],
            "ResponseMetadata": {
                "RequestId": FAKE.uuid4(),
                "HTTPStatusCode": 200,
                "HTTPHeaders": {
                    "x-amzn-requestid": FAKE.uuid4(),
                    "content-type": "application/x-amz-json-1.1",
                    "content-length": "1234",
                    "date": FAKE.date_time(),
                },
                "RetryAttempts": 0,
            },
        }
        mock_boto3_client.return_value = s3_client
        try:
            _check_cost_report_access(
                FAKE.word(),
                {
                    "aws_access_key_id": FAKE.md5(),
                    "aws_secret_access_key": FAKE.md5(),
                    "aws_session_token": FAKE.md5(),
                },
            )
        except Exception as exc:
            self.fail(exc)

    @patch("providers.aws.provider.boto3.client")
    def test_check_cost_report_access_bucket_not_configured_error(self, mock_boto3_client):
        """Test _check_cost_report_access fails when bucket has no report definition."""
        test_bucket = "test-bucket"
        other_bucket = "not-test-bucket"

        s3_client = Mock()
        s3_client.describe_report_definitions.return_value = {
            "ReportDefinitions": [
                {
                    "ReportName": FAKE.word(),
                    "Compression": "Parquet",
                    "AdditionalSchemaElements": ["RESOURCES"],
                    "S3Bucket": test_bucket,
                    "S3Region": "us-east-1",
                }
            ]
        }
        mock_boto3_client.return_value = s3_client
        with self.assertRaises(ValidationError):
            _check_cost_report_access(
                FAKE.word(),
                {
                    "aws_access_key_id": FAKE.md5(),
                    "aws_secret_access_key": FAKE.md5(),
                    "aws_session_token": FAKE.md5(),
                },
                bucket=other_bucket,
            )

    @patch("providers.aws.provider.boto3.client")
    def test_check_cost_report_access_compression_error(self, mock_boto3_client):
        """Test _check_cost_report_access errors with invalid compression."""
        test_bucket = "test-bucket"
        s3_client = Mock()
        s3_client.describe_report_definitions.return_value = {
            "ReportDefinitions": [
                {
                    "ReportName": FAKE.word(),
                    "Compression": "Fake",
                    "AdditionalSchemaElements": ["RESOURCES"],
                    "S3Bucket": test_bucket,
                    "S3Region": "us-east-1",
                }
            ]
        }
        mock_boto3_client.return_value = s3_client
        with self.assertRaises(ValidationError):
            _check_cost_report_access(
                FAKE.word(),
                {
                    "aws_access_key_id": FAKE.md5(),
                    "aws_secret_access_key": FAKE.md5(),
                    "aws_session_token": FAKE.md5(),
                },
                bucket=test_bucket,
            )

    @patch("providers.aws.provider.get_cur_report_definitions")
    @patch("providers.aws.provider.boto3.client")
    def test_check_cost_report_access_fail(self, mock_boto3_client, mock_check):
        """Test _check_cost_report_access fail."""
        s3_client = Mock()
        mock_boto3_client.return_value = s3_client
        mock_check.side_effect = _mock_boto3_kwargs_exception
        with self.assertRaises(ValidationError):
            _check_cost_report_access(
                FAKE.word(),
                {
                    "aws_access_key_id": FAKE.md5(),
                    "aws_secret_access_key": FAKE.md5(),
                    "aws_session_token": FAKE.md5(),
                },
                bucket="wrongbucket",
            )

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(
            aws_access_key_id=FAKE.md5(), aws_secret_access_key=FAKE.md5(), aws_session_token=FAKE.md5()
        ),
    )
    @patch("providers.aws.provider._check_s3_access", return_value=True)
    @patch("providers.aws.provider._check_cost_report_access", return_value=True)
    def test_cost_usage_source_is_reachable(
        self, mock_check_cost_report_access, mock_check_s3_access, mock_get_sts_access
    ):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        try:
            credentials = {"role_arn": "arn:aws:s3:::my_s3_bucket"}
            data_source = {"bucket": "bucket_name"}
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
        except Exception:
            self.fail("Unexpected Error")

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(
            aws_access_key_id=FAKE.md5(), aws_secret_access_key=FAKE.md5(), aws_session_token=FAKE.md5()
        ),
    )
    @patch("providers.aws.provider._check_s3_access", return_value=True)
    @patch("providers.aws.provider._check_cost_report_access")
    def test_cost_usage_source_is_reachable_with_region(
        self, mock_check_cost_report_access, mock_check_s3_access, mock_get_sts_access
    ):
        """Verify that the bucket region is used when available"""
        provider_interface = AWSProvider()
        credentials = {"role_arn": "arn:aws:s3:::my_s3_bucket"}
        data_source = {"bucket": "bucket_name", "bucket_region": "me-south-1"}
        provider_interface.cost_usage_source_is_reachable(credentials, data_source)

        self.assertIn("region_name", mock_check_s3_access.call_args.kwargs)
        self.assertIn("region_name", mock_get_sts_access.call_args.kwargs)

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(
            aws_access_key_id=FAKE.md5(), aws_secret_access_key=FAKE.md5(), aws_session_token=FAKE.md5()
        ),
    )
    @patch("providers.aws.provider._check_s3_access", return_value=True)
    @patch("providers.aws.provider._check_cost_report_access")
    def test_cost_usage_source_is_call_no_region(
        self, mock_check_cost_report_access, mock_check_s3_access, mock_get_sts_access
    ):
        """Verify that the bucket region is not passed in when not availeble in the data source
        so that the default value in the function definiton is used."""
        provider_interface = AWSProvider()
        credentials = {"role_arn": "arn:aws:s3:::my_s3_bucket"}
        data_source = {"bucket": "bucket_name"}
        provider_interface.cost_usage_source_is_reachable(credentials, data_source)

        self.assertNotIn("region_name", mock_check_s3_access.call_args.kwargs)
        self.assertNotIn("region_name", mock_check_cost_report_access.call_args.kwargs)

    def test_cost_usage_source_is_reachable_no_arn(self):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            credentials = {"role_arn": None}
            data_source = {"bucket": "bucket_name"}
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)

    @patch("providers.aws.provider._check_cost_report_access", return_value=True)
    def test_storage_only_source_is_created(self, mock_check_cost_report_access):
        """Verify that a storage only sources is created."""
        provider_interface = AWSProvider()
        try:
            credentials = {"role_arn": "arn:aws:s3:::my_s3_bucket"}
            data_source = {"bucket": "bucket_name", "storage_only": True}
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
        except Exception:
            self.fail("Unexpected Error")

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(aws_access_key_id=None, aws_secret_access_key=None, aws_session_token=None),
    )
    def test_cost_usage_source_is_reachable_no_access(self, mock_get_sts_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            credentials = {"role_arn": "arn:aws:s3:::my_s3_bucket"}
            data_source = {"bucket": "bucket_name"}
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(
            aws_access_key_id=FAKE.md5(), aws_secret_access_key=FAKE.md5(), aws_session_token=FAKE.md5()
        ),
    )
    def test_cost_usage_source_is_reachable_no_bucket(self, mock_get_sts_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            credentials = {"role_arn": "arn:aws:s3:::my_s3_bucket"}
            data_source = {"bucket": None}
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(
            aws_access_key_id=FAKE.md5(), aws_secret_access_key=FAKE.md5(), aws_session_token=FAKE.md5()
        ),
    )
    @patch("providers.aws.provider._check_s3_access", return_value=False)
    def test_cost_usage_source_is_reachable_no_bucket_exists(self, mock_check_s3_access, mock_get_sts_access):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        with self.assertRaises(ValidationError):
            credentials = {"role_arn": "arn:aws:s3:::my_s3_bucket"}
            data_source = {"bucket": "bucket_name"}
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)

    @patch(
        "providers.aws.provider._get_sts_access",
        return_value=dict(
            aws_access_key_id=FAKE.md5(), aws_secret_access_key=FAKE.md5(), aws_session_token=FAKE.md5()
        ),
    )
    @patch("providers.aws.provider._check_s3_access", return_value=True)
    @patch("providers.aws.provider._check_cost_report_access", return_value=True)
    def test_cost_usage_source_is_reachable_no_topics(
        self, mock_check_cost_report_access, mock_check_s3_access, mock_get_sts_access
    ):
        """Verify that the cost usage source is authenticated and created."""
        provider_interface = AWSProvider()
        try:
            credentials = {"role_arn": "arn:aws:s3:::my_s3_bucket"}
            data_source = {"bucket": "bucket_name"}
            provider_interface.cost_usage_source_is_reachable(credentials, data_source)
        except Exception:
            self.fail("Unexpected Error")

    @patch("providers.aws.provider.boto3.client")
    def test_cur_has_resourceids(self, mock_boto3_client):
        """Test that a CUR with resource IDs succeeds."""
        bucket = FAKE.word()
        s3_client = Mock()
        s3_client.describe_report_definitions.return_value = {
            "ReportDefinitions": [
                {
                    "ReportName": FAKE.word(),
                    "TimeUnit": "HOURLY",
                    "Format": "textORcsv",
                    "Compression": "GZIP",
                    "AdditionalSchemaElements": ["RESOURCES"],
                    "S3Bucket": bucket,
                    "S3Prefix": FAKE.word(),
                    "S3Region": "us-east-1",
                    "AdditionalArtifacts": [],
                    "RefreshClosedReports": True,
                    "ReportVersioning": "CREATE_NEW_REPORT",
                }
            ],
            "ResponseMetadata": {
                "RequestId": FAKE.uuid4(),
                "HTTPStatusCode": 200,
                "HTTPHeaders": {
                    "x-amzn-requestid": FAKE.uuid4(),
                    "content-type": "application/x-amz-json-1.1",
                    "content-length": "1234",
                    "date": FAKE.date_time(),
                },
                "RetryAttempts": 0,
            },
        }
        mock_boto3_client.return_value = s3_client
        try:
            _check_cost_report_access(
                FAKE.word(),
                {
                    "aws_access_key_id": FAKE.md5(),
                    "aws_secret_access_key": FAKE.md5(),
                    "aws_session_token": FAKE.md5(),
                },
                bucket=bucket,
            )
        except Exception as exc:
            self.fail(str(exc))

    @patch("providers.aws.provider.boto3.client")
    def test_cur_without_resourceids(self, mock_boto3_client):
        """Test that a CUR without resource IDs raises ValidationError."""
        bucket = FAKE.word()
        s3_client = Mock()
        s3_client.describe_report_definitions.return_value = {
            "ReportDefinitions": [
                {
                    "ReportName": FAKE.word(),
                    "TimeUnit": "HOURLY",
                    "Format": "textORcsv",
                    "Compression": "GZIP",
                    "AdditionalSchemaElements": [],
                    "S3Bucket": bucket,
                    "S3Prefix": FAKE.word(),
                    "S3Region": "us-east-1",
                    "AdditionalArtifacts": [],
                    "RefreshClosedReports": True,
                    "ReportVersioning": "CREATE_NEW_REPORT",
                }
            ],
            "ResponseMetadata": {
                "RequestId": FAKE.uuid4(),
                "HTTPStatusCode": 200,
                "HTTPHeaders": {
                    "x-amzn-requestid": FAKE.uuid4(),
                    "content-type": "application/x-amz-json-1.1",
                    "content-length": "1234",
                    "date": FAKE.date_time(),
                },
                "RetryAttempts": 0,
            },
        }
        mock_boto3_client.return_value = s3_client
        with self.assertRaises(ValidationError):
            _check_cost_report_access(
                FAKE.word(),
                {
                    "aws_access_key_id": FAKE.md5(),
                    "aws_secret_access_key": FAKE.md5(),
                    "aws_session_token": FAKE.md5(),
                },
                bucket=bucket,
            )
