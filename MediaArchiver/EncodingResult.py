class EncodingResult:
    """description of error codes from client"""
    
    ErrorCodes = {
            "NoError": 0,
            "TransmissionError": -1,
            "ProcessAborted": -2,
            "OsError": -3,
            "FFMPEGError": -4,
            "UnknownError": -5,
            "CannotSaveSpace": -100
        }

    def __init__(self, errorCode, newFileLength = 0, comment = ""):
        self.ErrorCode = errorCode
        self.NewFileLength = newFileLength
        self.Comment = comment

    def __repr__(self):
        return "{} - {}".format(self.ErrorCode, self.Comment)