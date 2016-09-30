from contextlib import contextmanager
import logging
import os
import subprocess
import yaml

from buildcloud.utility import (
    get_temp_controller_name,
    cloud_from_env,
    run_command,
)


__metaclass__ = type


class JujuClient:

    def __init__(self, juju_path, host, log_dir, operator_flag='-m'):
        self.juju = juju_path
        self.host = host
        self.log_dir = log_dir
        self.operator_flag = operator_flag
        self.bootstrapped = []

    def _bootstrap(self):
        for i, controller in enumerate(self.host.controllers):
            constraints = '--constraints mem=3G'
            cloud = cloud_from_env(controller)
            controller = "cwr-{}".format(controller)
            self.host.controllers[i] = self.get_model(controller)
            if 'azure' in controller.lower():
                controller = get_temp_controller_name(controller)
            try:
                run_command(
                    '{} bootstrap --show-log {} {} {} --config '
                    'test-mode=true --default-model {}'.format(
                            self.juju, constraints, controller, cloud,
                            controller))
            except subprocess.CalledProcessError:
                logging.error('Bootstrapping failed on {}'.format(
                        controller))
                continue
            self.bootstrapped.append(controller)

    def _destroy(self):
        killed = []
        for controller in self.bootstrapped:
            try:
                run_command('{} --debug kill-controller {} -y'.format(
                    self.juju, controller))
                killed.append(controller)
            except subprocess.CalledProcessError:
                logging.error(
                    "Error destroy env failed: {}".format(controller))
        self.bootstrapped = [x for x in self.bootstrapped if x not in killed]

    @contextmanager
    def bootstrap(self):
        run_command('{} --version'.format(self.juju))
        logging.info("JUJU_DATA is set to {}".format(self.host.tmp_juju_home))
        try:
            self._bootstrap()
            yield
        finally:
            try:
                self.copy_remote_logs()
            except subprocess.CalledProcessError:
                logging.error('Getting logs failed.')
            self._destroy()

    def get_model(self, controller):
        return '{}:{}'.format(controller, controller)

    def copy_remote_logs(self):
        logging.info("Gathering remote logs.")
        logs = [
            '/var/log/cloud-init*.log',
            '/var/log/juju/*.log',
            '/var/log/syslog',
        ]
        for controller in self.bootstrapped:
            model = self.get_model(controller)
            status = self.get_status(model=model)
            machines = yaml.safe_load(status).get('machines')
            if not machines:
                logging.warn('No machines listed.')
                continue
            machines = yaml.safe_load(status)['machines'].keys()
            for machine in machines:
                for log in logs:
                    args = '{} ls {}'.format(machine, log)
                    try:
                        files = self.run('ssh', args, controller)
                    except subprocess.CalledProcessError:
                        logging.warn("Could not list remote files.")
                        continue
                    files = files.strip().split()
                    for f in files:
                        try:
                            args = '{} sudo chmod  -Rf go+r {}'.format(
                                    machine, f)
                            self.run('ssh', args, model=controller)
                            basename = '{}--{}'.format(
                                    controller, os.path.basename(f))
                            dst_path = os.path.join(self.log_dir, basename)
                            args = '-- -rC {}:{} {}'.format(
                                    machine, f, dst_path)
                            self.run('scp', args, model=controller)
                        except subprocess.CalledProcessError:
                            logging.warn(
                                "Could not get logs for {} {}".format(
                                        controller, f))
        else:
            logging.info('No machine logs to copy.')

    def run(self, command, args='', model=''):
        m = '{} {}'.format(self.operator_flag, model) if model else model
        return run_command('{} {} {} {}'.format(self.juju, command, m, args))

    def get_status(self, model=''):
        return self.run('status --format yaml', model=model)


class JujuClient1x(JujuClient):

    def __init__(self, juju_path, host, log_dir):
        super(JujuClient1x, self).__init__(
                juju_path, host, log_dir, operator_flag='-e')

    def get_model(self, controller):
        return controller

    def _bootstrap(self):
        for controller in self.host.controllers:
            constraints = '--constraints mem=3G'
            try:
                run_command(
                    '{} bootstrap --show-log -e {} {}'.format(
                        self.juju, controller, constraints))
                run_command('{} set-constraints -e {} mem=2G'.format(
                    self.juju, controller))
            except subprocess.CalledProcessError:
                logging.error('Bootstrapping failed on {}'.format(controller))
                continue
            self.bootstrapped.append(controller)

    def _destroy(self):
        killed = []
        for controller in self.bootstrapped:
            try:
                run_command(
                    '{} destroy-environment --force --yes {}'.format(
                        self.juju, controller))
                killed.append(controller)
            except subprocess.CalledProcessError:
                logging.error(
                    "Error destroy env failed: {}".format(controller))
        self.bootstrapped = [x for x in self.bootstrapped if x not in killed]

    @contextmanager
    def bootstrap(self):
        run_command('{} --version'.format(self.juju))
        logging.info("Juju home is set to {}".format(self.host.tmp_juju_home))
        try:
            self._bootstrap()
            yield
        finally:
            try:
                self.copy_remote_logs()
            except subprocess.CalledProcessError:
                logging.error('Getting logs failed.')
            self._destroy()


def make_client(juju_path=None, *args, **kwargs):
    if juju_path is None:
        juju_path = 'juju'
    version = run_command('{} --version'.format(juju_path)).strip()
    if version.startswith('1.'):
        return JujuClient1x(juju_path, *args, **kwargs)
    elif version.startswith('2.'):
        return JujuClient(juju_path, *args, **kwargs)
    else:
        raise ValueError('Unknown juju version')
