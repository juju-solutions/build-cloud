from contextlib import contextmanager
import logging
import os
import subprocess
import yaml

from buildcloud.utility import (
    cloud_from_env,
    run_command,
)


__metaclass__ = type


class JujuClient:

    def __init__(self, juju_path, host, log_dir, operator_flag='-m',
                 bootstrap_constraints=None, constraints=None):
        self.juju = juju_path
        self.host = host
        self.log_dir = log_dir
        self.operator_flag = operator_flag
        self.bootstrapped = []
        self.bootstrap_constraints = bootstrap_constraints
        self.constraints = constraints

    def _bootstrap(self):
        for i, controller in enumerate(self.host.controllers):
            args = []
            if self.constraints:
                args.append('--constraints {}'.format(self.constraints))
            if self.bootstrap_constraints:
                args.append('--bootstrap-constraints {}'.format(
                        self.bootstrap_constraints))
            cloud = cloud_from_env(controller)
            if cloud is None:
                raise ValueError('Unknown cloud: {}'.format(cloud))
            self.host.controllers[i] = self.get_model(controller)
            args = ' {}'.format(' '.join(args)) if args else ''
            try:
                run_command(
                    '{} bootstrap --show-log {} {} --config '
                    'test-mode=true --default-model {} --no-gui{}'.format(
                            self.juju, cloud, controller, controller,
                            args))
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
            yield [self.get_model(x) for x in self.bootstrapped]
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


def make_client(juju_path, host, log_dir, bootstrap_constraints,
                constraints):
    if juju_path is None:
        juju_path = 'juju'
    version = run_command('{} --version'.format(juju_path)).strip()
    if version.startswith('1.'):
        raise ValueError('Juju 1.x is not supported.')
    elif version.startswith('2.'):
        return JujuClient(juju_path, host, log_dir=log_dir,
                          bootstrap_constraints=bootstrap_constraints,
                          constraints=constraints)
    else:
        raise ValueError('Unknown juju version')
