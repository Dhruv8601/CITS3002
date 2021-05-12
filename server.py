import socket
import select
import message

class Client():
  """This class stores one client connection, the address of the client,
  and a buffer of bytes that we have received from the client but not yet
  processed.
  """
  def __init__(self, connection, address):
    self.connection = connection
    self.address = address
    self.buffer = bytearray()

# create the server socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# bind to all local interfaces
server_address = ('', 30021)
sock.bind(server_address)

# allow up to 5 queued (but not yet accepted) connections
sock.listen(5)

# a list of all the clients currently connected to our server
clients = []

# a list of all the connections that we want to listen to:
# - first sock, which will tell us about new incoming client connections
# - later we will also add the client connections, so that we can read their
#   messages
listening = [sock]

# remove a client from the server (because they have disconnected)
# we need to remove them from the global client list, and also remove their
# connection from our list of connections-to-listen-to
def remove_client(client):
  global clients, listening
  listening.remove(client.connection)
  clients.remove(client)

# send a message to all clients. if the client's connection is down, then the
# sendall() might fail. don't worry too much about that here, we will detect
# the severed connection later (when we next attempt to read from the
# connection), and we can handle the disconnection there.
def send_to_all(msg):
  global clients

  msgbytes = msg.pack() # pack the message once

  for client in clients:
    try:
      client.connection.sendall(msgbytes)
    except Exception as e:
      print('exception sending message: {}'.format(e))

# the main server loop, run forever / until the user interrupts the process
#   interrupt with Ctrl+C or Ctrl+Pause/Break
#
while True:
  # wait for any one of our socket/connections to be readable, or to have an
  # exceptional state.
  # get back a list of all the socket/connections that are readable or in an
  # exceptional state.
  readable, _, exceptional = select.select(listening, [], listening)

  # was the main socket one of our readable objects? if so, there is a new
  # client connection waiting to be accepted
  if sock in readable:
    connection, client_address = sock.accept()

    print('received connection from {}'.format(client_address))

    # add client to our global list of clients, and add the client connection
    # to our global list of connections-to-listen-to.
    client = Client(connection, client_address)
    clients.append(client)
    listening.append(client.connection)
  
  # check if any of our client connections were in the list of currently
  # readable connections (i.e. check if there is a message on any of them).

  disconnected = []

  for client in clients:
    if client.connection in exceptional:
      print('client {} exception'.format(client.address))
      disconnected.append(client)

    elif client.connection in readable:
      # try to read a chunk of bytes from this client
      try:
        chunk = client.connection.recv(4096)
      except Exception:
        print('client {} recv exception, removing client'.format(client.address))
        disconnected.append(client)
        continue # go to next client

      if not chunk:
        print('client {} closed connection'.format(client.address))
        disconnected.append(client)
        continue # go to next client

      # add the bytes we just received to this client's buffer
      client.buffer.extend(chunk)

      # read as many complete messages as possible out of this client's buffer
      while True:
        msg, consumed = message.Message.unpack(client.buffer)
        if consumed:
          client.buffer = client.buffer[consumed:]

          printmsg = '{}: {}'.format(client.address, msg.contents)
          print(printmsg)

          send_to_all(message.Message(printmsg))
        else:
          break
  
  # remove any disconnected clients
  for client in disconnected:
    remove_client(client)
