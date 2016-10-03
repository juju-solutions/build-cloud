import subprocess

from mock import (
    call,
    patch,
)

from buildcloud.juju import (
    JujuClient,
    make_client,
    )
from tests import TestCase
from tests.test_schedule_cwr_jobs import jenkins_env


class TestMakeClient(TestCase):

    def test_make_client(self):
        with patch('buildcloud.juju.run_command', autospec=True,
                   return_value='2.00'):
            client = make_client('/tmp/juju', 'host', 'logdir')
        self.assertIsInstance(client, JujuClient)

    def test_make_client1x(self):
        with patch('buildcloud.juju.run_command', autospec=True,
                   return_value='1.23'):
            with self.assertRaisesRegexp(
                    ValueError, 'Juju 1.x is not supported'):
                make_client('/tmp/juju', 'host', 'logdir')


class TestJujuClient(TestCase):

    def test__bootstrap(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar', fake_host, None)
        with patch('buildcloud.juju.run_command', autospec=True) as jrc_mock:
            with jenkins_env():
                jc._bootstrap()
        calls = ([
            call('/foo/bar bootstrap --show-log --constraints mem=3G '
                 'cwr-gce google/europe-west1 --config test-mode=true '
                 '--default-model cwr-gce'),
            call('/foo/bar bootstrap --show-log --constraints mem=3G '
                 'cwr-azure-1234 azure/westus --config test-mode=true '
                 '--default-model cwr-azure-1234')])
        self.assertEqual(jrc_mock.call_args_list, calls)
        self.assertEqual(jc.bootstrapped, ['cwr-gce', 'cwr-azure-1234'])
        self.assertEqual(jc.host.controllers,
                         ['cwr-gce:cwr-gce', 'cwr-azure-1234:cwr-azure-1234'])

    def test__bootstrap_exception(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar', fake_host, None)
        with patch('buildcloud.juju.run_command', autospec=True,
                   side_effect=[None, subprocess.CalledProcessError('', '')]
                   ) as jrc_mock:
            with patch('buildcloud.juju.get_temp_controller_name',
                       autospec=True, return_value='baz') as gtcn_mock:
                jc._bootstrap()
        calls = ([
            call('/foo/bar bootstrap --show-log --constraints mem=3G '
                 'cwr-gce google/europe-west1 --config test-mode=true '
                 '--default-model cwr-gce'),
            call('/foo/bar bootstrap --show-log --constraints mem=3G '
                 'baz azure/westus --config test-mode=true --default-model '
                 'baz')])
        self.assertEqual(jrc_mock.call_args_list, calls)
        self.assertEqual(jc.bootstrapped, ['cwr-gce'])
        gtcn_mock.assert_called_once_with('cwr-azure')

    def test_bootstrap(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar/juju', fake_host, None)
        with patch('buildcloud.juju.run_command', autospec=True) as jrc_mock:
            with patch.object(jc, 'copy_remote_logs', autospec=True
                              ) as crl_mock:
                with patch.object(jc, '_bootstrap', autospec=True
                                  ) as b_mock:
                    with patch.object(jc, '_destroy', autospec=True
                                      ) as d_mock:
                        with jc.bootstrap():
                            pass
        jrc_mock.assert_called_once_with('/foo/bar/juju --version')
        crl_mock.assert_called_once_with()
        b_mock.assert_called_once_with()
        d_mock.assert_called_once_with()

    def test_copy_remote_logs(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar', fake_host, '/tmp/log')
        jc.bootstrapped = ['cwr-gce', 'cwr-azure']
        with patch.object(jc, 'run', autospec=True,
                          side_effect=['file1', None, None,
                                       'file1', None, None,
                                       'file1', None, None,
                                       'file1', None, None,
                                       'file1', None, None,
                                       'file2', None, None]
                          ) as r_mock:
            with patch.object(jc, 'get_status', autospec=True,
                              return_value=None) as gs_mock:
                with patch('buildcloud.juju.yaml.safe_load', autospec=True,
                           return_value={'machines': {'0': ''}}):
                    jc.copy_remote_logs()
        gs_calls = [call(model='cwr-gce:cwr-gce'),
                    call(model='cwr-azure:cwr-azure')]
        self.assertEqual(gs_mock.call_args_list, gs_calls)
        r_calls = [
            call('ssh', '0 ls /var/log/cloud-init*.log', 'cwr-gce'),
            call('ssh', '0 sudo chmod  -Rf go+r file1', model='cwr-gce'),
            call('scp', '-- -rC 0:file1 /tmp/log/cwr-gce--file1',
                 model='cwr-gce'),
            call('ssh', '0 ls /var/log/juju/*.log', 'cwr-gce'),
            call('ssh', '0 sudo chmod  -Rf go+r file1', model='cwr-gce'),
            call('scp', '-- -rC 0:file1 /tmp/log/cwr-gce--file1',
                 model='cwr-gce'),
            call('ssh', '0 ls /var/log/syslog', 'cwr-gce'),
            call('ssh', '0 sudo chmod  -Rf go+r file1', model='cwr-gce'),
            call('scp', '-- -rC 0:file1 /tmp/log/cwr-gce--file1',
                 model='cwr-gce'),
            call('ssh', '0 ls /var/log/cloud-init*.log', 'cwr-azure'),
            call('ssh', '0 sudo chmod  -Rf go+r file1', model='cwr-azure'),
            call('scp', '-- -rC 0:file1 /tmp/log/cwr-azure--file1',
                 model='cwr-azure'),
            call('ssh', '0 ls /var/log/juju/*.log', 'cwr-azure'),
            call('ssh', '0 sudo chmod  -Rf go+r file1', model='cwr-azure'),
            call('scp', '-- -rC 0:file1 /tmp/log/cwr-azure--file1',
                 model='cwr-azure'),
            call('ssh', '0 ls /var/log/syslog', 'cwr-azure'),
            call('ssh', '0 sudo chmod  -Rf go+r file2', model='cwr-azure'),
            call('scp', '-- -rC 0:file2 /tmp/log/cwr-azure--file2',
                 model='cwr-azure')]
        self.assertEqual(r_mock.call_args_list, r_calls)

    def test__destroy(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar/juju', fake_host, None)
        jc.bootstrapped = ['cwr-gce', 'cwr-azure']
        with patch('buildcloud.juju.run_command', autospec=True) as jrc_mock:
            jc._destroy()
        calls = ([
            call('/foo/bar/juju --debug kill-controller cwr-gce -y'),
            call('/foo/bar/juju --debug kill-controller cwr-azure -y')])
        self.assertEqual(jrc_mock.call_args_list, calls)

    def test__destroy_exception(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar/juju', fake_host, None)
        jc.bootstrapped = ['cwr-gce', 'cwr-azure']
        with patch('buildcloud.juju.run_command', autospec=True,
                   side_effect=[None, subprocess.CalledProcessError('', '')]
                   ) as jrc_mock:
            jc._destroy()
        calls = ([
            call('/foo/bar/juju --debug kill-controller cwr-gce -y'),
            call('/foo/bar/juju --debug kill-controller cwr-azure -y')])
        self.assertEqual(jrc_mock.call_args_list, calls)

    def test_get_model(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar/juju', fake_host, None)
        model = jc.get_model('foo')
        self.assertEqual(model, 'foo:foo')

    def test_run(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar', fake_host, None)
        with patch('buildcloud.juju.run_command', autospec=True,
                   return_value='foo') as jrc_mock:
            result = jc.run('bzr', '--version', 'bzr-model')
        jrc_mock.assert_called_once_with('/foo/bar bzr -m bzr-model --version')
        self.assertEqual(result, 'foo')


class FakeHost:

    def __init__(self):
        self.controllers = ['gce', 'azure']
        self.tmp_juju_home = '/foo/home'
