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

all_players = {}  # stores all the players whether they are playing or spectating
active_players = Queue() # stores the players that are actually playing that round
live_idnums = [] # stores the idnum of the players that are actually playing that round
all_messages = [] # stores all the messages since from a specific game to get new players updated on the game state

game_created = False # True if there are enough players to start a game
made_first_move = False # True if a move has been made. if False, a new game will start if a new player joins if they are not a spectator


board = tiles.Board() # creates new global board

class Player:
  def __init__(self, connection, name, idnum, hadPlayerTurn):
    self.connection = connection
    self.name = name
    self.idnum = idnum
    self.hadPlayerTurn = hadPlayerTurn

def new_game():
  '''initialises the game state variables and creates a new game'''
    # global variables
  global live_idnums
  global all_players
  global active_players
  global all_messages
  global game_created
  global made_first_move
  global board

  # reset variables
  active_players = Queue()
  live_idnums = []
  all_messages = []

  game_created = True # True since a new game has been created
  made_first_move = False

  board = tiles.Board()

  for key, player in all_players.items():
    player.hadPlayerTurn = False
    print(player.idnum)
    all_messages.append(tiles.MessagePlayerJoined(player.name, player.idnum))


  all_players_list = list(all_players.keys())
  random.shuffle(all_players_list)
  num_players = min(len(all_players), 4)

  for i in range(num_players):
    add_player = all_players[all_players_list[i]]
    active_players.put(add_player)
    live_idnums.append(add_player.idnum)
  
  send_to_all(tiles.MessageGameStart())
  first_player = list(active_players.queue)[0]
  send_to_all(tiles.MessagePlayerTurn(first_player.idnum))
  all_players[first_player.idnum].hadPlayerTurn = True

  for idnum in live_idnums:
    player = all_players[idnum]
    for _ in range(tiles.HAND_SIZE):
      tileid = tiles.get_random_tileid()
      player.connection.send(tiles.MessageAddTileToHand(tileid).pack())



def next_player(eliminated):
  '''determines the next player of the game by rearragning the queue and removing any people that got eliminated'''
  global live_idnums
  global active_players
  global game_created

  live_idnums = []
  tempList = list(active_players.queue)
  current_player = active_players.get()
  tempList = list(active_players.queue)
  tempList.append(current_player)

  active_players = Queue()

  for player in tempList:
    if player.idnum not in eliminated:
      active_players.put(player)
      live_idnums.append(player.idnum)

  print(list(active_players.queue))

  if (active_players.qsize() > 1):
    next_p = list(active_players.queue)[0]
    send_to_all(tiles.MessagePlayerTurn(next_p.idnum))
    all_players[next_p.idnum].hadPlayerTurn = True
  else:
    game_created = False

def send_to_all(msg):
  '''sends a message to all the players'''
  for key, player in all_players.items():
    player.connection.send(msg.pack())
  
  all_messages.append(msg)

def client_handler(connection, address, idnum):
  # global variables
  global live_idnums
  global all_players
  global active_players
  global all_messages
  global game_created
  global made_first_move
  global board

  host, port = address
  name = '{}:{}'.format(host, port)
  
  all_players[idnum] = Player(connection, name, idnum, False)

  connection.send(tiles.MessageWelcome(idnum).pack())

  # notifiy all exisitng players of the new player and notify the new player of all existng players
  for key, player in all_players.items():
    if not made_first_move:
      connection.send(tiles.MessagePlayerJoined(player.name, player.idnum).pack())
    if player.idnum != idnum:
      player.connection.send(tiles.MessagePlayerJoined(name, idnum).pack())
  
  if (len(all_players) > 1) and not made_first_move:
    send_to_all(tiles.MessageCountdown())
    if not game_created:
      game_created = True
      time.sleep(10)
    new_game()

  # if game has already started then update the new plyayer of the current game state
  if made_first_move:
    for msg in all_messages:
      connection.send(msg.pack())

  buffer = bytearray()

  while True:
    if (len(all_players)) > 1 and (not game_created):
      send_to_all(tiles.MessageCountdown())
      if not game_created:
        game_created = True
        time.sleep(10)
      new_game()

    chunk = connection.recv(4096)
    if not chunk:
      print('client {} disconnected'.format(address))
      return

    buffer.extend(chunk)

    while True:
      msg, consumed = tiles.read_message_from_bytearray(buffer)
      if not consumed:
        break

      buffer = buffer[consumed:]

      print('received message {}'.format(msg))

      # sent by the player to put a tile onto the board (in all turns except
      # their second)
      if (name == list(active_players.queue)[0].name):
        print("1-----")
        if isinstance(msg, tiles.MessagePlaceTile):
          print("2-----")
          if board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
            print("3-----")
            if not made_first_move:
              made_first_move = True
            # notify client that placement was successful
            send_to_all(msg)

            # check for token movement
            positionupdates, eliminated = board.do_player_movement(live_idnums)

            for msg in positionupdates:
              send_to_all(msg)
            
            for idnum in eliminated:
              send_to_all(tiles.MessagePlayerEliminated(idnum))

            # pickup a new tile
            tileid = tiles.get_random_tileid()
            connection.send(tiles.MessageAddTileToHand(tileid).pack())

            # start next turn
            next_player(eliminated)

        # sent by the player in the second turn, to choose their token's
        # starting path
        elif isinstance(msg, tiles.MessageMoveToken):
          if not board.have_player_position(msg.idnum):
            if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
              # check for token movement
              positionupdates, eliminated = board.do_player_movement(live_idnums)

              for msg in positionupdates:
                send_to_all(msg)
              
              for idnum in eliminated:
                send_to_all(tiles.MessagePlayerEliminated(idnum))
              
              # start next turn
              next_player(eliminated)


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
