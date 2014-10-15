import socket

DEFAULT_IP      = "0.0.0.0"
DEFAULT_PORT    = 5005
DEFAULT_ROOT    = "test"
DEFAULT_BLKSIZE = 512

# TFTP Opcodes
OP_NULL  = "\0"
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
    def __init__(self, ipaddr=DEFAULT_IP, port=DEFAULT_PORT, root=DEFAULT_ROOT):
        # IP information.
        self.ipaddr = ipaddr
        self.port = port

        # Create and bind a UDP socket.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((ipaddr, port))
        self.sock = sock

        # TODO: Keep a list of clients/requests
        self.clients = {}
        self.root = root

    def serve(self):
        """Serve multiple clients at once. This is the main event loop."""
        while True:
            data, addr = self.sock.recvfrom(1024)
            self.dispatch(data, addr)

    def send_block(self, read_obj, last_received=-1):
        current_blockno = read_obj.blockno
        if current_blockno == last_received:
            # Send each block in order.
            read_obj.incr_blockno()

        # Get next block and read request's address.
        address = read_obj.address
        next_block = read_obj.get_nextblock()
        if next_block is not None:
            payload = OP_NULL + OP_DATA + OP_NULL + chr(current_blockno) + next_block
            print "sending payload: ", list(payload)
            self.sock.sendto(payload, address)

    def dispatch(self, data, address):
        """Given a packet and an address, dispatches to the correct function call.
           Will pick the appropriate action to be taken for Read, Write, Data, Ack, and 
           Error requests."""
        if len(data) < 4:
            print("request length too short")

        addr_string = address[0] + ":" + str(address[1])
        print "raw request: ", list(data)

        # Figure out what the request was, and handle it accordingly.
        # Ignore first byte (it's irrelevant anyway)
        opcode = data[1]
        if opcode == OP_READ:
            print "read request received from " + addr_string
            payload = data[2:].split("\0")
            file_name = self.root + "/" + payload[0]
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
                self.send_block(read_req)
            except (IOError, OSError) as e:
                # Print out our error and send an ERROR response.
                print e
                self.sock.sendto("\0\5\0\1file not found\0", address)
        elif opcode == OP_WRITE:
            print "write request received from " + addr_string
        elif opcode == OP_DATA:
            print "data received from " + addr_string
        elif opcode == OP_ACK:
            print "ack received from " + addr_string
            # Check if ACK is for a current request.
            if addr_string in self.clients:
                req_obj = self.clients[addr_string]
                last_received = (ord(data[2]) << 8) | ord(data[3])
                if req_obj.req_type == RRQ:
                    self.send_block(req_obj, last_received)
        elif opcode == OP_ERROR:
            print "error received from " + addr_string

class RequestObject:
    def __init__(self, address, file_buffer, req_type):
        # TODO: Change from file_object to a buffer.
        self.address = address
        self.file_buffer = file_buffer
        self.next_block = ""
        self.blockno = 1
        self.req_type = req_type
        self.complete = False

    def get_nextblock(self):
        if self.req_type == RRQ:
            file_buffer = self.file_buffer
            length = len(file_buffer)
            blockno = self.blockno
            if not self.complete:
                if blockno * DEFAULT_BLKSIZE > length:
                    self.complete = True
                    return file_buffer[:blockno*DEFAULT_BLKSIZE]
                else:
                    return file_buffer[(blockno-1)*DEFAULT_BLKSIZE: blockno*DEFAULT_BLKSIZE]
            else:
                return None

    def incr_blockno(self):
        if self.req_type == RRQ:
            self.blockno += 1

if __name__ == "__main__":
    server = TFTPServer()
    server.serve()
