from configparser import ConfigParser

class ClientConfig():
    """Opens and reads config file for server"""
    __configFileName = "MediaArchiver.ini"

    def __init__(self, *args, **kwargs):
        self.__parser = ConfigParser(allow_no_value=True)
        self.__parser.read(self.__configFileName)
        self.SecondsToWaitBetweenConnectionRetries = float(self.__parser.get("Client", "SecondsToWaitBetweenConnectionRetries"))
        self.SecondsToWaitBetweenFileQueries = int(self.__parser.get("Client", "SecondsToWaitBetweenFileQueries"))
        self.ChunkSize = int(self.__parser.get("Client", "ChunkSize"))
        self.MaxFileSize = int(self.__parser.get("Client", "MaxFileSize"))
        self.WorkFolder = self.__parser.get("Client", "WorkFolder")
        self.FFMpegPath = self.__parser.get("Client", "FFMpegPath")
        self.FFProbePath = self.__parser.get("Client", "FFProbePath")
        self.ServerAddress = self.__parser.get("Client", "ServerAddress")
        self.ServerPort = (int)(self.__parser.get("Client", "ServerPort"))


