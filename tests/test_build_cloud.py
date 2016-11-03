import os
from argparse import Namespace
from unittest import TestCase

from mock import (
    Mock,
    patch,
)

from buildcloud.build_cloud import (
    get_cwr_options,
    run_test_without_container,
    parse_args,
)
from tests.common_test import (
    setup_test_logging,
)


class TestCloudBuild(TestCase):

    def setUp(self):
        self.temp_home = '/tmp/home/cloud-city'
        home_original = os.environ['JUJU_HOME']
        os.environ['JUJU_HOME'] = self.temp_home
        self.addCleanup(self.restore_home, home_original)
        setup_test_logging(self)

    def restore_home(self, home_original):
        os.environ['JUJU_HOME'] = home_original

    def test_parse_args(self):
        build_number = os.environ.get('BUILD_NUMBER', '')
        os.environ['BUILD_NUMBER'] = "1234"
        args = parse_args(['cwr-model', 'test-plan'])
        expected = Namespace(bootstrap_constraints=None,
                             bucket=None,
                             bundle_file='',
                             config='test-mode=true',
                             constraints='mem=3G',
                             controllers=['cwr-model'],
                             controllers_bootstrapped=False,
                             cwr_path=None,
                             juju_home='/tmp/home/cloud-city',
                             juju_path='juju',
                             log_dir=None,
                             no_container=False,
                             results_dir=None,
                             results_per_bundle=None,
                             s3_creds=None,
                             test_id='1234',
                             test_plan='test-plan',
                             verbose=0,
                             )
        self.assertEqual(args, expected)
        os.environ['BUILD_NUMBER'] = build_number

    def get_args(self):
        return Namespace(env='juju-env')

    def test_get_cwr_options(self):
        args = parse_args(['controller', 'test-plan'])
        host = Mock(test_results='/foo')
        options = get_cwr_options(args, host)
        expected = '--results-dir /foo --s3-private'
        self.assertEqual(options, expected)

        args = parse_args(['controller', 'test-plan',
                           '--results-dir', 'foo/dir',
                           '--bucket', 'bar',
                           '--s3-creds', 'baz'])
        options = get_cwr_options(args, host)
        expected = ("--results-dir foo/dir --bucket bar --s3-creds baz "
                    "--s3-private")
        self.assertEqual(options, expected)

    def test_run_test_without_container(self):
        args = parse_args(['controller', 'test-plan', '--test-id', '2'])
        with patch('buildcloud.build_cloud.run_command', autospec=True
                   ) as rc_mock:
            host = Mock(test_results='/test_results')
            run_test_without_container(host, args, ['cntr1', 'cntr2'])
        rc_mock.assert_called_once_with(
            'cwr -F -l DEBUG -v  cntr1 cntr2 test-plan --test-id 2 '
            '--results-dir /test_results --s3-private')

    def test_run_test_without_container_non_default(self):
        args = parse_args(['controller', 'test-plan',
                           '--cwr-path', 'cwr/run.py',
                           '--test-id', '2',
                           '--results-dir', 'foo/dir',
                           '--bucket', 'my-bucket',
                           '--s3-creds', '/baz/creds'])
        with patch('buildcloud.build_cloud.run_command', autospec=True
                   ) as rc_mock:
            host = Mock(test_results='/test_results')
            run_test_without_container(host, args, ['cntr1', 'cntr2'])
        rc_mock.assert_called_once_with(
            'python cwr/run.py -F -l DEBUG -v  cntr1 cntr2 test-plan '
            '--test-id 2 --results-dir foo/dir --bucket my-bucket --s3-creds '
            '/baz/creds --s3-private')
