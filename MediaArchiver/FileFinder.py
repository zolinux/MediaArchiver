import logging
import threading
from os import path
import os

from DataServer import DataServer

class FileFinder():
    """description of class"""

    def __init__(self, fileFoundReportee, folders, extensions):
        self.__log = logging.getLogger(__name__)
        self.__parent = fileFoundReportee
        self.__folders = folders
        self.__exts = extensions
        self.__stopReq = False
        self.__myThread = threading.Thread(target=FileFinder.__mainloop, args=(self,), name=__name__)
        self.__myThread.start()

    def __mainloop(self):
        self.__log.debug("Thread started")
        for dir_ in self.__folders:
            self.__processFolder(dir_)
            if self.__stopReq:
                break

    def __processFolder(self, folder):
        if self.__stopReq:
            return

        self.__log.debug("Entering folder %s" % folder)
        for root, dirs, files in os.walk(folder):
            # adding matching files to the list
            newFileList = []
            for f in files:
                for e in self.__exts:
                    if f.upper().endswith(e):
                        newFileList.append(os.path.join(root, f))
                        break

            if len(newFileList) > 0:
                self.__parent.ReportFile(newFileList)

