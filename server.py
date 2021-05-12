import socket
import select
import sys
import tiles
import random
import time
from queue import Queue

class Client():
  """This class stores one client connection, the address of the client,
  and a buffer of bytes that we have received from the client but not yet
  processed.
  """
  def __init__(self, connection, name, idnum, had_turn = False, num_turn = 0):
    self.connection = connection
    self.name = name
    self.idnum = idnum
    self.had_turn = had_turn
    self.num_turn = num_turn
    self.buffer = bytearray()

class Game():
  def __init__(self, board, created = False, made_first_move = False):
    self.board = board
    self.created = created
    self.made_first_move = made_first_move

# create the server socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# bind to all local interfaces
server_address = ('', 30020)
sock.bind(server_address)

# allow up to 5 queued (but not yet accepted) connections
sock.listen(5)

# a list of all the clients currently connected to our server
clients = []
game = Game(tiles.Board())
messages = []
live_idnums = []
client_order = Queue()
idnum = 0
# a list of all the connections that we want to listen to:
# - first sock, which will tell us about new incoming client connections
# - later we will also add the client connections, so that we can read their
#   messages
listening = [sock]

def new_game():
  global clients
  global live_idnums
  global messages
  global game
  global client_order

  game = Game(tiles.Board(), True)
  live_idnums = []
  messages = []

  send_to_all(tiles.MessageGameStart())

  all_clients_list = clients
  random.shuffle(all_clients_list)
  num_players = min(len(all_clients_list, 4))

  for i in range(num_players):
    client_order.put(all_clients_list[i])
    live_idnums.append(all_clients_list[i].idnum)

  first_client = list(client_order.queue)[0]
  send_to_all(tiles.MessagePlayerTurn(first_client.idnum))

  for client in clients:
    if client == first_client:
      client.had_turn = True
      client.num_turn += 1

  for client in clients:
    if client.idnum in live_idnums:
      for _ in range(tiles.HAND_SIZE):
        tileid = tiles.get_random_tileid()
        client.connection.send(tiles.MessageAddTileToHand(tileid).pack())




def next_client(eliminated):
  global clients
  global live_idnums
  global client_order 
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
  global messages

  msgbytes = msg.pack() # pack the message once

  for client in clients:
    try:
      client.connection.sendall(msgbytes)
      messages.append(msgbytes)
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
    host, port = client_address
    name = '{}:{}'.format(host, port)

    client = Client(connection, name, idnum)
    clients.append(client)
    listening.append(client.connection)
    idnum += 1

    client.connection.send(tiles.MessageWelcome(client.idnum).pack())

    for old_client in clients:
      client.connection.send(tiles.MessagePlayerJoined(old_client.name, old_client.idnum).pack())
      if old_client.idnum != client.idnum:
        old_client.connection.send(tiles.MessagePlayerJoined(client.name, client.idnum).pack())
  
  # check if any of our client connections were in the list of currently
  # readable connections (i.e. check if there is a message on any of them).

  disconnected = []

  for client in clients:
    if client.connection in exceptional:
      print('client {} exception'.format(client.name))
      disconnected.append(client)

    elif client.connection in readable:
      # try to read a chunk of bytes from this client
      try:
        chunk = client.connection.recv(4096)
      except Exception:
        print('client {} recv exception, removing client'.format(client.name))
        disconnected.append(client)
        continue # go to next client

      if not chunk:
        print('client {} closed connection'.format(client.name))
        disconnected.append(client)
        continue # go to next client

      # add the bytes we just received to this client's buffer
      client.buffer.extend(chunk)

      # read as many complete messages as possible out of this client's buffer
      while True:
        msg, consumed = tiles.read_message_from_bytearray(client.buffer)
        client.buffer = client.buffer[consumed:]

        print('received message {}'.format(msg))

        if isinstance(msg, tiles.MessagePlaceTile):
          if game.board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
            if not game.made_first_move:
              game.made_first_move = True
            
            send_to_all(msg)

            positionupdates, eliminated = game.board.do_player_movement(live_idnums)

            for msg in positionupdates:
              send_to_all(msg)

            for idnum in eliminated:
              send_to_all(tiles.MessagePlayerEliminated(idnum))

            tileid = tiles.get_random_tileid()
            client.connection.send(tiles.MessageAddTileToHand(tileid).pack())

            next_player(eliminated)
        elif isinstance(msg, tiles.MessageMoveToken):
          if not game.board.have_player_position(msg.idnum):
            if game.board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):

              positionupdates, eliminated = game.board.do_player_movement(live_idnums)

              for msg in positionupdates:
                send_to_all(msg)
            
              if idnum in eliminated:
                send_to_all(tiles.MessagePlayerEliminated(idnum))
            
              # start next turn
              next_player(eliminated)

        else:
          break
  
  # remove any disconnected clients
  for client in disconnected:
    remove_client(client)
