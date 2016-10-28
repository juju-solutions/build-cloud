import os
import subprocess

from mock import patch
import yaml

from buildcloud.utility import (
    copytree_force,
    generate_controller_names,
    rename_env,
    run_command,
    temp_dir,
)
from tests import TestCase


class TestUtility(TestCase):

    def test_temp_dir(self):
        with temp_dir() as d:
            self.assertTrue(os.path.isdir(d))
        self.assertFalse(os.path.exists(d))

    def test_temp_dir_contents(self):
        with temp_dir() as d:
            self.assertTrue(os.path.isdir(d))
            open(os.path.join(d, "a-file"), "w").close()
        self.assertFalse(os.path.exists(d))

    def test_temp_dir_parent(self):
        with temp_dir() as p:
            with temp_dir(parent=p) as d:
                self.assertTrue(os.path.isdir(d))
                self.assertEqual(p, os.path.dirname(d))
            self.assertFalse(os.path.exists(d))
        self.assertFalse(os.path.exists(p))

    def test_run_command(self):
        proc = FakeProc()
        cmd = ['foo', 'bar']
        with patch('subprocess.Popen', autospec=True,
                   return_value=proc) as p_mock:
                run_command(cmd)
        p_mock.assert_called_once_with(cmd, stdout=subprocess.PIPE)

    def test_run_command_str(self):
        proc = FakeProc()
        cmd = ['foo bar']
        with patch('subprocess.Popen', autospec=True,
                   return_value=proc) as p_mock:
            run_command(cmd, verbose=True)
        p_mock.assert_called_once_with(cmd, stdout=subprocess.PIPE)

    def test_run_command_verbose(self):
        proc = FakeProc()
        cmd = ['foo', 'bar']
        with patch('subprocess.Popen', autospec=True,
                   return_value=proc) as p_mock:
            run_command(cmd, verbose=True)
        p_mock.assert_called_once_with(cmd, stdout=subprocess.PIPE)

    def test_copytree_force(self):
        with temp_dir() as src:
            with temp_dir() as dst:
                sub_src_dir = os.path.join(src, 'tmp')
                os.mkdir(sub_src_dir)
                sub_dst_dir = os.path.join(dst, 'tmp')
                os.mkdir(sub_dst_dir)
                copytree_force(src, dst)
                self.assertTrue(os.path.exists(sub_dst_dir))

    def test_rename_env(self):
        with temp_dir() as tmp_dir:
            env = {'environments': {
                   'old-env': {'access-key': 'my_access_key'}}}
            file_path = os.path.join(tmp_dir, 't.yaml')
            with open(file_path, 'w') as f:
                yaml.dump(env, f, default_flow_style=True)
            rename_env('old-env', 'cwr-', file_path)
            with open(file_path) as f:
                new_env = yaml.load(f)
            expected_env = {'environments': {'cwr-old-env': {
                'access-key': 'my_access_key'}}}
            self.assertEqual(new_env, expected_env)

    def test_generate_controller_names(self):
        names = ['gce', 'cwr-aws']
        new_names = generate_controller_names(names)
        expected = ['cwr-gce', 'cwr-aws']
        self.assertEqual(new_names, expected)


class FakeProc:

    returncode = 0

    def poll(self):
        return True
