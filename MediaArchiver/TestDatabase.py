import DataServer
import unittest

class Test_TestDatabase(unittest.TestCase):
    def setUp(self):
        self.ds = DataServer.DataServer("MediaArchiver.db", False)
        return super().setUp()

    def test_Reserve(self):
        ret = self.ds.ReserveNextFile(1000*1024*1024,"test:0000")
        print("Result: %s" % (ret,))

if __name__ == '__main__':
    unittest.main()
