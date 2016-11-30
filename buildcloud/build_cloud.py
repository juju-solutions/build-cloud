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
    generate_controller_names,
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
        '--controllers_bootstrapped', action='store_true',
        help="If set, it won't bootstrap the controllers")
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
    parser.add_argument('--bootstrap-constraints',
                        help='Bootstrap machine constraints')
    parser.add_argument('--constraints',
                        help='Model constraints', default='mem=3G')
    parser.add_argument('--cwr-path',
                        help='Path to cwr. If path is provided, it will '
                             'execute it with python')
    # TODO: this should be updated to support a config per controller instead
    # of a single config for all controllers.
    parser.add_argument('--config', default='test-mode=true',
                        help='Specify a controller configuration file')
    # CWR options
    parser.add_argument('--results-dir',
                        help="Directory to store the test results.")
    parser.add_argument('--bucket',
                        help='Store / find results in this S3 bucket '
                             'instead of locally')
    parser.add_argument('--s3-creds',
                        help='Path to config file containing S3 credentials')
    parser.add_argument('--results-per-bundle', type=int,
                        help='Maximum number of results to list per bundle in '
                             'the index.  Older results will not be listed, '
                             'but the result reports themselves will be '
                             'preserved.')
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

        if args.controllers_bootstrapped:
            new_names = args.controllers
        else:
            new_names = generate_controller_names(args.controllers)

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
                              name='jujusolutions/cwrbox',
                              home=container_home,
                              ssh_home=container_ssh_home,
                              juju_home=container_juju_home,
                              test_results=container_test_results,
                              juju_repository=container_repository,
                              test_plans=container_test_plans)
        yield host, container


def get_cwr_options(args, host, container=None):
    options = []
    if not args.bucket and not args.results_dir:
        args.results_dir = host.test_results
    s3_creds = args.s3_creds
    if not args.no_container and args.s3_creds:
        if container is None:
            raise ValueError('Container is not set.')
        s3_creds = os.path.join(
            container.home, os.path.basename(args.s3_creds))
    arg_list = [
        [args.bundle_file, '--bundle'],
        [args.results_dir, '--results-dir'],
        [args.bucket, '--bucket'],
        [s3_creds, '--s3-creds'],
        [True, '--s3-private'],
        [args.results_per_bundle, '--results-per-bundle'],
    ]
    for arg, opt in arg_list:
        if arg:
            options.append(opt)
            if not isinstance(arg, bool):
                options.append(arg)
    options = ' '.join(options) if options else ''
    return options


def get_cwr_path(args):
    cwr_path = 'cwr'
    if args.cwr_path:
        cwr_path = 'python {}'.format(args.cwr_path)
    return cwr_path


def run_test_without_container(host, args, bootstrapped_controllers):
    logging.debug('Running test without a container.')
    cwr_options = get_cwr_options(args, host)
    cwr_path = get_cwr_path(args)
    cmd = ('{} -F -l DEBUG -v {} {} --test-id {} {}'.
           format(cwr_path, ' '.join(bootstrapped_controllers), args.test_plan,
                  args.test_id, cwr_options))
    run_command(cmd)


def run_test_with_container(host, container, args, bootstrapped_controllers):
    logging.debug("Host data: ", host)
    logging.debug("Container data: ", container)
    run_command('sudo docker pull {}'.format(container.name))
    s3_creds = ''
    if args.s3_creds:
        s3_creds = '-v {}:{} '.format(
            args.s3_creds,
            os.path.join(container.home, os.path.basename(args.s3_creds)))
    container_options = (
        '--rm '
        '--entrypoint bash '  # override jujubox entrypoint
        '-u {} '
        '-e HOME={} '
        '-e JUJU_HOME={} '
        '-e JUJU_DATA={} '
        '-e PYTHONPATH={} '
        '-w {} '
        '-v {}:{} '   # Test result location
        '-v {}:{} '   # Temp Juju home
        '-v {}/.deployer-store-cache:{}/.deployer-store-cache '
        '-v {}:{} '   # Repository location
        '-v {}:{} '   # Temp location.
        '-v {}:{} '   # Test plan
        '{}'          # S3 creds
        '-v {}:{} '   # ssh path
        '-t {} '.format(container.user,
                        container.home,
                        container.juju_home,
                        container.juju_home,
                        os.path.join(container.home, 'cloud-weather-report'),
                        container.home,
                        host.test_results, container.test_results,
                        host.tmp_juju_home, container.juju_home,
                        host.tmp, container.juju_home,
                        host.juju_repository, container.juju_repository,
                        host.tmp, host.tmp,
                        os.path.dirname(args.test_plan), container.test_plans,
                        s3_creds,
                        host.ssh_path, container.ssh_home,
                        container.name))
    test_plan = os.path.join(
        container.test_plans, os.path.basename(args.test_plan))
    cwr_options = get_cwr_options(args, host, container=container)
    cwr_path = os.path.join(
        container.home, 'cloud-weather-report/cloudweatherreport/run.py')
    shell_options = (
        'sudo juju --version && sudo -HE env PATH=$PATH PYTHONPATH=$PYTHONPATH'
        ' python2 {} -F -l DEBUG -v {} {} --test-id {} {}'.format(
            cwr_path, ' '.join(bootstrapped_controllers), test_plan,
            args.test_id, cwr_options))
    # The '-c [shell_options]' will get passed to to our entrypoint (bash)
    command = ("sudo docker run {} -c ".format(
        container_options).split() + [shell_options])
    run_command(command)

    # Copy logs
    if args.log_dir:
        copytree_force(host.test_results, args.log_dir,
                       ignore=shutil.ignore_patterns('static'))


def run_test(host, args, bootstrapped_controllers, container):
    if args.no_container is True:
        run_test_without_container(
            host, args, bootstrapped_controllers)
    else:
        run_test_with_container(
            host, container, args, bootstrapped_controllers)


def main():
    args = parse_args()
    log_level = max(logging.WARN - args.verbose * 10, logging.DEBUG)
    configure_logging(log_level)
    with env(args) as (host, container):
        with temp_juju_home(host.tmp_juju_home, args.juju_path):
            client = make_client(args.juju_path, host, args.log_dir,
                                 args.bootstrap_constraints,
                                 args.constraints, args.config)
            if args.controllers_bootstrapped:
                logging.info('Using already bootstrapped controller:{}'.format(
                    args.controllers))
                run_test(host, args, args.controllers, container)
            else:
                logging.info('Bootstrapping: {}'.format(args.controllers))
                with client.bootstrap() as bootstrapped_controllers:
                    logging.info('Bootstrapped: {}'.format(
                        bootstrapped_controllers))
                    if bootstrapped_controllers:
                        run_test(host, args, bootstrapped_controllers,
                                 container)


if __name__ == '__main__':
    main()
