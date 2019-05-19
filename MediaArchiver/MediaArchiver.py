import sys
import logging
from os import environ, path
from getopt import getopt
try:
    from daemoniker import Daemonizer
    daemonize = True
except:
    daemonize = False;

from ServerConfig import ServerConfig
from Daemon import Daemon
from DataServer import DataServer
from FileFinder import FileFinder

if __name__ == "__main__":
    opt, o = getopt(sys.argv[1:],"dl:r")

    dbName = "MediaArchiver.db"
    forceSearchFiles = False
    noExistingDB = False

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    daemon = False
    forceSearchFiles = False

    # create console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    # create formatter and add it to the handlers
    ch.setFormatter(formatter)
    # add the handlers to the logger
    logging.getLogger('').addHandler(ch)    
    logger = logging.getLogger(__name__)

    for option in opt:
        if option[0] == "-l":
            fh = logging.FileHandler('MediaArchiver.log')
            fh.setFormatter(formatter)
            fh.setLevel(logging.DEBUG)
            logging.getLogger('').addHandler(fh)
            loglevel = int(option[1])
            logging.getLogger().setLevel (loglevel)
            logger.setLevel(loglevel)
            ch.setLevel(loglevel)
            continue

        if option[0] == "-d":
            daemon = True
            continue

        if option[0] == "-r":
            forceSearchFiles = True
            continue

    if daemon:
        if not path.isfile(dbName):
            logger.debug("No Database found")
            noExistingDB = True
            forceSearchFiles = True

        servConfig = ServerConfig()
        ds = DataServer(dbName, noExistingDB)
        
        if daemonize:
            #with Daemonizer() as (is_setup, daemonizer):
            #    if is_setup:
            #        # This code is run before daemonization.
            #        pass #do_things_here()

            #    # We need to explicitly pass resources to the daemon; other variables
            #    # may not be correct
            #    is_parent = daemonizer(environ["TMP"]+"\\MediaArchiverDaemon.pid")

            #    if is_parent:
            #        # Run code in the parent after daemonization
            #        logger.debug("Main process exit...")
            #        sys.exit()
            pass

        # We are now daemonized, and the parent just exited.        
        daemon = Daemon(servConfig, ds)
        daemon.Main(forceSearchFiles)

        
    



