import socket

DEFAULT_IP      = "0.0.0.0"
DEFAULT_PORT    = 5005
DEFAULT_PATH    = "test"
DEFAULT_BLKSIZE = 512

# TFTP Opcodes
OP_READ  = "\1"
OP_WRITE = "\2"
OP_DATA  = "\3"
OP_ACK   = "\4"
OP_ERROR = "\5"

# Request types
RRQ = 1
WRQ = 2

class TFTPServer:
    """Constructor."""
    def __init__(self, ipaddr=DEFAULT_IP, port=DEFAULT_PORT, path=DEFAULT_PATH):
        # IP information.
        self.ipaddr = ipaddr
        self.port = port

        # Create and bind a UDP socket.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((ipaddr, port))
        self.sock = sock

        # TODO: Keep a list of clients/requests
        self.clients = {}

    def serve(self):
        """Serve multiple clients at once. This is the main event loop."""
        self.serve_clients()
        while True:
            data, addr = self.sock.recvfrom(1024)
            self.get_request(data, addr)

    def serve_clients(self):
        for addr in self.clients:
            request_obj = self.clients[addr]

    def serve_client(self, request_obj):
        if request_obj.req_type == RRQ:
            next_block = request_obj.get_nextblock()
            if next_block is not None:
                self.sock.sendto(next_block, request_obj.address)

    def get_request(self, data, address):
        if len(data) < 4:
            print("request length too short")

        addr_string = address[0] + ":" + str(address[1])

        # Figure out what the request was, and handle it accordingly.
        # Ignore first byte (it's irrelevant anyway)
        opcode = data[1]
        log = "" 
        if opcode == OP_READ:
            print "read request received from " + addr_string
            payload = data[2:].split("\0")
            file_name = payload[0]
            file_format = payload[1]
            try: 
                # Try opening file and creating a read request object.
                # TODO: Depending on file length, we can read the whole file in at once or 
                # just pass in a file object.

                # Open file and read into a buffer.
                file_object = open(file_name, 'r')
                file_buffer = file_object.read()
                file_object.close()

                # Create a request object.
                read_req = RequestObject(address, file_buffer, RRQ)
                if addr_string in self.clients:
                    self.clients.pop(addr_string, None)
                self.clients[addr_string] = read_req
                self.serve_client(read_req)
            except (IOError, OSError) as e:
                # Raise an exception if we can't open the file.
                print e
                # TODO: send an error.
                self.sock.sendto("\0\5\0\1file not found\0", address)
        elif opcode == OP_WRITE:
            print "write request received from " + addr_string
        elif opcode == OP_DATA:
            print "data received from " + addr_string
        elif opcode == OP_ACK:
            print "ack received from " + addr_string
        elif opcode == OP_ERROR:
            print "error received from " + addr_string

class RequestObject:
    def __init__(self, address, file_buffer, req_type):
        # TODO: Change from file_object to a buffer.
        self.address = address
        self.file_buffer = file_buffer
        self.next_block = ""
        self.blockno = 0
        self.req_type = req_type

    def get_next_block(self):
        if self.blockno * DEFAULT_BLKSIZE > len(file_buffer):
            return None
        return file_buffer[self.blockno*DEFAULT_BLKSZE:]

if __name__ == "__main__":
    server = TFTPServer()
    server.serve()
