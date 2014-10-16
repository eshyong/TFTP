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

# Error codes
UNDEF_ERR     = 0
NOT_FOUND_ERR = 1
ACCESS_ERR    = 2
DISK_FULL_ERR = 3
ILLEGAL_ERR   = 4
TID_ERR       = 5
EXISTS_ERR    = 6
USER_ERR      = 7

# Strings
OP_STRINGS = ["NULL", 
              "READ REQUEST", 
              "WRITE REQUEST", 
              "DATA", 
              "ACK", 
              "ERROR"]

ERROR_MSGS = ["\0\5\0\0Not implemented.\0", 
              "\0\5\0\1File not found.\0", 
              "\0\5\0\2Access violation.\0", 
              "\0\5\0\3Disk full or allocation exceeded.\0", 
              "\0\5\0\4Illegal tftp operation.\0",
              "\0\5\0\5Unknown transfer ID.\0",
              "\0\5\0\6File already exists.\0",
              "\0\5\0\7No such user.\0"]

DATA_PACKET = "\0\3{0}{1}{2}"
ACK_PACKET  = "\0\4{0}{1}"

# Client types
RRQ = 1
WRQ = 2

class TFTPServer:
    def __init__(self, ipaddr=DEFAULT_IP, port=DEFAULT_PORT, root=DEFAULT_ROOT):
        """Constructor"""
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

    def dispatch(self, data, address):
        """Given a packet and an address, dispatches to the correct function call.
           Will pick the appropriate action to be taken for Read, Write, Data, Ack, and 
           Error requests."""
        if len(data) < 4:
            print("request length too short")

        addr_string = repr(address)
        print "\nraw packet: ", list(data)

        # Figure out what the request was, and handle it accordingly.
        # Ignore first byte (it's irrelevant anyway)
        opcode = data[1]
        print "{} received from {}".format(OP_STRINGS[ord(opcode)], addr_string)
        if opcode == OP_READ:
            header = data[2:].split(OP_NULL)
            self.create_readclient(address, header)
        elif opcode == OP_WRITE:
            error_msg = ERROR_MSGS[UNDEF_ERR]
            self.sock.sendto(error_msg, address)
        elif opcode == OP_DATA:
            error_msg = ERROR_MSGS[UNDEF_ERR]
            self.sock.sendto(error_msg, address)
        elif opcode == OP_ACK:
            if addr_string in self.clients:
                # Check if ACK is for a current ReadClient.
                read_client = self.clients[addr_string]
                if isinstance(read_client, ReadClient):
                    # Interpret last received block. This number is in two separate bytes, 
                    # so we have to rejoin them.
                    last_received = (ord(data[2]) << 8) | ord(data[3])
                    self.send_block(read_client, last_received)
        elif opcode == OP_ERROR:
            error_msg = ERROR_MSGS[UNDEF_ERR]
            self.sock.sendto(error_msg, address)

    def create_readclient(self, address, header):
        """Creates a ReadClient object"""
        addr_string = repr(address)
        file_name = self.root + "/" + header[0]
        file_format = header[1]

        # By default, we read in "netascii", or 'r' mode. Otherwise
        # we read binary in "octet" mode.
        mode = "r"
        if file_format == "octet":
            mode = "rb"
        try: 
            # Open file and read into a buffer.
            file_object = open(file_name, mode)
            file_buffer = file_object.read()
            file_object.close()

            # Create a request object.
            read_client = ReadClient(address, file_buffer)
            if addr_string in self.clients:
                self.clients.pop(addr_string, None)
            self.clients[addr_string] = read_client
            self.send_block(read_client)
        except (IOError, OSError) as e:
            # Print out our error and send an ERROR response.
            print e
            error_msg = ERROR_MSGS[NOT_FOUND_ERR]
            self.sock.sendto(error_msg, address)

    def send_block(self, read_client, last_received=-1):
        current_blockno = read_client.blockno
        if current_blockno == last_received:
            # If the last block was confirmed received, we increment the block #.
            current_blockno += 1
            read_client.blockno = current_blockno

        # Get next block and read request's address.
        address = read_client.address
        next_block = read_client.get_nextblock()
        if next_block is None:
            self.clients.pop(repr(address), None)
        else:
            first_byte = current_blockno >> 8
            second_byte = current_blockno & 0xFF
            payload = DATA_PACKET.format(chr(first_byte), chr(second_byte), next_block)
            print "blockno: {0:d}, payload length: {1:d}".format(current_blockno, len(payload))
            print "block: {}".format(next_block)
            self.sock.sendto(payload, address)


class Client:
    def __init__(self, address):
        self.address = address
        self.complete = False

class ReadClient(Client):
    def __init__(self, address, file_buffer):
        Client.__init__(self, address)
        self.file_buffer = file_buffer
        self.blockno = 1

    def get_nextblock(self):
        file_buffer = self.file_buffer
        length = len(file_buffer)
        blockno = self.blockno
        if not self.complete:
            lower, upper = (blockno - 1) * DEFAULT_BLKSIZE, blockno * DEFAULT_BLKSIZE
            if upper > length:
                self.complete = True
                return file_buffer[lower:]
            else:
                return file_buffer[lower:upper]
        else:
            return None

if __name__ == "__main__":
    server = TFTPServer()
    server.serve()
