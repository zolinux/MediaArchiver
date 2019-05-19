import unittest

from EncodingResult import EncodingResult
from ServerConfig import ServerConfig
from DataServer import DataServer
from Daemon import Daemon

import logging

class Test_TestDaemon(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.servConfig = ServerConfig()
        ds = DataServer("MediaArchiver.db", False)
        self.daemon = Daemon(self.servConfig, ds)
        self.client = "test:0000"
        self.size = 0
        return super().setUpClass()

    def test_ReadFile1(self):
        id, size = self.daemon.GetNextFile(500*1024*1024, self.client)
        fh = open("tmp.bin", 'wb')
        currLen = 0
        while currLen < size:
            data = self.daemon.GetFileData(self.client)
            fh.write(data)
            currLen = currLen + len(data)
        
        fh.close()
        Test_TestDaemon.size = currLen
        print ("Uploading...")

    def test_WriteFile1(self):
        fh = open("tmp.bin", 'rb')
        self.daemon.PutFile(EncodingResult(0, Test_TestDaemon.size, ""), self.client)
        currLen = 0
        chunk = 16384
        while True:
            data = fh.read(chunk)
            self.daemon.PutFileData(data, self.client)
            if len(data) < chunk:
                break
            currLen = currLen + len(data)
        
        fh.close()
        print ("Uploading finished")
        self.daemon._LoopInside()

if __name__ == '__main__':
    fh = logging.FileHandler('MediaArchiver.log')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    fh.setLevel(logging.DEBUG)
    logging.getLogger('').addHandler(fh)
    loglevel = logging.DEBUG
    logging.getLogger().setLevel (loglevel)

    unittest.main()
