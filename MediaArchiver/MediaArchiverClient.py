import re
import os
import time
import rpyc
import logging
import threading
import subprocess

from ClientConfig import ClientConfig
from EncodingResult import EncodingResult
from MediaArchiverService import MediaArchiverService

class MediaArchiverClient:
    __id = 0
    def __init__(self, clientConfig):
        self.__id = MediaArchiverClient.__id
        MediaArchiverClient.__id = MediaArchiverClient.__id + 1

        self.__logger = logging.getLogger(__name__)
        self.__config = clientConfig
        self.__lock = threading.Lock()
        self.__event = threading.Event()
        self.__tmpFileName = ""
        self.__tmpOutFileName = os.path.join(clientConfig.WorkFolder, "tmpOutFile{}.mp4".format(self.__id))
        self.__connection : rpyc.connect_stream = None
        self.__serverInstance : MediaArchiverService = None
        self.__encodingResult : EncodingResult = None
        self.__process : subprocess.Popen = None
        self.__stopRequested = False
        self.__abortRequested = False
        self.__ffmpegParams = list()
        self.__myThread = threading.Thread(target=MediaArchiverClient.__mainloop, args=(self,), name=__name__)

    def __removeInputFile(self):
        if len(self.__tmpFileName) < 1:
            return

        while True:
            try:
                if os.path.isfile(self.__tmpFileName):
                    os.remove(self.__tmpFileName)
                break
            except :
                time.sleep(2)

    def __removeOutFile(self):
        while True:
            try:
                if os.path.isfile(self.__tmpOutFileName):
                    os.remove(self.__tmpOutFileName)
                break
            except :
                time.sleep(2)

    def __mainloop(self):
        waitResolution = 1
        state = 0
        state2 = 0
        waitctr = 0
        encStarted = False
        isNewFileToEncode = False

        while not (self.__stopRequested and state < 3 and encStarted == False):
            if state == -1:
                time.sleep(waitResolution)
                waitctr = waitctr - 1
                if waitctr <= 0:
                    state = 0
            elif state == 0:  # connect
                self.__connect()
                if self.IsConnected:
                    state = 1
                else:
                    waitctr = self.__config.SecondsToWaitBetweenConnectionRetries / waitResolution
                    state = -1

            elif state == 1: # download/upload file
                if state2 == 0: # downloading file
                    self.__removeInputFile()
                    self.__removeOutFile()
                    
                    isNewFileToEncode = self.__getFile()
                    if isNewFileToEncode:
                        if self.__abortRequested:
                            self.__logger.debug("File transfer aborted")
                            self.__encodingResult = EncodingResult(EncodingResult.ErrorCodes["ProcessAborted"], 0, "File transfer aborted by client")
                            state = 4
                        else:
                            self.__logger.debug("Local File Copy Finished.")
                            state = 2
                    else:
                        self.__logger.debug("No new file to process")
                        state = 2

                elif state2 == 1: # uploading file
                    state = 4

            elif state == 2: # disconnect
                self.__disconnect()
                if isNewFileToEncode:
                    state = 3
                else:
                    waitctr = self.__config.SecondsToWaitBetweenFileQueries / waitResolution
                    state = -1

            elif state == 3: # do processing
                if not encStarted:
                    self.__startEncoding()
                    encStarted = True
                    state2 = 1
                    isNewFileToEncode = False
                else:
                    p = self.__process
                    st = p.poll()
                    out = str.join("", p.stderr.read(1024).decode("utf-8"))
                    #self.__logger.debug("FFMPEG:%s", out)

                    if st == None:
                        if not self.__abortRequested:
                            time.sleep(1)
                        else:
                            self.__logger.debug("abort running encode process...")
                            self.__process.kill()
                            self.__process = None
                            self.__encodingResult = EncodingResult(EncodingResult.ErrorCodes["ProcessAborted"], 0, "Encoding aborted by client")
                            encStarted = False  # to quit thread
                            state2 = 0
                            state = 0
                    else:
                        ret = p.returncode
                        if ret == 0:
                            self.__encodingResult = self.__evaluateResult()
                            self.__logger.info("Encoding finished (%s), connecting again to server...", self.__encodingResult)

                        else:
                            self.__encodingResult = EncodingResult(EncodingResult.ErrorCodes["FFMPEGError"], ret, out)
                            self.__logger.debug("Error in encoding: %i, %s", ret, out)
                        
                        self.__process = None
                        state = 0
                
            elif state == 4:
                self.__putFile()
                self.__removeInputFile()
                self.__removeOutFile()
                self.__encodingResult = None
                encStarted = False
                state2 = 0
                state = 1
                self.__logger.debug("Prepared to receive next file..")

            else:
                raise RuntimeError("Illegal state {}".format(state))

        self.__logger.debug("Closing worker thread...")
        self.__disconnect()
        self.__removeInputFile()
        self.__removeOutFile()

    def __evaluateResult(self):
        """ Checks if result file is ok and returns a response object """
        err = EncodingResult.ErrorCodes["UnknownError"]
        message = "EV"
        fsize = os.stat(self.__tmpOutFileName).st_size
        finsize = os.stat(self.__tmpFileName).st_size
        if fsize > 0:
            resDurIn = self.readMediaDuration(self.__tmpFileName)
            resDurOut = self.readMediaDuration(self.__tmpOutFileName)
            diffDur = abs(resDurIn - resDurOut)
            if resDurIn < 0 or resDurOut < 0:
                err = EncodingResult.ErrorCodes["FFMPEGError"]
                message = "Duration of input or output clip could not be determined"
                self.__logger.error(message)
            elif diffDur > 3:
                err = EncodingResult.ErrorCodes["FFMPEGError"]
                message = "Duration difference is too much: {}".format(diffDur)
                self.__logger.error(message)
            else:
                if fsize >= finsize:
                    err = EncodingResult.ErrorCodes["CannotSaveSpace"]
                    message = ""
                else:
                    err = EncodingResult.ErrorCodes["NoError"]
                    message = ""

        else:
            self.__logger.debug("Encoding finished with success but file size is 0...")
            err = EncodingResult.ErrorCodes["FFMPEGError"]
            message = "Encoding Finished but file corrupt (size 0)"

        if err != EncodingResult.ErrorCodes["NoError"]:
            fsize = 0
        return EncodingResult(err, fsize, message)

    def readMediaDuration(self, file):
        # "Duration: 00:00:36.93, start: 1.040000, bitrate: 16355 kb/s"
        dur = -1
        cmd = [self.__config.FFProbePath, "-i", file]
        p = subprocess.Popen(cmd, stderr = subprocess.PIPE)
        errCode = p.wait()
        if errCode == 0:
            finfo = p.stderr.read(1024*1024).decode('utf-8')
            regex = re.compile(r"(?:Duration:\s*)(\d*):(\d*):(\d*).(\d*)", re.MULTILINE | re.IGNORECASE)
            matches = re.search(regex, finfo)
            if matches == None or len(matches.groups()) != 4:
                self.__logger.error("Duration could not be read in result media file")          
            else:
                c = [3600,60,1,0]
                i = 0    
                dur = 0
                for d in matches.groups():
                    dur += int(d) * c[i]
                    i += 1
                self.__logger.debug("Media duration %s: %s secs", file, dur)       
        return dur

    def __connect(self):
        with self.__lock:
            if self.__connection == None:
                try:
                    self.__logger.debug("Connecting to %s:%s...", self.__config.ServerAddress, self.__config.ServerPort)
                    self.__connection = rpyc.connect(self.__config.ServerAddress, self.__config.ServerPort)
                    #conn = rpyc.connect_by_service("MediaArchiver")
                    self.__serverInstance = self.__connection.root

                except Exception as e:
                    self.__logger.error("Could not connect to server: %s", e)
                    if self.__connection != None:
                        self.__connection.close()
                        self.__connection = None
                    self.__serverInstance = None

            self.IsConnected = self.__serverInstance != None

    def __disconnect(self):
        with self.__lock:
            if self.__connection != None:
                try:
                    self.__logger.debug("Disconnecting...")
                    self.__connection.close()

                except Exception as e:
                    self.__logger.error("Could not connect to server: %s", e)
                finally:
                    self.__connection = None
                    self.__serverInstance = None

            self.IsConnected = self.__serverInstance != None

    def __getFile(self):
        size, ffmpegParams, ext = self.__serverInstance.GetNextFile(self.__config.MaxFileSize)
        self.__ffmpegParams = list(ffmpegParams)
        self.__tmpFileName = os.path.join(clientConfig.WorkFolder, "tmpFile{}{}".format(self.__id, ext))

        ptr = 0
        if size > 0:
            with open(self.__tmpFileName, "wb") as handle:
                while size > ptr and not self.__abortRequested:
                    try:
                        data = self.__serverInstance.GetFileData()
                        handle.write(data)
                        ptr = ptr + len(data)
                    except :
                        self.__logger.exception("Exception during receiving file:")

        return size > 0
    
    def __putFile(self):
        self.__logger.debug("Signalling result %s", self.__encodingResult)
        self.__serverInstance.exposed_PutFile(self.__encodingResult.ErrorCode, self.__encodingResult.NewFileLength, self.__encodingResult.Comment)
        if self.__encodingResult != None and self.__encodingResult.ErrorCode == EncodingResult.ErrorCodes["NoError"]:
            chunkSize = self.__config.ChunkSize
            eof = False
            with open(self.__tmpOutFileName, "rb") as fh:
                while not eof and not self.__abortRequested:
                    data = fh.read(chunkSize)
                    eof = len(data) < chunkSize
                    self.__serverInstance.PutFileData(data)

    def __startEncoding(self):
        cmd = [self.__config.FFMpegPath, "-i", self.__tmpFileName]
        cmd.extend(self.__ffmpegParams)
        cmd.append(self.__tmpOutFileName)
        self.__logger.debug("Start encoding cmdline: %s", cmd)
        self.__process = subprocess.Popen(cmd, stderr = subprocess.PIPE)        
        
    def __onEncodingFinished(self, result:int):
        with self.__lock:
            self.__needToSendBackFile = result > 0
            if self.__serverInstance != None:
                self.__serverInstance.exposed_PutFile(result)

    def Start(self):
        with self.__lock:
            if not self.__myThread.is_alive():
                self.__logger.debug("Starting worker thread...");
                self.__myThread.start()

    def Abort(self):     
        with self.__lock:
            self.__stopRequested = True
            if self.__myThread.is_alive():
                self.__logger.debug("Stopping worker thread...");
                self.__abortRequested = True

    def StopWhenFinished(self):
        with self.__lock:
            self.__stopRequested = True

    def IsBusy(self):
        with self.__lock:
            return self.__myThread.is_alive()

    def Shutdown(self):
        self.Abort()
        self.__myThread.join()

if __name__ == "__main__":
    fh = logging.FileHandler('MediaArchiverClient.log')
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    fh.setLevel(logging.DEBUG)
    logging.getLogger('').addHandler(fh)
    loglevel = logging.DEBUG
    logging.getLogger().setLevel (loglevel)

    clientConfig = ClientConfig()
    client = MediaArchiverClient(clientConfig)
    client.Start()

    print("Press Ctrl+C to stop client!")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt as e:
        pass

    client.StopWhenFinished()
    print("Waiting to finish current encoding process. For abort press Ctrl+C")

    try:
        while client.IsBusy():
            time.sleep(1)
    except KeyboardInterrupt as e:
        pass

    client.Shutdown()
