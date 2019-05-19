import sqlite3
import threading
import logging
import datetime

class DataServer():
    """description of class"""
    __srcFileTableName ="sourcefiles"
    __queueTableName ="queue"
    __archiveTableName ="archives"

    def __init__(self, name, createNew):
        self.__log = logging.getLogger(__name__)
        self.__conn = sqlite3.connect(name, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        self.__conn.row_factory = sqlite3.Row
        self.__lock = threading.Lock()
        if(createNew):
            self.__InitDB()
        else:
            self.__checkWork()


    def __InitDB(self):
        try:
            self.__lock.acquire()
            self.__conn.executescript('''
            CREATE TABLE sourcefiles (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, size INTEGER);
            CREATE TABLE archives (id INTEGER, path TEXT);
            CREATE TABLE queue (id INTEGER, status INTEGER, count INTEGER, start timestamp, comment TEXT);
            ''')
            
        except Exception as err:
            self.__log.error("InitDB failed: %s" % err)
        finally:
            self.__isWork = False
            self.__lock.release()

    @property
    def IsWork(self):
        return self.__isWork

    def __checkWork(self):
        try:
            self.__lock.acquire()
            self.__conn.execute("select sourcefiles.id,path,size from sourcefiles inner join queue ON sourcefiles.id=queue.id where queue.status=0 or (queue.status<0 and queue.count<3)")
            
        except Exception as err:
            self.__log.error("Reading from DB failed: %s" % err)
            self.__isWork = False
        finally:
            self.__lock.release()
    
    def TryGetIdOfSourceFile(self, file):
        """looks up file in sorce file table and returns id or 0 if not present"""
        try:
            self.__lock.acquire()
            c = self.__conn.cursor()
            id = 0
            c.execute("select id from sourcefiles where path=?", (file,))
            row = c.fetchone()
            if row != None:
                id = row[0]

        except Exception as err:
             self.__log.exception("Error during look up file %s: %s", file, err)
        finally:
            self.__conn.commit()
            self.__lock.release()
        return id

    def AddMediaFile(self, fileList):
        """Add file to database"""
        try:
            self.__lock.acquire()
            c = self.__conn.cursor()
            for file, size, queue in fileList:
                c.execute("select id from sourcefiles where path=?", (file,))
                row = c.fetchone()
                alreadyPresent = row != None

                if not alreadyPresent:
                    #it may be among the archived files as well
                    c.execute("Select id from archives where path=?", (file,))
                    row = c.fetchone()
                    alreadyPresent = row != None

                if alreadyPresent:
                    self.__log.debug("File '%s' already present, skipping" % file)
                else:
                    c.execute("INSERT INTO sourcefiles (path,size) VALUES (?,?)", (file, size))
                    if queue:
                        self.__conn.execute("INSERT INTO queue (id,status,count,start) VALUES (?,?,?,?)", (c.lastrowid, 0, 0, 0))
                    self.__log.debug("File '%s' successfully put into DB" % file)
                    self.__isWork = True

        except Exception as err:
             self.__log.exception("put file '%s' to DB failed: %s" % file, err)
        finally:
            self.__conn.commit()
            self.__lock.release()
    def AddArchive(self, id, size, path, comment):
        """Add archived file to database. Params: id, path"""
        try:
            self.__lock.acquire()
            c = self.__conn.cursor()
            status = size

            if size > 0:
                status = 5
                c.execute("select id from archives where archives.path=?", (path,))
                if c.fetchone() == None:
                    c.execute("INSERT INTO archives (id,path) VALUES (?,?)", (id, path))
                else:
                    self.__log.debug("File is already present in DB")

            if id  > 0:
                c.execute("select status, count, start from queue where queue.id=?", (id,)) #check if id already present
                r2 = c.fetchone()
                if r2 == None:
                    self.__conn.execute("insert into queue (id,count) VALUES (?,0)",(id,))

            c.execute("update queue set status=?,start=?,comment=? where id=?", (status, datetime.datetime.now(), comment, id))
            self.__log.debug("File %i('%s') successfully put among archives with status=%i", id, path, status)

        except Exception as err:
             self.__log.exception("put archive file %i:'%s' to DB failed: %s", id, path, err)
        finally:
            self.__conn.commit()
            self.__lock.release()
    
    def RemoveMediaFile(self, file):
        try:
            self.__lock.acquire()
            c = self.__conn.cursor()
            c.execute("select id from sourcefiles where path=?", (file,))
            row = c.fetchone()
            if row != None:
                id = row[0]
                self.__log.debug("File to delete found in source table as id %s" % id)
                c.execute("delete from sourcefiles where id=?", (id,))
                c.execute("delete from queue where id=?", (id,))
            else:
                c.execute("select id from archives where path=?", (file,))
                row = c.fetchone()
                if row == None:
                    self.__log.debug("File %s was not found in database", file)
                else:
                    self.__log.debug("File to delete found in source table as id %s", row[0])
                    c.execute("delete from queue where id=?", (id,))

        except Exception as err:
             self.__log.exception("Remove file '%s' from DB failed: %s", file, err)
        finally:
            self.__conn.commit()
            self.__lock.release()

    def MoveMediaFile(self, src, dest):
        try:
            self.__lock.acquire()
            c = self.__conn.cursor()
            c.execute("select id from sourcefiles where path=?", (src,))
            row = c.fetchone()
            if row != None:
                id = row[0]
                self.__log.debug("File to move found in source table as id %s", id)
                c.execute("update sourcefiles set path=? where id=?", (dest, id))
            else:
                c.execute("select id from archives where path=?", (src,))
                row = c.fetchone()
                if row == None:
                    self.__log.debug("File %s was not found in database", src)
                else:
                    self.__log.debug("File to move found in archived table as id %s", row[0])
                    c.execute("update archives set path=? where id=?", (dest, row[0]))

        except Exception as err:
             self.__log.exception("Remove file '%s' from DB failed: %s", file, err)
        finally:
            self.__conn.commit()
            self.__lock.release()

    def ReserveNextFile(self, maxSize, worker):
        """search and lock next file for processing"""
        try:
            self.__lock.acquire()
            c = self.__conn.cursor()
            c.execute("select sourcefiles.id, path, size from sourcefiles join queue on queue.id=sourcefiles.id where sourcefiles.size <= ? and (queue.status=0 or (queue.status < 0 and queue.status >= -99 and queue.count < 3)) union select sourcefiles.id, path, size from sourcefiles where sourcefiles.size <= ? and sourcefiles.id not in (select id from queue) LIMIT 1", (maxSize, maxSize))
            row = c.fetchone()

            if row == None:
                self.__log.debug("No files to process!")
                return (0, None, 0)
            else:
                dt = datetime.datetime.now()
                id = row[0]
                c.execute("select status, count, start from queue where queue.id=?", (id,)) #check if id already present
                r2 = c.fetchone()
                if r2 == None:
                    self.__log.debug("Adding new file to queue: %i(%s)" % (id, row[1]))
                    self.__conn.execute("insert into queue (id,status,count,start) VALUES (?,1,1,?)",(id, dt))
                else:
                    self.__log.debug("File already present in queue: %i(%s) status=%i count=%i started=%s" % (id, row[1], r2[0], r2[1], r2[2]))
                    self.__conn.execute("update queue set status=1,count=count+1,start=? where queue.id=?", (dt, id))

                #self.__conn.execute("INSERT INTO queue (id,status,count,start) VALUES (?,1,1,?) ON CONFLICT(id) DO UPDATE SET status=1, count=count+1, started=?", (row[0], dt, dt))
                #self.__conn.execute("UPDATE OR REPLACE queue SET id=?, status=1, count=count+1, start=? where queue.id=?", (row[0], dt, row[0]))
                self.__log.debug("File %i:'%s' reserved for processing" % (id, row[1]))
                return tuple(row)

        except Exception as err:
             self.__log.exception("put file '%s' to DB failed: %s" % file, err)
        finally:
            self.__conn.commit()
            self.__lock.release()
