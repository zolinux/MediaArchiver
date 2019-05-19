import unittest

from EncodingResult import EncodingResult
from ClientConfig import ClientConfig
from MediaArchiverClient import MediaArchiverClient

import logging

class Test_TestClient(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.config = ClientConfig()
        self.client = MediaArchiverClient(self.config)
        return super().setUpClass()

    def test_EvaluateResult(self):
        dur = self.client.readMediaDuration("C:\\Users\\Zoli\\Pictures\\test\\2004Balcsi.avi")
        self.assertGreater(dur, 0)

if __name__ == '__main__':
    fh = logging.FileHandler('MediaArchiver.log')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    fh.setLevel(logging.DEBUG)
    logging.getLogger('').addHandler(fh)
    loglevel = logging.DEBUG
    logging.getLogger().setLevel (loglevel)

    unittest.main()
