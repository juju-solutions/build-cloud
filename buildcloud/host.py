
__metaclass__ = type


class Host:

    def __init__(self, tmp_juju_home, juju_repository, test_results, tmp,
                 ssh_path, root, models):
        self.tmp_juju_home = tmp_juju_home
        self.juju_repository = juju_repository
        self.test_results = test_results
        self.tmp = tmp
        self.ssh_path = ssh_path
        self.root = root
        self.models = models
