#!/usr/bin/env python

from argparse import ArgumentParser
from contextlib import contextmanager
from collections import namedtuple
import logging
import os
import shutil
from tempfile import mkdtemp

from buildcloud.host import Host
from buildcloud.juju import make_client
from buildcloud.utility import (
    configure_logging,
    copytree_force,
    ensure_dir,
    get_juju_home,
    rename_env,
    run_command,
    temp_dir,
)


def parse_args(argv=None):
    parser = ArgumentParser()
    parser.add_argument(
        'controllers', nargs='+', help='Name of controllers to use')
    parser.add_argument(
        'test_plan', help='File path to test plan.')
    parser.add_argument(
        '--juju-path', help='Path to juju.', default='juju')
    parser.add_argument(
        '--bundle-file',
        help='Name of bundle file to deploy, if url points to a bundle '
             'containing multiple bundle files.', default='')
    parser.add_argument(
        '--verbose', action='count', default=0)
    parser.add_argument(
        '--juju-home', help='Juju home directory.', default=get_juju_home())
    parser.add_argument('--log-dir', help='The directory to dump logs to.')
    parser.add_argument('--test-id', help='Test ID.',
                        default=os.environ['BUILD_NUMBER'])
    parser.add_argument('--no-container', action='store_true',
                        help='Run cwr test without container.')
    args = parser.parse_args(argv)
    if args.juju_path != 'juju':
        args.juju_path = os.path.realpath(args.juju_path)
    return args


@contextmanager
def temp_juju_home(juju_home, juju_path):
    org_juju_home = os.environ.get('JUJU_HOME', '')
    org_juju_data = os.environ.get('JUJU_DATA', '')
    org_path = os.environ.get('PATH', '')
    os.environ["JUJU_HOME"] = juju_home
    os.environ["JUJU_DATA"] = juju_home

    temp_dir = mkdtemp(prefix='cwr_tst_')
    temp_name = os.path.join(temp_dir, 'juju')
    os.symlink(juju_path, temp_name)
    if juju_path != 'juju':
        os.environ['PATH'] = '{}{}{}'.format(temp_dir, os.pathsep, org_path)

    try:
        yield
    finally:
        os.environ['JUJU_HOME'] = org_juju_home
        os.environ['JUJU_DATA'] = org_juju_data
        shutil.rmtree(temp_dir)


@contextmanager
def env(args):
    with temp_dir() as root:
        tmp_juju_home = os.path.join(root, 'tmp_juju_home')
        shutil.copytree(args.juju_home, tmp_juju_home,
                        ignore=shutil.ignore_patterns('environments'))

        juju_repository = ensure_dir('juju_repository', parent=root)
        test_results = ensure_dir('results', parent=root)

        tmp = ensure_dir('tmp', parent=root)
        ssh_dir = os.path.join(tmp, 'ssh')
        os.mkdir(ssh_dir)
        shutil.copyfile(os.path.join(tmp_juju_home, 'staging-juju-rsa'),
                        os.path.join(ssh_dir, 'id_rsa'))
        ssh_path = os.path.join(tmp, 'ssh')

        new_names = []
        for controller in args.controllers:
            prefix = 'cwr-'
            name = rename_env(controller, prefix, os.path.join(
                tmp_juju_home, 'environments.yaml'))
            new_names.append(name)
        host = Host(tmp_juju_home=tmp_juju_home,
                    juju_repository=juju_repository, test_results=test_results,
                    tmp=tmp, ssh_path=ssh_path, root=root,
                    controllers=new_names)
        Container = namedtuple(
            'Container',
            ['user', 'name', 'home', 'ssh_home', 'juju_home', 'test_results',
             'juju_repository', 'test_plans'])
        container_user = 'ubuntu'
        container_home = os.path.join('/home', container_user)
        container_juju_home = os.path.join(container_home, '.juju')
        container_ssh_home = os.path.join(container_home, '.ssh')
        container_test_results = os.path.join(container_home, 'results')
        container_repository = os.path.join(container_home, 'charm-repo')
        container_test_plans = os.path.join(container_home, 'test_plans')
        container = Container(user=container_user,
                              name='seman/cwrbox',
                              home=container_home,
                              ssh_home=container_ssh_home,
                              juju_home=container_juju_home,
                              test_results=container_test_results,
                              juju_repository=container_repository,
                              test_plans=container_test_plans)
        yield host, container


def run_test_without_container(host, args):
    bundle_file = ''
    if args.bundle_file:
        bundle_file = '--bundle {}'.format(args.bundle_file)
    cmd = ('cwr -F -l DEBUG -v {} {} {} --test-id {} --result-output {}'.
           format(bundle_file, ' '.join(host.controllers), args.test_plan,
                  args.test_id, host.test_results))
    run_command(cmd)


def run_test_with_container(host, container, args):
    logging.debug("Host data: ", host)
    logging.debug("Container data: ", container)
    run_command('sudo docker pull {}'.format(container.name))
    container_options = (
        '--rm '
        '-u {} '
        '-e Home={} '
        '-e JUJU_HOME={} '
        '-w {} '
        '-v {}:{} '   # Test result location
        '-v {}:{} '   # Temp Juju home
        '-v {}/.deployer-store-cache:{}.deployer-store-cache '
        '-v {}:{} '   # Repository location
        '-v {}:{} '   # Temp location.
        '-v {}:{} '   # Test plan
        '-v {}:{} '   # ssh path
        '-t {} '.format(container.user,
                        container.home,
                        container.juju_home,
                        container.home,
                        host.test_results, container.test_results,
                        host.tmp_juju_home, container.juju_home,
                        host.tmp, container.juju_home,
                        host.juju_repository, container.juju_repository,
                        host.tmp, host.tmp,
                        os.path.dirname(args.test_plan), container.test_plans,
                        host.ssh_path, container.ssh_home,
                        container.name))
    test_plan = os.path.join(
        container.test_plans, os.path.basename(args.test_plan))
    bundle_file = ''
    if args.bundle_file:
        bundle_file = '--bundle {}'.format(args.bundle_file)
    shell_options = (
        'sudo cwr -F -l DEBUG -v {} {} {} --test-id {}'.format(
            bundle_file, ' '.join(host.controllers), test_plan, args.test_id))
    command = ('sudo docker run {} sh -c'.format(
        container_options).split() + [shell_options])
    run_command(command)
    print("User id: {} Group id: {}".format(os.getegid(), os.getpgrp()))
    # Copy logs
    if args.log_dir:
        copytree_force(host.test_results, args.log_dir,
                       ignore=shutil.ignore_patterns('static'))


def main():
    args = parse_args()
    log_level = max(logging.WARN - args.verbose * 10, logging.DEBUG)
    configure_logging(log_level)
    with env(args) as (host, container):
        with temp_juju_home(host.tmp_juju_home, args.juju_path):
            client = make_client(args.juju_path, host, args.log_dir)
            with client.bootstrap():
                if host.controllers:
                    if args.no_container is True:
                        run_test_without_container(host, args)
                    else:
                        run_test_with_container(host, container, args)


if __name__ == '__main__':
    main()
