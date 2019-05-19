import logging
import glob
import threading
import os
import re
import subprocess
import xmlrpc.server
from os import path

try:
    import watchdog
    watchdogEventCHandler = events.PatternMatchingEventHandler
    watchdogPresent = True
except:
    watchdogPresent = False
    watchdogEventCHandler = object

from ServerConfig import ServerConfig
from RPCClientListener import RPCClientListener
from DataServer import DataServer
from FileFinder import FileFinder
from collections import deque
from EncodingResult import EncodingResult

class Daemon(watchdogEventCHandler):
    """main class for mediaarchiver daemon"""

    def __init__(self, servConf, dataServer):
        l=[]
        for a in servConf.FileExtensions:
            l.append("*%s" % a)

        if watchdogPresent == True:
            super().__init__(ignore_directories=True, patterns=l)

        self.__logger = logging.getLogger(__name__)
        self.__serverConfig = servConf
        self.__ds = dataServer
        self.__event = threading.Event()
        self.__lock = threading.Lock()
        self.__cond = threading.Condition(self.__lock)
        self.__fileAddQueue = deque()
        self.__fileMovedQueue = deque()
        self.__fileDeletedQueue = deque()
        self.__fileFinishedQueue = deque()
        self.__filesInTransfer = []
        self.__fileMoveThreads = []
        if watchdogPresent:
            self.__observer = observers.Observer()

    def GetFFMPEGParams(self):
        par = ["-preset", "veryfast", "-c:v", self.__serverConfig.VideoCodec,
              "-c:a", self.__serverConfig.AudioCodec, "-crf", self.__serverConfig.CRF,
             "-b:a", self.__serverConfig.AudioBitRate]
        return par

    def Main(self, forceSearchFiles):
        self.__logger.debug("Starting main daemon operations...")
        if forceSearchFiles:
            FileFinder(self, self.__serverConfig.Folders, self.__serverConfig.FileExtensions)
        if watchdogPresent:
            for folder in self.__serverConfig.Folders:
                self.__logger.debug("watching folder: %s", folder)
                self.__observer.schedule(self, folder, True)
                self.__observer.start()
        
        self.__RPCDispatcher = RPCClientListener(self, self.__serverConfig.Port)

        self.__cond.acquire()
        while True:
            try:
                self.__cond.wait()
                self._LoopInside()
            except KeyboardInterrupt:
                break;
            except Exception as e:
                self.__logger.exception("Error: %s" % e)

        self.__logger.debug("Shutting down. Waiting running threads to finish.")
        for moveThread in self.__fileMoveThreads:
            moveThread.join()

    def _LoopInside(self):
        while(len(self.__fileAddQueue) > 0):
            t = self.__fileAddQueue.pop()
            for f in t:
                id = self._NeedArchive(f[0])
                if id > 0:
                    self.__ds.AddArchive(id, f[1], f[0], None)
                elif id == 0:
                    self.__ds.AddMediaFile([f])
                else:
                    self.__logger.debug("File %s ignored", f[0])

        while(len(self.__fileMovedQueue) > 0):
            t = self.__fileMovedQueue.pop()
            self.__ds.MoveMediaFile(t[0], t[1])

        while(len(self.__fileDeletedQueue) > 0):
            t = self.__fileDeletedQueue.pop()
            self.__ds.RemoveMediaFile(t)

        while(len(self.__fileFinishedQueue) > 0):
            t = self.__fileFinishedQueue.pop()
            #self.__ds....(t) #start thread to copy file?
            try:
                dest = path.join(path.dirname(t['path']), path.basename(t['of']))
                self.__logger.debug("moving file %i:<%s> to <%s>..." % (t['id'], t['of'], dest))
                os.utime(t['of'], (t['time'],t['time']))
                thr = threading.Thread(target=self.__MoveFileAndAddToDatabase, args=(t['of'], dest, t['id'], t['size'], t['comment']))
                self.__fileMoveThreads.append(thr)
                thr.start()
            except Exception as e:
                self.__logger.error("Could not copy/add archived file: %s", e)

    def __MoveFileAndAddToDatabase(self, src, dest, id, size, comment):
        try:
            os.rename(src, dest)
            self.__ds.AddArchive(id, size, dest, comment)
        except Exception as e:
            self.__logger.error("Error during moving archived file to destination or putting to DB: %s", e)

    def _NeedArchive(self, path):
        id = -1
        pf = os.path.splitext(path)
        if pf[0].endswith(self.__serverConfig.ArchivedFileSuffix):
            srcFile = pf[0].replace(self.__serverConfig.ArchivedFileSuffix, "")
            # look for original file with arbitrary extension present
            # if yes, put that file into source table and get the id
            # if not, we consider having no original file anymore, leave id=0
            originalFile = glob.glob(srcFile + ".*")
            if len(originalFile) > 1:
                self.__logger.warn("More than 1 original file found for '%s'", path)
            elif len(originalFile) < 1:
                self.__logger.debug("No original file found for '%s'", path)
                id = 0
            else:
                of = originalFile[0]
                while id <= 0:
                    id = self.__ds.TryGetIdOfSourceFile(of)
                    if id <= 0:
                        tupleToAdd=(of,0,False)
                        self.__ds.AddMediaFile([tupleToAdd])      # hack: add original file to media file list even if it does not exist

            self.__logger.debug("Source file ID of '%s' -> %i", srcFile, id)

        else:
            #  Stream #0:0[0x1011]: Video: h264
            regex = re.compile(r"(?:Stream\s.*Video:\s*)(\w*)", re.MULTILINE | re.IGNORECASE)
            #outputP = subprocess.run([self.__serverConfig.FFProbePath, "-i", path], stderr=subprocess.PIPE)
            outputP = subprocess.Popen([self.__serverConfig.FFProbePath, path], stderr=subprocess.PIPE, stdout = subprocess.DEVNULL)
            outputP.wait()
            output = outputP.stderr.read(1024*1024).decode('utf-8')
            matches = re.search(regex, output)
            if outputP.returncode != 0:
                self.__logger.debug("FFProbe return error: %s", output)
            else:
                if matches == None:
                    self.__logger.error("File not supported by FFMpeg: %s", path)
                elif len(matches.groups()) > 1:
                    self.__logger.debug("File %s using has multiple video streams video codec %s", path, matches.groups())
                else:
                    codec = matches.group(1).upper()
                    if not codec in self.__serverConfig.SkipFilesWithVideoCodec:
                        id = 0
                        self.__logger.debug("File %s using video codec %s", path, codec)
                    else:
                        self.__logger.debug("File %s ignored due to configuration", path)
        return id

    def ReportFile(self, file, queue=False):
        """ Add a file found by FileFinder to the DB """
        if not isinstance(file, list):
            file = [file]
        
        lstFiles=list()

        for f in file:
            if not os.access(f, os.R_OK):
                self.__logger.error("File '%s' is not readable", f)
            else:
                lstFiles.append((f, os.path.getsize(f), queue))
        if len(lstFiles) > 0:
            with self.__cond:
                self.__fileAddQueue.appendleft(lstFiles)
                self.__cond.notify_all()
    
    def ReportFileMoved(self, src, dest):
        with self.__cond:
            self.__fileMovedQueue.appendleft((src, dest))
            self.__cond.notify_all()
       
    def ReportFileDeleted(self, file):
        with self.__cond:
            self.__fileDeletedQueue.appendleft(file)
            self.__cond.notify_all()

    def on_created(self, event):
        self.__logger.debug("New file detected: %s" % event.src_path)
        self.ReportFile(event.src_path, True)

    def on_moved(self, event):
        self.__logger.debug("File Move detected: %s" % event.src_path)
        self.ReportFileMoved(event.src_path, event.dest_path)

    def on_deleted(self, event):
        self.__logger.debug("File Move detected: %s" % event.src_path)
        self.ReportFileDeleted(event.src_path)

    def GetNextFile(self, maxLength, clientAddr):
        """ Returns (id, size) """
        instF = next((item for item in self.__filesInTransfer if item["client"] == clientAddr), None)
        if instF != None:
            self.__logger.debug("New request for file means client had issue or was just restarted. Cancelling previous running job")
            with self.__cond:
                self.__filesInTransfer.remove(instF)
                self.__ds.AddArchive(instF['id'], EncodingResult.ErrorCodes["ProcessAborted"], None, "Server cancelled")

        self.__logger.debug("Received Request for a file with max length of %u bytes" % maxLength)
        ext = "bin"
        id, path, size = self.__ds.ReserveNextFile(maxLength, clientAddr)
        if path != None:
            ext = os.path.splitext(path)[1]
            fh = open(path, 'rb');
            self.__logger.debug("File %i opened for reading by %s", id, clientAddr)
            time = os.path.getmtime(path)
            self.__filesInTransfer.append({'id':id, 'path': path, 'size' : size, 'client' : clientAddr, 'offset':0, 'fh':fh, 'dir':0, 'time':time})
            
        return (id, size, ext)

    def GetFileData(self, clientAddr):
        instF = next(item for item in self.__filesInTransfer if item["client"] == clientAddr)
        if instF == None:
            self.__logger.error("Client %s could not be found in the list of open files" % clientAddr)
            raise EnvironmentError("No file opened by client")
        
        fh = instF['fh']
        data = fh.read(self.__serverConfig.ChunkSize)
        if len(data) < self.__serverConfig.ChunkSize:
            self.__logger.debug("File %i read finished", instF['id'])
            fh.close()
        instF['offset'] = instF['offset'] + len(data)
        return data

    def PutFile(self, result, clientAddr):
        """ Client calls this function to signal end of encoding
            result: instance of EncodingResult
        """
        instF = next((item for item in self.__filesInTransfer if item["client"] == clientAddr), None)
        if instF == None:
            self.__logger.error("Client %s could not be found in the list of open files" % clientAddr)
            raise EnvironmentError("No file opened by client")

        self.__logger.debug("Client %s finished encoding (file %i) with %i" % (clientAddr, instF['id'], result.ErrorCode))
        if result.ErrorCode < 0:
            with self.__cond:
                self.__filesInTransfer.remove(instF)
                self.__ds.AddArchive(instF['id'], result.ErrorCode, None, result.Comment)
        else:
            fileName = path.join(self.__serverConfig.WorkFolder, path.basename(path.splitext(instF['path'])[0]) + self.__serverConfig.ArchivedFileSuffix + self.__serverConfig.FinalExtension)
            fh = open(fileName, 'wb')
            instF['fh'] = fh
            instF['offset'] = 0
            instF['dir'] = 1
            instF['of'] = fileName
            instF['size'] = result.NewFileLength
            instF['error'] = result.ErrorCode
            instF['comment'] = result.Comment
        
    def PutFileData(self, data, clientAddr):
        instF = next(item for item in self.__filesInTransfer if item["client"] == clientAddr)
        if instF == None:
            self.__logger.error("Client %s could not be found in the list of open files" % clientAddr)
            raise EnvironmentError("No file opened by client")

        fh = instF['fh']
        fh.write(data)
        instF['offset'] = instF['offset'] + len(data)
        if instF['offset'] == instF['size']:
            self.__logger.debug("File transfer from %s has been finished." % clientAddr)
            fh.close()
            with self.__cond:
                self.__fileFinishedQueue.appendleft(instF)
                self.__filesInTransfer.remove(instF)
                self.__cond.notify_all()

