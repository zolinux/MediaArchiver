from configparser import ConfigParser

class ServerConfig():
    """Opens and reads config file for server"""
    __configFileName = "MediaArchiver.ini"

    def __init__(self, *args, **kwargs):
        self.__parser = ConfigParser(allow_no_value=True)
        self.__parser.read(self.__configFileName)
        self.Port = (int)(self.__parser.get("Server", "Port"))
        self.Folders = self.__parser.get("Server", "Folders").split(';')
        self.FileExtensions = self.__parser.get("Server", "Extensions").upper().split(';')
        self.VideoCodec = self.__parser.get("Server", "VideoCodec")
        self.CRF = self.__parser.get("Server", "CRF")
        self.FFProbePath = self.__parser.get("Server", "FFProbePath")
        self.AudioBitRate = self.__parser.get("Server", "AudioBitRate")
        self.AudioCodec = self.__parser.get("Server", "AudioCodec")
        self.StartLocalClient = self.__parser.get("Server", "StartLocalClient") == "True"
        self.ChunkSize = int(self.__parser.get("Server", "ChunkSize"))
        self.FinalExtension = self.__parser.get("Server", "FinalExtension")
        self.WorkFolder = self.__parser.get("Server", "WorkFolder")
        self.SkipFilesWithVideoCodec = self.__parser.get("Server", "SkipFilesWithVideoCodec").upper().split(';')
        self.ArchivedFileSuffix = self.__parser.get("Server", "ArchivedFileSuffix").strip()

