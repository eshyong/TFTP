import tftpserver

if __name__ == "__main__":
    server = tftpserver.TFTPServer()
    server.serve()
