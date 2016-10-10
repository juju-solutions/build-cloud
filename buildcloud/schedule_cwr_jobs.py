#!/usr/bin/env python

from argparse import ArgumentParser
from collections import namedtuple
import os
import yaml

from jenkins import Jenkins

from utility import generate_test_id


Credentials = namedtuple('Credentials', ['user', 'password'])


def parse_args(argv=None):
    parser = ArgumentParser()
    parser.add_argument(
        'test_plan_dir', help='File path to test plan directory.')
    parser.add_argument(
        '--user', default=os.environ.get('JENKINS_USER'))
    parser.add_argument(
        '--password', default=os.environ.get('JENKINS_PASSWORD'))
    parser.add_argument(
        '--cwr-test-token', default=os.environ.get('CWR_TEST_TOKEN'))
    parser.add_argument(
        'controllers', nargs='+', help='List of controllers. ')
    parser.add_argument(
        '--test_plans', nargs='+',
        help='List of test plan files.  Instead of scheduling all the tests, '
             'this can be use to restrict the test plan files. If this is '
             'not set, all the test will be scheduled.')
    args = parser.parse_args(argv)
    if not args.cwr_test_token:
        parser.error("Please set the cwr-test Jenkins job token by "
                     "exporting the CWR_TEST_TOKEN environment variable.")
    return args


def make_parameters(test_plan, args, controller, test_id):
    with open(test_plan, 'r') as f:
        plan = yaml.load(f)
    parameters = {
        'test_plan': test_plan,
        'controllers': controller,
        'bundle_name': plan['bundle_name'],
        'bundle_file': plan.get('bundle_file'),
        'test_id': test_id,
    }
    # Remove empty values
    parameters = {k: v for k, v in parameters.items() if v}
    return parameters


def get_test_plans(args):
    test_plans = args.test_plans or os.listdir(args.test_plan_dir)
    for test_plan in test_plans:
        if not test_plan.endswith('.yaml'):
            continue
        test_plan = os.path.join(args.test_plan_dir, test_plan)
        yield test_plan


def get_credentials(args):
    if None in (args.user, args.password):
        raise ValueError(
            'Jenkins username and/or password not supplied.')
    return Credentials(args.user, args.password)


def get_job_name(controller):
    controller = controller.lower()
    if 'aws' in controller:
        return 'cwr-aws'
    if 'gce' in controller:
        return 'cwr-gce'
    if 'joyent' in controller:
        return 'cwr-joyent'
    if 'azure' in controller:
        return 'cwr-azure'
    if 'power8' in controller:
        return 'cwr-maas-power8'
    if 'ob-maas' in controller:
        return 'cwr-maas-ob'
    raise Exception('Unknown Jenkins job name requested')


def build_jobs(credentials, test_plans, args):
    jenkins = Jenkins('http://juju-ci.vapour.ws:8080', *credentials)
    for test_plan in test_plans:
        test_id = generate_test_id()
        for controller in args.controllers:
            job_name = get_job_name(controller)
            parameter = make_parameters(test_plan, args, controller, test_id)
            jenkins.build_job(job_name, parameter, token=args.cwr_test_token)


def main():
    args = parse_args()
    credentials = get_credentials(args)
    test_plans = get_test_plans(args)
    build_jobs(credentials, test_plans, args)


if __name__ == '__main__':
    main()
