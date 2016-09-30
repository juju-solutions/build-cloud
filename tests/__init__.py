import logging
from StringIO import StringIO
import unittest


class TestCase(unittest.TestCase):

    def setUp(self):
        logger = logging.getLogger()
        self.addCleanup(setattr, logger, "handlers", logger.handlers)
        logger.handlers = []
        self.log_stream = StringIO()
        handler = logging.StreamHandler(self.log_stream)
        formatter = logging.Formatter("%(name)s %(levelname)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
