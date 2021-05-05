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
import time
import random

class Player:
  def __init__(self, connection, name, idnum):
    self.connection = connection
    self.name = name
    self.idnum = idnum

all_players = {}
active_players = {}
player_turn = 0
player_turn_index = 0
live_idnums = []

game_running = False
made_first_move = False

disconnected = []
new_disconnected = False

board = tiles.Board()

all_messages = []

num_move = 0


def new_game():
  global all_players
  global active_players
  global player_turn
  global player_turn_index
  global live_idnums
  global game_running
  global made_first_move
  global board

  print("NEW GAME WILL START IN 10 SECONDS")
  send_to_all(tiles.MessageCountdown())
  time.sleep(5)

  active_players = {}
  player_turn_index = 0
  live_idnums = []
  
  game_running = True
  made_first_move = False
  
  board = tiles.Board()

  all_players_list = list(all_players.keys())

  random.shuffle(all_players_list)

  num_players = min(len(all_players), 4)

  for i in range(num_players):
    add_player = all_players[all_players_list[i]]
    active_players[add_player.idnum] = add_player

  live_idnums = [active_players[player].idnum for player in active_players]
  player_turn = live_idnums[player_turn_index]


  send_to_all(tiles.MessageGameStart())
  send_to_all(tiles.MessagePlayerTurn(player_turn))

  for key, player in active_players.items():
    for _ in range(tiles.HAND_SIZE):
      tileid = tiles.get_random_tileid()
      player.connection.send(tiles.MessageAddTileToHand(tileid).pack())

def send_to_all(msg):
  global all_players
  global all_messages

  all_messages.append(msg)
  for key, player in all_players.items():
    player.connection.send(msg.pack())
  

def next_player(eliminated):
  global player_turn
  global player_turn_index
  global live_idnums

  found = False

  while not found: 
    player_turn_index = (player_turn_index + 1) % len(live_idnums)
    player_turn = live_idnums[player_turn_index]

    if player_turn not in eliminated:
      found = True

  live_idnums = [active_players[player].idnum for player in active_players]
  player_turn_index = live_idnums.index(player_turn)

  send_to_all(tiles.MessagePlayerTurn(player_turn))


def client_handler(connection, address, idnum):
  global all_players
  global active_players
  global player_turn
  global player_turn_index
  global live_idnums
  global game_running
  global made_first_move
  global board
  global disconnected
  global new_disconnected
  global num_move

  host, port = address
  name = '{}:{}'.format(host, port)

  new_player = Player(connection, name, idnum)
  all_players[new_player.idnum] = new_player


  connection.send(tiles.MessageWelcome(idnum).pack())
  
  all_messages.append(tiles.MessagePlayerJoined(name, idnum))

  for key, player in all_players.items():
    if not made_first_move:
      connection.send(tiles.MessagePlayerJoined(player.name, player.idnum).pack())
    if player.idnum != idnum:
      player.connection.send(tiles.MessagePlayerJoined(name, idnum).pack())

  if (len(all_players)) > 1 and not made_first_move:
    new_game()

  if made_first_move:
    for msg in all_messages:
      connection.send(msg.pack())



  buffer = bytearray()

  while True:
    if (len(all_players)) > 1 and (not game_running):
      new_game()

    if new_disconnected:
      new_disconnected = False
      print(list(all_players.keys()), idnum)

      for idnum in disconnected:
        if idnum in all_players:

          del all_players[idnum]
          del active_players[idnum]
          send_to_all(tiles.MessagePlayerEliminated(idnum))
          send_to_all(tiles.MessagePlayerLeft(idnum))
          if len(active_players) < 2:
            game_running = False
          else:
            next_player([idnum])

    if idnum not in disconnected:
      chunk = connection.recv(4096)
      if not chunk:
        print('client {} disconnected'.format(address))
        disconnected.append(idnum)
        new_disconnected = True
  
        

      if chunk:
        buffer.extend(chunk)

    while True:
      msg, consumed = tiles.read_message_from_bytearray(buffer)
      if not consumed:
        break

      buffer = buffer[consumed:]

      print('received message {}'.format(msg))

      # sent by the player to put a tile onto the board (in all turns except
      # their second)
      # if time.sleep(2):
      #   if num_move > 2 * len(active_players):
      #     msg = tiles.MessagePlaceTile 
      if (name == all_players[player_turn].name and game_running):
        num_move += 1
        if isinstance(msg, tiles.MessagePlaceTile):
          if not made_first_move:
            made_first_move = True
          if board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
            # notify client that placement was successful
            send_to_all(msg)

            # check for token movement
            positionupdates, eliminated = board.do_player_movement(live_idnums)

            for msg in positionupdates:
              send_to_all(msg)
            
            for idnum in eliminated:
              send_to_all(tiles.MessagePlayerEliminated(idnum))
              del active_players[idnum]
            if len(active_players) < 2:
              game_running = False

            # pickup a new tile
            tileid = tiles.get_random_tileid()
            connection.send(tiles.MessageAddTileToHand(tileid).pack())

            # start next turn
            if game_running:
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
                del active_players[idnum]
              if len(active_players) < 2:
                game_running = False  
              
              # start next turn
              if game_running:
                next_player(eliminated)
      else:
        print("Please wait for your turn!")


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
  thread = threading.Thread(target=client_handler, args=(connection, client_address, idnum))
  thread.start()
  
  idnum += 1
