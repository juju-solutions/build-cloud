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


class TestMakeClient(TestCase):

    def test_make_client(self):
        with patch('buildcloud.juju.run_command', autospec=True,
                   return_value='2.00'):
            client = make_client('/tmp/juju', 'host', 'logdir', None, None,
                                 None)
        self.assertIsInstance(client, JujuClient)

    def test_make_client1x(self):
        with patch('buildcloud.juju.run_command', autospec=True,
                   return_value='1.23'):
            with self.assertRaisesRegexp(
                    ValueError, 'Juju 1.x is not supported'):
                make_client('/tmp/juju', 'host', 'logdir', None, None, None)


class TestJujuClient(TestCase):

    def test__bootstrap(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar', fake_host, None, constraints='mem=3G')
        with patch('buildcloud.juju.run_command', autospec=True) as jrc_mock:
            jc._bootstrap()
        calls = ([
            call('/foo/bar bootstrap --show-log google/europe-west1 gce '
                 '--default-model gce --no-gui --constraints mem=3G'),
            call('/foo/bar bootstrap --show-log azure/westus azure '
                 '--default-model azure --no-gui --constraints mem=3G')
        ])
        self.assertEqual(jrc_mock.call_args_list, calls)
        self.assertEqual(jc.bootstrapped, ['gce', 'azure'])
        self.assertEqual(jc.host.controllers,
                         ['gce:gce', 'azure:azure'])

    def test__bootstrap_exception(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar', fake_host, None, constraints='mem=3G',
                        config='test-mode=true')
        with patch('buildcloud.juju.run_command', autospec=True,
                   side_effect=[None, subprocess.CalledProcessError('', '')]
                   ) as jrc_mock:
            jc._bootstrap()
        calls = ([
            call('/foo/bar bootstrap --show-log google/europe-west1 gce '
                 '--default-model gce --no-gui '
                 '--constraints mem=3G --config test-mode=true'),
            call('/foo/bar bootstrap --show-log azure/westus azure '
                 '--default-model azure --no-gui '
                 '--constraints mem=3G --config test-mode=true')
        ])
        self.assertEqual(jrc_mock.call_args_list, calls)
        self.assertEqual(jc.bootstrapped, ['gce'])

    def test__bootstrap_bootstrap_constraints(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar', fake_host, None,
                        bootstrap_constraints='tags=ob', config='foo=bar')
        with patch('buildcloud.juju.run_command', autospec=True) as jrc_mock:
            jc._bootstrap()
        calls = ([
            call('/foo/bar bootstrap --show-log google/europe-west1 gce '
                 '--default-model gce --no-gui --bootstrap-constraints '
                 'tags=ob --config foo=bar'),
            call('/foo/bar bootstrap --show-log azure/westus azure '
                 '--default-model azure --no-gui --bootstrap-constraints '
                 'tags=ob --config foo=bar')
        ])
        self.assertEqual(jrc_mock.call_args_list, calls)
        self.assertEqual(jc.bootstrapped, ['gce', 'azure'])
        self.assertEqual(jc.host.controllers,
                         ['gce:gce', 'azure:azure'])

    def test__bootstrap_bootstrap_constraints_model_constraints(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar', fake_host, None,
                        bootstrap_constraints='tags=ob',
                        constraints='mem=2G')
        with patch('buildcloud.juju.run_command', autospec=True) as jrc_mock:
            jc._bootstrap()
        calls = ([
            call('/foo/bar bootstrap --show-log google/europe-west1 gce '
                 '--default-model gce --no-gui '
                 '--constraints mem=2G --bootstrap-constraints tags=ob'),
            call('/foo/bar bootstrap --show-log azure/westus azure '
                 '--default-model azure --no-gui --constraints mem=2G '
                 '--bootstrap-constraints tags=ob')
        ])
        self.assertEqual(jrc_mock.call_args_list, calls)
        self.assertEqual(jc.bootstrapped, ['gce', 'azure'])
        self.assertEqual(jc.host.controllers,
                         ['gce:gce', 'azure:azure'])

    def test__bootstrap_no_constraints(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar', fake_host, None)
        with patch('buildcloud.juju.run_command', autospec=True) as jrc_mock:
            jc._bootstrap()
        calls = ([
            call('/foo/bar bootstrap --show-log google/europe-west1 gce '
                 '--default-model gce --no-gui'),
            call('/foo/bar bootstrap --show-log azure/westus azure '
                 '--default-model azure --no-gui')])
        self.assertEqual(jrc_mock.call_args_list, calls)
        self.assertEqual(jc.bootstrapped, ['gce', 'azure'])
        self.assertEqual(jc.host.controllers,
                         ['gce:gce', 'azure:azure'])

    def test_bootstrap(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar/juju', fake_host, None, config='foo=bar')
        with patch('buildcloud.juju.run_command', autospec=True) as jrc_mock:
            with patch.object(jc, 'copy_remote_logs', autospec=True
                              ) as crl_mock:
                with patch.object(jc, '_destroy', autospec=True) as d_mock:
                    with jc.bootstrap() as bootstrapped:
                        pass
        calls = ([
            call('/foo/bar/juju --version'),
            call('/foo/bar/juju bootstrap --show-log google/europe-west1 gce '
                 '--default-model gce --no-gui --config foo=bar'),
            call('/foo/bar/juju bootstrap --show-log azure/westus azure '
                 '--default-model azure --no-gui --config foo=bar')])
        self.assertEqual(jrc_mock.call_args_list, calls)
        crl_mock.assert_called_once_with()
        d_mock.assert_called_once_with()
        self.assertEqual(bootstrapped, ['gce:gce', 'azure:azure'])

    def test_bootstrap_with_cloud_fail(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar/juju', fake_host, None)
        with patch('buildcloud.juju.run_command', autospec=True,
                   side_effect=[None, None,
                                subprocess.CalledProcessError('', '')]
                   ) as jrc_mock:
            with patch.object(jc, 'copy_remote_logs', autospec=True
                              ) as crl_mock:
                with patch.object(jc, '_destroy', autospec=True) as d_mock:
                    with jc.bootstrap() as bootstrapped:
                        pass
        calls = ([
            call('/foo/bar/juju --version'),
            call('/foo/bar/juju bootstrap --show-log google/europe-west1 gce '
                 '--default-model gce --no-gui'),
            call('/foo/bar/juju bootstrap --show-log azure/westus azure '
                 '--default-model azure --no-gui')])
        self.assertEqual(jrc_mock.call_args_list, calls)
        crl_mock.assert_called_once_with()
        d_mock.assert_called_once_with()
        self.assertEqual(bootstrapped, ['gce:gce'])

    def test_copy_remote_logs(self):
        fake_host = FakeHost()
        jc = JujuClient('/foo/bar', fake_host, '/tmp/log')
        jc.bootstrapped = ['cwr-gce', 'cwr-azure']
        with patch.object(jc, 'run', autospec=True,
                          side_effect=['file1', None, None,
                                       'file2', None, None,
                                       'file3', None, None,
                                       'file4', None, None,
                                       'file5', None, None,
                                       'file6', None, None,
                                       'file7', None, None,
                                       'file8', None, None,
                                       'file9', None, None,
                                       'file10', None, None,
                                       'file12', None, None,
                                       'file13', None, None,
                                       ]
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
            call('ssh', '0 ls /var/log/cloud-init*.log', 'cwr-gce:cwr-gce'),
            call('ssh', '0 sudo chmod  -Rf go+r file1',
                 model='cwr-gce:cwr-gce'),
            call('scp', '-- -rC 0:file1 /tmp/log/cwr-gce-cwr-gce--file1',
                 model='cwr-gce:cwr-gce'),
            call('ssh', '0 ls /var/log/juju/*.log', 'cwr-gce:cwr-gce'),
            call('ssh', '0 sudo chmod  -Rf go+r file2',
                 model='cwr-gce:cwr-gce'),
            call('scp', '-- -rC 0:file2 /tmp/log/cwr-gce-cwr-gce--file2',
                 model='cwr-gce:cwr-gce'),
            call('ssh', '0 ls /var/log/syslog', 'cwr-gce:cwr-gce'),
            call('ssh', '0 sudo chmod  -Rf go+r file3',
                 model='cwr-gce:cwr-gce'),
            call('scp', '-- -rC 0:file3 /tmp/log/cwr-gce-cwr-gce--file3',
                 model='cwr-gce:cwr-gce'),
            call('ssh', '0 ls /var/log/cloud-init*.log', 'cwr-gce:controller'),
            call('ssh', '0 sudo chmod  -Rf go+r file4',
                 model='cwr-gce:controller'),
            call('scp', '-- -rC 0:file4 /tmp/log/cwr-gce-controller--file4',
                 model='cwr-gce:controller'),
            call('ssh', '0 ls /var/log/juju/*.log', 'cwr-gce:controller'),
            call('ssh', '0 sudo chmod  -Rf go+r file5',
                 model='cwr-gce:controller'),
            call('scp', '-- -rC 0:file5 /tmp/log/cwr-gce-controller--file5',
                 model='cwr-gce:controller'),
            call('ssh', '0 ls /var/log/syslog', 'cwr-gce:controller'),
            call('ssh', '0 sudo chmod  -Rf go+r file6',
                 model='cwr-gce:controller'),
            call('scp', '-- -rC 0:file6 /tmp/log/cwr-gce-controller--file6',
                 model='cwr-gce:controller'),
            call('ssh', '0 ls /var/log/cloud-init*.log',
                 'cwr-azure:cwr-azure'),
            call('ssh', '0 sudo chmod  -Rf go+r file7',
                 model='cwr-azure:cwr-azure'),
            call('scp', '-- -rC 0:file7 /tmp/log/cwr-azure-cwr-azure--file7',
                 model='cwr-azure:cwr-azure'),
            call('ssh', '0 ls /var/log/juju/*.log', 'cwr-azure:cwr-azure'),
            call('ssh', '0 sudo chmod  -Rf go+r file8',
                 model='cwr-azure:cwr-azure'),
            call('scp', '-- -rC 0:file8 /tmp/log/cwr-azure-cwr-azure--file8',
                 model='cwr-azure:cwr-azure'),
            call('ssh', '0 ls /var/log/syslog', 'cwr-azure:cwr-azure'),
            call('ssh', '0 sudo chmod  -Rf go+r file9',
                 model='cwr-azure:cwr-azure'),
            call('scp', '-- -rC 0:file9 /tmp/log/cwr-azure-cwr-azure--file9',
                 model='cwr-azure:cwr-azure'),
            call('ssh', '0 ls /var/log/cloud-init*.log',
                 'cwr-azure:controller'),
            call('ssh', '0 sudo chmod  -Rf go+r file10',
                 model='cwr-azure:controller'),
            call('scp',
                 '-- -rC 0:file10 /tmp/log/cwr-azure-controller--file10',
                 model='cwr-azure:controller'),
            call('ssh', '0 ls /var/log/juju/*.log', 'cwr-azure:controller'),
            call('ssh', '0 sudo chmod  -Rf go+r file12',
                 model='cwr-azure:controller'),
            call('scp',
                 '-- -rC 0:file12 /tmp/log/cwr-azure-controller--file12',
                 model='cwr-azure:controller'),
            call('ssh', '0 ls /var/log/syslog', 'cwr-azure:controller'),
            call('ssh', '0 sudo chmod  -Rf go+r file13',
                 model='cwr-azure:controller'),
            call('scp',
                 '-- -rC 0:file13 /tmp/log/cwr-azure-controller--file13',
                 model='cwr-azure:controller')]
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
