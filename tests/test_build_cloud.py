import os
from argparse import Namespace
from unittest import TestCase

from buildcloud.build_cloud import (
    parse_args,
)
from tests.common_test import (
    setup_test_logging,
)


class TestCloudBuild(TestCase):

    def setUp(self):
        self.temp_home = '/tmp/home'
        home_original = os.environ['HOME']
        os.environ['HOME'] = self.temp_home
        self.addCleanup(self.restore_home, home_original)
        setup_test_logging(self)

    def restore_home(self, home_original):
        os.environ['HOME'] = home_original

    def test_parse_args(self):
        build_number = os.environ.get('BUILD_NUMBER', '')
        os.environ['BUILD_NUMBER'] = "1234"
        args = parse_args(['cwr-model', 'test-plan'])
        expected = Namespace(bundle_file='',
                             juju_home='/tmp/home/cloud-city', log_dir=None,
                             model=['cwr-model'], test_plan='test-plan',
                             verbose=0, test_id="1234")
        self.assertEqual(args, expected)
        os.environ['BUILD_NUMBER'] = build_number

    def get_args(self):
        return Namespace(env='juju-env')
