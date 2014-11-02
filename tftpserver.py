import errno
import os
import socket
import time

from collections import deque

# Default constants.
DEFAULT_IP       = "0.0.0.0"
DEFAULT_PORT     = 5005
DEFAULT_ROOT_DIR = "test"
DEFAULT_BLKSIZE  = 512

# TFTP Opcodes
OP_NULL  = 0
OP_READ  = 1
OP_WRITE = 2
OP_DATA  = 3
OP_ACK   = 4
OP_ERROR = 5

# Error codes
NOT_IMPL_ERR  = 0
PROTOCOL_ERR  = 1
NOT_FOUND_ERR = 2
ACCESS_ERR    = 3
DISK_FULL_ERR = 4
ILLEGAL_ERR   = 5
TID_ERR       = 6
EXISTS_ERR    = 7
USER_ERR      = 8

# Strings
OP_STRINGS = ["NULL", 
              "READ REQUEST", 
              "WRITE REQUEST", 
              "DATA", 
              "ACK", 
              "ERROR"]

ERROR_MSGS = ["\0\5\0\0Not implemented.\0", 
              "\0\5\0\0Unknown protocol.\0",
              "\0\5\0\1File not found.\0", 
              "\0\5\0\2Access violation.\0", 
              "\0\5\0\3Disk full or allocation exceeded.\0", 
              "\0\5\0\4Illegal tftp operation.\0",
              "\0\5\0\5Unknown transfer ID.\0",
              "\0\5\0\6File already exists.\0",
              "\0\5\0\7No such user.\0"]

DATA_PACKET = "\0\3{0}{1}{2}"
ACK_PACKET  = "\0\4{0}{1}"

NETASCII = "netascii"
OCTET = "octet"

class TFTPServer(object):
    def __init__(self, ipaddr=DEFAULT_IP, port=DEFAULT_PORT, root_dir=DEFAULT_ROOT_DIR):
        """A TFTPServer object consists of a socket, a client map, and client queue. The default root
        directory is where files will be served from and stored. To serve requests, we create request
        objects and map them for quick lookup. In case of client timeouts, we will need to resend messages.
        For this reason, we use a priority queue to keep track of the earliest clients, and determine
        if they require retransmission or reminders."""
        # IP information.
        self.ipaddr = ipaddr
        self.port = port

        # Create and bind a UDP socket.
        address = (ipaddr, port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(address)
        self.sock = sock

        # TODO: Keep a list of clients/requests
        self.clients = {}
        self.client_queue = deque()
        self.root_dir = os.getcwd() + "/" + root_dir
        print "Listening on address {}".format(repr(address))

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
            error_msg = ERROR_MSGS[PROTOCOL_ERR]
            self.sock.sendto(error_msg, address)
            return

        addr_string = repr(address)
        # print "\nraw packet: ", list(data)

        # Figure out what the request was, and handle it accordingly.
        # Ignore first byte (it's irrelevant anyway)
        opcode = ord(data[1])
        print "{0} received from {1}".format(OP_STRINGS[opcode], addr_string)
        if opcode == OP_READ:
            header = data[2:].split(chr(OP_NULL))
            self.create_read_client(address, header)
        elif opcode == OP_WRITE:
            header = data[2:].split(chr(OP_NULL))
            self.create_write_client(address, header)
        elif opcode == OP_DATA:
            try:
                # Check if DATA is for a current WriteClient.
                client = self.clients[addr_string]
                if isinstance(client, WriteClient): 
                    if client.complete:
                        self.clients.pop(client, None)
                        self.client_queue.popleft()
                    else:
                        # Send an ACK for this packet.
                        blockno = (ord(data[2]) << 8) | ord(data[3])
                        block = data[4:]
                        self.write_block_and_send_ack(client, blockno, block)
                elif isinstance(client, ErrorClient):
                    # Remove ErrorClients and completed requests.
                    self.clients.pop(client, None)
            except KeyError as e:
                print e
                error_msg = ERROR_MSGS[TID_ERR]
                self.sock.sendto(error_msg, address)
        elif opcode == OP_ACK:
            try:
                # Check if ACK is for a current ReadClient.
                client = self.clients[addr_string]
                if isinstance(client, ReadClient):
                    if client.complete:
                        self.clients.pop(client, None)
                        self.client_queue.popleft()
                    else:
                        # Interpret last block received and send next block.
                        last_received = (ord(data[2]) << 8) | ord(data[3])
                        self.send_block(client, last_received)
                elif isinstance(client, ErrorClient):
                    # Remove ErrorClients and completed requests.
                    self.clients.pop(client, None)
            except KeyError as e:
                print e
                error_msg = ERROR_MSGS[TID_ERR]
                self.sock.sendto(error_msg, address)
        elif opcode == OP_ERROR:
            error_msg = ERROR_MSGS[NOT_IMPL_ERR]
            self.sock.sendto(error_msg, address)
        else:
            # Unknown protocol, send an error.
            error_msg = ERROR_MSGS[PROTOCOL_ERR]
            self.sock.sendto(error_msg, address)

    def create_read_client(self, address, header):
        """Creates a ReadClient object in response to a Read Request."""
        file_name = self.root_dir + "/" + header[0]
        file_format = header[1]

        # By default, we read in "netascii", or 'r' mode. Otherwise
        # we read binary in OCTET mode.
        mode = "r"
        if file_format == OCTET:
            mode = "rb"
        try: 
            # Open file and read into a buffer.
            # status = os.stat(file_name)
            # if status.st_size > 
            file_object = open(file_name, mode)
            file_buffer = file_object.read()
            file_object.close()

            # Create a request object.
            read_client = ReadClient(address, file_buffer)

            # Map and enqueue request.
            self.clients[repr(address)] = read_client
            self.client_queue.append(read_client)

            self.send_block(read_client)
        except (IOError, OSError) as e:
            # Print out our error and send an ERROR response.
            print e

            # Create a dummy client for handling acks, otherwise we get a KeyError.
            error_client = ErrorClient(address)
            self.clients[repr(address)] = error_client

            # Send our error message.
            error_msg = ERROR_MSGS[NOT_FOUND_ERR]
            self.sock.sendto(error_msg, address)

    def create_write_client(self, address, header):
        """Creates a WriteClient object in response to a Write Request."""
        file_name = self.root_dir + "/" + header[0]
        file_format = header[1]
        mode = "w"
        if file_format == OCTET:
            mode = "wb"
        try:
            # Create a WriteClient and add to list.
            file_handle = open(file_name, mode)
            write_client = WriteClient(address, file_handle)

            # Map and enqueue request.
            self.clients[repr(address)] = write_client
            self.client_queue.append(write_client)

            # Send an ACK with block number 0.
            packet = ACK_PACKET.format(chr(OP_NULL), chr(OP_NULL))
        except (IOError, OSError) as e:
            # Print out error and send an ERROR response
            print e
            
            # Create a dummy client for handling acks, otherwise we get a KeyError.
            error_client = ErrorClient(address)
            self.clients[repr(address)] = error_client

            # TODO: Handle different IOErrors here. 
            packet = ERROR_MSGS[DISK_FULL_ERR]

        # Send an ack packet on success and error otherwise.
        self.sock.sendto(packet, address)

    def send_block(self, read_client, last_received=0):
        """Sends the next block to a ReadClient object."""
        current_blockno = read_client.blockno
        if current_blockno == last_received:
            # If the last block was confirmed received, we increment the block number.
            current_blockno = read_client.incr_blockno()

        # Get next block to send to client.
        address = read_client.address
        blksize = read_client.blksize
        next_block = read_client.get_next_block()

        # If blocksize is less than DEFAULT_BLKSIZE, then this is the last block.
        if len(next_block) < blksize:
            read_client.complete = True

        # Format block # as a 2 byte char string.
        first_byte = current_blockno >> 8
        second_byte = current_blockno & 0xFF

        # Send a formatted payload.
        payload = DATA_PACKET.format(chr(first_byte), chr(second_byte), next_block)
        self.sock.sendto(payload, address)

    def write_block_and_send_ack(self, write_client, blockno, block):
        address = write_client.address
        error_code = write_client.write_next_block(block)
        if bool(error_code):
            # TODO: Handle multiple errors.
            print "Write failed!"
            msg = ERROR_MSGS[DISK_FULL_ERR]
        else:
            if len(block) < write_client.blksize:
                # This is the last block, so we set complete to true.
                write_client.complete = True
                write_client.cleanup()

            # Write success, send an acknowledgement packet.
            write_client.last_received = blockno
            first_byte = blockno >> 8
            second_byte = blockno & 0xFF
            msg = ACK_PACKET.format(chr(first_byte), chr(second_byte))

        # Send an ACK packet on success and ERROR otherwise.
        self.sock.sendto(msg, address)

class Client(object):
    """Clients have two forms: ReadClients and WriteClients, which represent
       clients of Read Requests and Write Requests, respectively."""
    def __init__(self, address):
        self.address = address
        self.complete = False

class ReadClient(Client):
    """Read clients are formed from Read Requests of the form `get filename`.
       To fulfill a request, we open a file for reading."""
    def __init__(self, address, file_buffer, blksize=DEFAULT_BLKSIZE):
        Client.__init__(self, address)
        self.file_buffer = file_buffer
        self.file_length = len(file_buffer)
        self.blockno = 1
        self.blksize = blksize

    def get_next_block(self):
        file_buffer = self.file_buffer
        length = self.file_length
        blockno = self.blockno
        blksize = self.blksize

        lower, upper = (blockno - 1) * blksize, blockno * blksize
        if upper > length:
            return file_buffer[lower:]
        else:
            return file_buffer[lower:upper]

    def incr_blockno(self):
        self.blockno += 1
        return self.blockno

class WriteClient(Client):
    def __init__(self, address, file_handle, blksize=DEFAULT_BLKSIZE):
        Client.__init__(self, address)
        self.file_handle = file_handle
        self.last_received = 0
        self.blksize = blksize

    def write_next_block(self, block):
        try:
            self.file_handle.write(block)
            return 0
        except (IOError, OSError) as e:
            # TODO: Handle exception somehow.
            print e
            return e.errno

    def cleanup(self):
        self.file_handle.close()

class ErrorClient(Client):
    def __init__(self, address):
        Client.__init__(self, address)
        self.complete = True

if __name__ == "__main__":
    server = TFTPServer()
    server.serve()
