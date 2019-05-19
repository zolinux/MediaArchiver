import rpyc
from EncodingResult import EncodingResult

class MediaArchiverService(rpyc.Service):
    def __init__(self, rpcListener, daemon):
        self.__daemon = daemon
        self.__rpcListener = rpcListener
        self.__client_address = None

    def on_connect(self, conn):
        # code that runs when a connection is created
        # (to init the service, if needed)
        self._connection = conn
        self.__client_address = conn._channel.stream.sock.getpeername()[0]
        self.__rpcListener.OnConnect(self)

    def on_disconnect(self, conn):
        # code that runs after the connection has already closed
        # (to finalize the service, if needed)
        self.__rpcListener.OnDisconnect(self)
        self.__client_address = None

    def exposed_GetNextFile(self, maxLength):
        id, size, ext = self.__daemon.GetNextFile(maxLength, self.__client_address)
        return (size, self.__daemon.GetFFMPEGParams(), ext)

    def exposed_GetFileData(self):
        data = self.__daemon.GetFileData(self.__client_address)  
        return data

    def exposed_PutFile(self, result, newFileSize, comment):
        return self.__daemon.PutFile(EncodingResult(result, newFileSize, comment), self.__client_address)

    def exposed_PutFileData(self, data):
        return self.__daemon.PutFileData(data, self.__client_address)




