import os
from argparse import Namespace
from unittest import TestCase

from mock import (
    call,
    Mock,
    patch,
    PropertyMock,
)

from buildcloud.build_cloud import (
    get_cwr_options,
    run_test_with_container,
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
        container = Mock(home='/home')
        options = get_cwr_options(args, host)
        expected = '--results-dir /foo --s3-private'
        self.assertEqual(options, expected)

        args = parse_args(['controller', 'test-plan',
                           '--results-dir', 'foo/dir',
                           '--bucket', 'bar',
                           '--s3-creds', '/bar/baz.cfg'])
        options = get_cwr_options(args, host, container=container)
        expected = ("--results-dir foo/dir --bucket bar --s3-creds "
                    "/home/baz.cfg --s3-private")
        self.assertEqual(options, expected)

    def test_run_test_without_container(self):
        args = parse_args(['controller', 'test-plan', '--test-id', '2'])
        with patch('buildcloud.build_cloud.run_command', autospec=True
                   ) as rc_mock:
            host = Mock(test_results='/test_results')
            run_test_without_container(host, args, ['cntr1', 'cntr2'])
        rc_mock.assert_called_once_with(
            'cwr -F -l DEBUG -v cntr1 cntr2 test-plan --test-id 2 '
            '--results-dir /test_results --s3-private')

    def test_run_test_without_container_non_default(self):
        args = parse_args(['controller', 'test-plan',
                           '--cwr-path', 'cwr/run.py',
                           '--test-id', '2',
                           '--results-dir', 'foo/dir',
                           '--bucket', 'my-bucket',
                           '--bundle-file', 'foo',
                           '--s3-creds', '/baz/creds',
                           '--no-container'])
        with patch('buildcloud.build_cloud.run_command', autospec=True
                   ) as rc_mock:
            host = Mock(test_results='/test_results')
            run_test_without_container(host, args, ['cntr1', 'cntr2'])
        rc_mock.assert_called_once_with(
            'python cwr/run.py -F -l DEBUG -v cntr1 cntr2 test-plan '
            '--test-id 2 --bundle foo --results-dir foo/dir '
            '--bucket my-bucket --s3-creds /baz/creds --s3-private')

    def test_run_test_with_container(self):
        args = parse_args(['controller', '/test/test-plan', '--test-id', '2',
                           '--s3-creds', '/host/s3-creds'])
        with patch('buildcloud.build_cloud.run_command', autospec=True
                   ) as rc_mock:
            host = Mock(test_results='/host/results',
                        tmp_juju_home='/host/.juju',
                        tmp='/host/tmp',
                        ssh_path='/host/ssh/path',
                        ssh_home='/host/ssh/home',
                        juju_repository='/host/repo',
                        )
            container = Mock(home='/home',
                             test_plans='/container/plans',
                             user='joe',
                             juju_home='/container/.juju',
                             test_results='/container/results',
                             juju_repository='/container/repo/',
                             ssh_home='/container/ssh/home',
                             )
            name = PropertyMock(return_value='cwrbox')
            type(container).name = name
            run_test_with_container(host, container, args, ['cntr1', 'cntr2'])
        calls = [
            call('sudo docker pull cwrbox'),
            call([
                'sudo', 'docker', 'run', '--rm',
                '--entrypoint', 'bash',
                '-u', 'joe',
                '-e', 'HOME=/home',
                '-e', 'JUJU_HOME=/container/.juju',
                '-e', 'JUJU_DATA=/container/.juju',
                '-e', 'PYTHONPATH=/home/cloud-weather-report',
                '-w', '/home',
                '-v', '/host/results:/container/results',
                '-v', '/host/.juju:/container/.juju',
                '-v', '/host/tmp/.deployer-store-cache:'
                      '/container/.juju/.deployer-store-cache',
                '-v', '/host/repo:/container/repo/',
                '-v', '/host/tmp:/host/tmp',
                '-v', '/test:/container/plans',
                '-v', '/host/s3-creds:/home/s3-creds',
                '-v', '/host/ssh/path:/container/ssh/home',
                '-t', 'cwrbox',
                '-c',
                'sudo juju --version && sudo -HE env PATH=$PATH '
                'PYTHONPATH=$PYTHONPATH python2 '
                '/home/cloud-weather-report/cloudweatherreport/run.py -F -l '
                'DEBUG -v cntr1 cntr2 /container/plans/test-plan --test-id 2 '
                '--results-dir /host/results --s3-creds /home/s3-creds '
                '--s3-private',
                ]
            )
        ]
        self.assertEqual(rc_mock.call_args_list, calls)
