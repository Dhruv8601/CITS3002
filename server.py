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
  def __init__(self, connection, name, idnum, had_player_turn = False, num_turn = 0):
    self.connection = connection
    self.name = name
    self.idnum = idnum
    self.had_player_turn = had_player_turn
    self.num_turn = num_turn

'''-------------------------------------------------------------------------------'''
def new_game():
  '''initialises the game state variables and creates a new game'''
  global all_players
  global active_players
  global live_idnums
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

  # for key, player in all_players.items():
  #   player.connection.send(tiles.MessageGameStart().pack())
  send_to_all(tiles.MessageGameStart())
  
  for key, player in all_players.items():
    player.had_player_turn = False
    player.num_turn = 0

    for key2, player2 in all_players.items():
      player.connection.send(tiles.MessagePlayerJoined(player2.name, player2.idnum).pack())
  
  

  all_players_list = list(all_players.keys())
  random.shuffle(all_players_list)
  num_players = min(len(all_players), 4)

  for i in range(num_players):
    add_player = all_players[all_players_list[i]]
    active_players.put(add_player)
    live_idnums.append(add_player.idnum)

  
  first_player = list(active_players.queue)[0]
  send_to_all(tiles.MessagePlayerTurn(first_player.idnum))
  all_players[first_player.idnum].hadPlayerTurn = True
  all_players[first_player.idnum].num_turn += 1

  for idnum in live_idnums:
    player = all_players[idnum]
    for _ in range(tiles.HAND_SIZE):
      tileid = tiles.get_random_tileid()
      player.connection.send(tiles.MessageAddTileToHand(tileid).pack())
  
  
  
'''-------------------------------------------------------------------------------'''

'''-------------------------------------------------------------------------------'''
def next_player(eliminated):
  '''determines the next player of the game by rearragning the queue and removing any people that got eliminated'''
  global live_idnums
  global active_players
  global game_created
  global made_first_move
  global all_players

  live_idnums = []
  curr_player = active_players.get()
  pre_elim = list(active_players.queue)
  pre_elim.append(curr_player)

  active_players = Queue()

  for player in pre_elim:
    if player.idnum not in eliminated:
      active_players.put(player)
      live_idnums.append(player.idnum)

  if len(live_idnums) < 2:
    game_created = False
    made_first_move = False
  
  if game_created:
    next_turn = list(active_players.queue)[0]
    print(next_turn.idnum)
    send_to_all(tiles.MessagePlayerTurn(next_turn.idnum))
    all_players[next_turn.idnum].had_player_turn = True
    all_players[next_turn.idnum].num_turn += 1


'''-------------------------------------------------------------------------------'''

'''-------------------------------------------------------------------------------'''
def send_to_all(msg):
  '''sends a message to all the players'''
  for key, player in all_players.items():
    player.connection.send(msg.pack())
  
  all_messages.append(msg)
'''-------------------------------------------------------------------------------'''

def client_handler(connection, address, idnum):
  global all_players
  global active_players
  global live_idnums
  global all_messages
  global game_created
  global made_first_move
  global board
  host, port = address
  name = '{}:{}'.format(host, port)

  all_players[idnum] = Player(connection, name, idnum)
  connection.send(tiles.MessageWelcome(idnum).pack())

  if len(all_players) > 1 and not made_first_move:
    new_game()

  # if game has already started then update the new plyayer of the current game state
  if made_first_move:
    for key, player in all_players.items():
      connection.send(tiles.MessagePlayerJoined(player.name, player.idnum).pack())
      if player.idnum != idnum:
        player.connection.send(tiles.MessagePlayerJoined(name, idnum).pack())

    for msg in all_messages:
      connection.send(msg.pack())

  buffer = bytearray()

  while True:
    if len(all_players) > 1 and not made_first_move and not game_created:
      new_game()

    chunk = connection.recv(4096)
    if not chunk:
      print('client {} disconnected'.format(address))
      return

    if name == list(active_players.queue)[0].name:
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
          if board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
            if not made_first_move:
              made_first_move = True
            # notify client that placement was successful
            send_to_all(msg)

            # check for token movement
            positionupdates, eliminated = board.do_player_movement(live_idnums)

            for msg in positionupdates:
              send_to_all(msg)
            
            if idnum in eliminated:
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
              
              if idnum in eliminated:
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
