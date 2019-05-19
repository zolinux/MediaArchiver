import logging
import threading
import rpyc
import rpyc.utils.factory
#from rpyc.utils.registry import REGISTRY_PORT, DEFAULT_PRUNING_TIMEOUT
#from rpyc.utils.registry import UDPRegistryServer, TCPRegistryServer 

from MediaArchiverService import MediaArchiverService

class RPCClientListener():
    """thread listens for incoming connections and starts an RPC server"""
    
    def __init__(self, daemon, port):
        self.__daemon = daemon
        self.__port = port
        self.__rpcThreads = list()
        self.__stopRequested = False
        self.__pendingConnection = None
        self.__logger = logging.getLogger(__name__)
        self.__lock = threading.Lock()
        self.__event = threading.Event()
        self.__myThread = threading.Thread(target=RPCClientListener.__mainloop, args=(self,), name=__name__)
        self.__myThread.start()
        self.__event.set()

    def __mainloop(self):
        #regserver = TCPRegistryServer('0.0.0.0',port = REGISTRY_PORT, pruning_timeout = DEFAULT_PRUNING_TIMEOUT, logger = logging.getLogger("RPYCRegServer"))
        #servthread = threading.Thread(target=regserver.start, args=(), name="RPYCRegServer")
        #servthread.start()

        self.__logger.debug("Dispatcher thread started.")
        while True:
            self.__event.wait()
            self.__event.clear()

            if self.__stopRequested:
                self.__logger.debug("Processing Stop request")
                break;
            else:
                service = rpyc.utils.helpers.classpartial(MediaArchiverService, self, self.__daemon)
                t = rpyc.utils.server.ThreadedServer(service, port=self.__port) #, registrar=regserver
                self.__rpcThreads.append(t)
                t.start()
                
        #regserver.close()
        #servthread.join()
        for rpc in self.__rpcThreads:
            rpc.close()
        self.__rpcThreads.clear()
        self.__logger.debug("Dispatcher thread stopped.")

    def Shutdown(self):
        self.__stopRequested = True
        self.__event.set()
        self.__myThread.join()

    def OnConnect(self, thrd):
        self.__logger.debug("Client Connected, opening new server...")

    def OnDisconnect(self, thrd):
        self.__logger.debug("Client Disconnected.")
