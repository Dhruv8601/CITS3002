# CITS3002 2021 Assignment
#
# This file implements a basic server that allows a single client to play a
# single game with no other participants, and very little error checking.
#
# Any other clients that connect during this time will need to wait for the
# first client's game to complete.
#
# Your task will be to write a new server that adds all connected clients into
# a pool of players. When enough players are available (two or more), the server
# will create a game with a random sample of those players (no more than
# tiles.PLAYER_LIMIT players will be in any one game). Players will take turns
# in an order determined by the server, continuing until the game is finished
# (there are less than two players remaining). When the game is finished, if
# there are enough players available the server will start a new game with a
# new selection of clients.

import socket
import sys
import tiles

import threading
import random
import time
from queue import Queue

class Client():
  '''This class stores one client connection'''
  def __init__(self, connection, name, idnum):
    self.connection = connection
    self.name = name
    self.idnum = idnum
    self.had_turn = False # used to check if they should be eliminated or not if they disconnect
    self.num_turn = 0 # used to determine what move the server should do if they were idle

class Game():
  '''This class stores the game state'''
  def __init__(self, board):
    self.board = board
    self.created = False # True if enough clients available
    self.made_first_move = False # True when the first move of a new game has been made


clients = [] # stores all clients
game = Game(tiles.Board()) # initial game state
messages = [] # stores all messages sent during a game
live_idnums = [] # idnums of all clients currently playing
client_order = Queue() # maintains the order of play

def new_game():
  '''Initialise a new game'''
  global clients
  global live_idnums
  global messages
  global game
  global client_order

  # initialise starting variables for new game
  game = Game(tiles.Board())
  game.created = True
  game.made_first_move = False
  live_idnums = []
  messages = []
  client_order = Queue()

  send_to_all(tiles.MessageGameStart())

  # number of players for game, max 4
  all_clients_list = clients
  random.shuffle(all_clients_list)
  num_players = min(len(all_clients_list), 4)

  # add clients to a player order
  for i in range(num_players):
    client_order.put(all_clients_list[i])
    live_idnums.append(all_clients_list[i].idnum)
    first_client = list(client_order.queue)[0]

  send_to_all(tiles.MessagePlayerTurn(first_client.idnum))

  for client in clients:
    if client == first_client:
      client.had_turn = True
      client.num_turn = 1
    else:
      client.had_turn = False
      client.num_turn = 0

  for client in clients:
    for _ in range(tiles.HAND_SIZE):
      tileid = tiles.get_random_tileid()
      client.connection.send(tiles.MessageAddTileToHand(tileid).pack())

def send_to_all(msg):
  '''Send a message to all clients'''
  global clients
  global messages

  msgbytes = msg.pack() # pack the message once
  for client in clients:
    try:
      client.connection.sendall(msgbytes)
    except Exception as e:
      print('exception sending message: {}'.format(e))

  messages.append(msgbytes)

def next_turn(eliminated, next=True):
  '''Remove eliminated players and go to the next turn needed'''
  global clients
  global live_idnums
  global client_order

  current_order = client_order

  # is next turn needed or did someone disconnect and needs to be eliminated only
  # reshuffle the list making the first player in the queue the last player
  if next:
    current_client = current_order.get()
    current_order.put(current_client)

  new_order = Queue()
  live_idnums = []

  
  # add only players still not eliminated
  for client in current_order.queue:
    if client.idnum not in eliminated:
      new_order.put(client)
      live_idnums.append(client.idnum)

  # if enough players, then next turn else stop game
  if new_order.qsize() > 1:
    new_client = list(new_order.queue)[0]
    send_to_all(tiles.MessagePlayerTurn(new_client.idnum))

    for client in clients:
      if client == new_client:
        client.had_turn = True
        client.num_turn += 1

  else:
    game.created = False
    game.made_first_move = False

  client_order = new_order

def remove_client(client):
  '''Removes a player if they have disconnected'''
  global clients
  clients.remove(client)
  
  # was the player in the current game or a spectator
  if client in list(client_order.queue):

    # if it was disconnected player's turn then go to next turn
    if client == list(client_order.queue)[0]:
      next_turn([client.idnum])
    else:
      next_turn([client.idnum], next=False)

    # if the client had his turn then eliminate him
    if client.had_turn:
      send_to_all(tiles.MessagePlayerEliminated(client.idnum))

  # add to the list of messages sent to keep a new client up to date with the current game
  send_to_all(tiles.MessagePlayerLeft(client.idnum))

def client_handler(connection, address, idnum):
  '''Handle each client separately'''
  global clients
  global live_idnums
  global game

  host, port = address
  name = '{}:{}'.format(host, port)

  client = Client(connection, name, idnum)
  clients.append(client)

  connection.send(tiles.MessageWelcome(idnum).pack())
  
  # inform each client of new client and inform new client of every other client
  for old_client in clients:
    client.connection.send(tiles.MessagePlayerJoined(old_client.name, old_client.idnum).pack())
    if old_client.idnum != client.idnum:
      old_client.connection.send(tiles.MessagePlayerJoined(client.name, client.idnum).pack())

  # if midway through a game then get new player up to date
  if game.made_first_move:
    for msg in messages:
      connection.send(msg)

  # if a game has not started (by a player making any move), make a new game
  elif len(clients) > 1 and not game.made_first_move:
    new_game()


  buffer = bytearray()
  while True:
    # if there is no game but enough clients, make a new game
    if len(clients) > 1 and not game.created:
      new_game()

    # check if client is in the list of all connected clients
    # if client has disconnected, remove them
    if name in [client.name for client in clients]:
      try:
        chunk = connection.recv(4096)
      except:
        print('client {} disconnected'.format(address))
        for client in clients:
          if client.name == name:
            remove_client(client)
            continue
            
      if not chunk:
        print('client {} disconnected'.format(address))
        for client in clients:
          if client.name == name:
            remove_client(client)
        continue

      # check if the sent message is by the player who's turn it is
      if name == list(client_order.queue)[0].name and game.created:
        buffer.extend(chunk)

        while True:
          msg, consumed = tiles.read_message_from_bytearray(buffer)
          if not consumed:
            break

          buffer = buffer[consumed:]

          print('received message {}'.format(msg))

          # sent by the player to put a tile onto the board (in all turns except
          # their second)
          if isinstance(msg, tiles.MessagePlaceTile):
            if game.board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
              if not game.made_first_move:
                game.made_first_move = True
              # notify clients that placement was successful
              send_to_all(msg)

              # check for token movement
              positionupdates, eliminated = game.board.do_player_movement(live_idnums)

              for msg in positionupdates:
                send_to_all(msg)
              
              for idnum in eliminated:
                send_to_all(tiles.MessagePlayerEliminated(idnum))

              # pickup a new tile
              tileid = tiles.get_random_tileid()
              connection.send(tiles.MessageAddTileToHand(tileid).pack())

              # start next turn
              next_turn(eliminated)

          # sent by the player in the second turn, to choose their token's
          # starting path
          elif isinstance(msg, tiles.MessageMoveToken):
            if not game.board.have_player_position(msg.idnum):
              if game.board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
                # check for token movement
                positionupdates, eliminated = game.board.do_player_movement(live_idnums)

                for msg in positionupdates:
                  send_to_all(msg)
                
                for idnum in eliminated:
                  send_to_all(tiles.MessagePlayerEliminated(idnum))
                
                # start next turn
                next_turn(eliminated)


# create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# listen on all network interfaces
server_address = ('', 30020)
sock.bind(server_address)

print('listening on {}'.format(sock.getsockname()))

sock.listen(5)

idnum = 0

while True:
  # handle each new connection independently
  connection, client_address = sock.accept()
  print('received connection from {}'.format(client_address))

  # create a new thread for each client
  thread = threading.Thread(target=client_handler, args=(connection, client_address, idnum), daemon=True).start()
  idnum += 1  # increment id so all clients have a different idnum
