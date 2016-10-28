from argparse import Namespace
from contextlib import contextmanager
import os
from unittest import TestCase

from mock import (
    patch,
    call,
)
import yaml

from buildcloud.schedule_cwr_jobs import (
    build_jobs,
    Credentials,
    get_credentials,
    get_job_name,
    get_test_plans,
    make_parameters,
    parse_args
)
from buildcloud.utility import temp_dir


class TestSchedule(TestCase):

    def test_parse_args(self):
        with jenkins_env():
            args = parse_args(['test_dir', 'default-aws', 'default-azure'])
            expected = Namespace(
                controllers=['default-aws', 'default-azure'],
                cwr_test_token='fake_pass',
                password='bar',
                test_plan_dir='test_dir',
                test_plans=None,
                user='foo',
            )
            self.assertEqual(args, expected)

    def test_make_parameters(self):
        args = Namespace(controllers=['default-aws'])
        with temp_dir() as test_dir:
            test_plan = self.fake_parameters(test_dir)
            parameters = make_parameters(
                test_plan, args, 'default-aws', '1234')
        expected = {
            'controllers': 'default-aws',
            'bundle_name': 'make_life_easy',
            'test_id': '1234',
            'test_plan': test_plan}
        self.assertEqual(parameters, expected)

    def test_get_test_plans(self):
        args = Namespace(controllers=['default-aws'], password='bar',
                         test_plan_dir='', test_plans=None, user='foo')
        with temp_dir() as test_dir:
            args.test_plan_dir = test_dir
            self.fake_parameters(test_dir)
            self.fake_parameters(test_dir, 2)
            self.fake_parameters(test_dir, 3, ext='.py')
            parameters = list(get_test_plans(args))
        expected = [
            os.path.join(test_dir, 'test1.yaml'),
            os.path.join(test_dir, 'test2.yaml'),
        ]
        self.assertItemsEqual(parameters, expected)

    def test_get_credentials(self):
        args = Namespace(controllers=['default-aws'], password='bar',
                         test_plan_dir='', test_plans=None, user='foo')
        cred = get_credentials(args)
        self.assertEqual(cred.user, 'foo')
        self.assertEqual(cred.password, 'bar')

    def fake_parameters(self, test_dir, count=1, ext='.yaml', test_label=None):
        test_plan = os.path.join(test_dir, 'test' + str(count) + ext)
        plan = {
            'bundle': 'make life easy',
            'bundle_name': 'make_life_easy',
            'bundle_file': ''
        }
        if test_label:
            plan['test_label'] = test_label
        with open(test_plan, 'w') as f:
            yaml.dump(plan, f)
        return test_plan

    def test_build_jobs(self):
        credentials = Credentials('joe', 'pass')
        args = Namespace(cwr_test_token='fake',
                         controllers=['default-aws', 'default-gce'],
                         test_plan_dir='')
        with patch('buildcloud.schedule_cwr_jobs.Jenkins',
                   autospec=True) as jenkins_mock:
            with patch('buildcloud.schedule_cwr_jobs.generate_test_id',
                       side_effect=['1', '2', '3', '4']) as gti_mock:
                with temp_dir() as test_dir:
                    args.test_plan_dir = test_dir
                    test_plan1 = os.path.join(test_dir, 'test1.yaml')
                    test_plan2 = os.path.join(test_dir, 'test2.yaml')
                    self.fake_parameters(test_dir)
                    self.fake_parameters(test_dir, 2)
                    test_plans = [test_plan1, test_plan2]
                    build_jobs(credentials, test_plans, args)
        jenkins_mock.assert_called_once_with(
            'http://juju-ci.vapour.ws:8080', 'joe', 'pass')
        self.assertEqual(gti_mock.mock_calls, [call(), call()])
        calls = [
            call('cwr-aws',
                 {
                     'controllers': 'default-aws',
                     'bundle_name': 'make_life_easy',
                     'test_id': '1',
                     'test_plan': test_plan1
                 },
                 token='fake'),
            call('cwr-gce',
                 {
                     'controllers': 'default-gce',
                     'bundle_name': 'make_life_easy',
                     'test_id': '1',
                     'test_plan': test_plan1
                 },
                 token='fake'),
            call('cwr-aws',
                 {
                     'controllers': 'default-aws',
                     'bundle_name': 'make_life_easy',
                     'test_id': '2',
                     'test_plan': test_plan2
                 },
                 token='fake'),
            call('cwr-gce',
                 {
                     'controllers': 'default-gce',
                     'bundle_name': 'make_life_easy',
                     'test_id': '2',
                     'test_plan': test_plan2
                 },
                 token='fake')
        ]
        self.assertEqual(jenkins_mock.return_value.build_job.mock_calls, calls)

    def test_build_jobs_test_label(self):
        credentials = Credentials('joe', 'pass')
        args = Namespace(cwr_test_token='fake',
                         controllers=['default-aws', 'default-gce'],
                         test_plan_dir='')
        with patch('buildcloud.schedule_cwr_jobs.Jenkins',
                   autospec=True) as jenkins_mock:
            with patch('buildcloud.schedule_cwr_jobs.generate_test_id',
                       side_effect=['1', '2', '3', '4']) as gti_mock:
                with temp_dir() as test_dir:
                    args.test_plan_dir = test_dir
                    test_plan1 = os.path.join(test_dir, 'test1.yaml')
                    test_plan2 = os.path.join(test_dir, 'test2.yaml')
                    self.fake_parameters(test_dir, test_label='cwr-aws')
                    self.fake_parameters(test_dir, 2, test_label='cwr-gce')
                    test_plans = [test_plan1, test_plan2]
                    build_jobs(credentials, test_plans, args)
        jenkins_mock.assert_called_once_with(
            'http://juju-ci.vapour.ws:8080', 'joe', 'pass')
        self.assertEqual(gti_mock.mock_calls, [call(), call()])
        calls = [
            call('cwr-aws',
                 {
                     'controllers': 'cwr-aws',
                     'test_label': 'cwr-aws',
                     'test_id': '1',
                     'test_plan': test_plan1,
                     'bundle_name': 'make_life_easy',
                 },
                 token='fake'),
            call('cwr-gce',
                 {
                     'controllers': 'cwr-gce',
                     'test_label': 'cwr-gce',
                     'test_id': '2',
                     'test_plan': test_plan2,
                     'bundle_name': 'make_life_easy',
                 },
                 token='fake')
        ]
        self.assertEqual(jenkins_mock.return_value.build_job.mock_calls, calls)

    def test_get_job_name(self):
        job_name = get_job_name('default-aws')
        self.assertEqual(job_name, 'cwr-aws')
        job_name = get_job_name('default-gce-dfe')
        self.assertEqual(job_name, 'cwr-gce')
        job_name = get_job_name('default-joyent')
        self.assertEqual(job_name, 'cwr-joyent')
        job_name = get_job_name('default-azure-')
        self.assertEqual(job_name, 'cwr-azure')


@contextmanager
def jenkins_env():
    user = os.environ.get('JENKINS_USER')
    password = os.environ.get('JENKINS_PASSWORD')
    cwr_token = os.environ.get('CWR_TEST_TOKEN')
    build_number = os.environ.get('BUILD_NUMBER')
    os.environ['BUILD_NUMBER'] = '1234'
    os.environ["JENKINS_USER"] = 'foo'
    os.environ["JENKINS_PASSWORD"] = 'bar'
    os.environ["CWR_TEST_TOKEN"] = 'fake_pass'
    try:
        yield
    finally:
        os.environ["JENKINS_USER"] = user if user else ''
        os.environ["JENKINS_PASSWORD"] = password if password else ''
        os.environ["CWR_TEST_TOKEN"] = cwr_token if cwr_token else ''
        os.environ['BUILD_NUMBER'] = build_number if build_number else ''
