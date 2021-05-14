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
  """This class stores one client connection, the address of the client,
  and a buffer of bytes that we have received from the client but not yet
  processed.
  """
  def __init__(self, connection, name, idnum):
    self.connection = connection
    self.name = name
    self.idnum = idnum
    self.had_turn = False
    self.num_turn = 0

class Game():
  def __init__(self, board):
    self.board = board
    self.created = False
    self.made_first_move = False


clients = []
game = Game(tiles.Board())
messages = []
live_idnums = []
client_order = Queue()
disconnected = []

def new_game():
  global clients
  global live_idnums
  global messages
  global game
  global client_order

  game = Game(tiles.Board())
  game.created = True
  game.made_first_move = False
  live_idnums = []
  messages = []
  client_order = Queue()

  send_to_all(tiles.MessageGameStart())

  all_clients_list = clients
  random.shuffle(all_clients_list)
  num_players = min(len(all_clients_list), 4)

  for i in range(num_players):
    client_order.put(all_clients_list[i])
    live_idnums.append(all_clients_list[i].idnum)
    first_client = list(client_order.queue)[0]

  send_to_all(tiles.MessagePlayerTurn(first_client.idnum))
  # print(first_client.idnum)
  # print([client.idnum for client in list(client_order.queue)])

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
  global clients
  global messages

  msgbytes = msg.pack() # pack the message once

  for client in clients:
    try:
      client.connection.sendall(msgbytes)
      messages.append(msgbytes)
    except Exception as e:
      print('exception sending message: {}'.format(e))

def next_turn(eliminated, next=True):
  global clients
  global live_idnums
  global client_order
  print("eliminated", end = " ")
  print(eliminated)

  current_order = client_order
  if next:
    current_client = current_order.get()
    current_order.put(current_client)

  new_order = Queue()
  live_idnums = []

  for client in current_order.queue:
    if client.idnum not in eliminated:
      new_order.put(client)
      live_idnums.append(client.idnum)

  #print([client.idnum for client in list(new_order.queue)])
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

# def remove_client(client):
#   global clients
#   listening.remove(client.connection)
#   clients.remove(client)

def remove_client(client):
  global clients
  print("removing client")
  print([client.idnum for client in list(client_order.queue)])
  clients.remove(client)
  
  if client in list(client_order.queue):
    print("was in queue")
    if client == list(client_order.queue)[0]:
      next_turn([client.idnum])
    else:
      next_turn([client.idnum], next=False)


    if client.had_turn:
      send_to_all(tiles.MessagePlayerEliminated(client.idnum))

  send_to_all(tiles.MessagePlayerLeft(client.idnum))
  print([client.idnum for client in list(client_order.queue)])

def client_handler(connection, address, idnum):
  global clients
  global live_idnums
  global game
  global disconnected

  host, port = address
  name = '{}:{}'.format(host, port)

  client = Client(connection, name, idnum)
  clients.append(client)

  connection.send(tiles.MessageWelcome(idnum).pack())
  
  for old_client in clients:
    client.connection.send(tiles.MessagePlayerJoined(old_client.name, old_client.idnum).pack())
    if old_client.idnum != client.idnum:
      old_client.connection.send(tiles.MessagePlayerJoined(client.name, client.idnum).pack())

  if game.made_first_move:
    for msg in messages:
      connection.send(msg)

  elif len(clients) > 1 and not game.made_first_move:
    new_game()


  buffer = bytearray()

  while True:
    if len(clients) > 1 and not game.created:
      new_game()

    for client in clients:
      if client.name == name:
        try:
          chunk = connection.recv(4096)
        except:
          print('client {} disconnected first way'.format(address))
          for client in clients:
            if client.name == name:
              remove_client(client)
              continue
              
        if not chunk:
          print('client {} disconnected second'.format(address))
          for client in clients:
            if client.name == name:
              print(f"did client have turn: {client.had_turn}")
              remove_client(client)
          continue
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
                # notify client that placement was successful
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
