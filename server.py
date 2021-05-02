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

board = tiles.Board()

def client_handler(connection, address, idnum):
  global all_players
  global active_players
  global player_turn
  global player_turn_index
  global live_idnums
  global game_running
  global board

  host, port = address
  name = '{}:{}'.format(host, port)

  new_player = Player(connection, name, idnum)
  active_players[new_player.idnum] = new_player
  all_players[new_player.idnum] = new_player

  live_idnums = [active_players[player].idnum for player in active_players]

  connection.send(tiles.MessageWelcome(idnum).pack())

  for key, player in active_players.items():
    connection.send(tiles.MessagePlayerJoined(player.name, player.idnum).pack())
    if player.idnum != idnum:
      player.connection.send(tiles.MessagePlayerJoined(name, idnum).pack())
  
  if (len(all_players)) > 1:
    game_running = True
    board = tiles.Board()
    for key, player in all_players.items():
      player.connection.send(tiles.MessageGameStart().pack())
      player.connection.send(tiles.MessagePlayerTurn(player_turn).pack())

      for _ in range(tiles.HAND_SIZE):
        tileid = tiles.get_random_tileid()
        player.connection.send(tiles.MessageAddTileToHand(tileid).pack())
    
  print(live_idnums)
  

  buffer = bytearray()

  while True:
    if (len(all_players)) > 1 and (not game_running):
      print("NEW GAME SHOULD BE STARTING RIGHT NOW")
      time.sleep(1)
      game_running = True
      board = tiles.Board()
      player_turn = 0
      player_turn_index = 0
      live_idnums = []
      active_players = {}
      
      for key, player in all_players.items():
        active_players[player.idnum] = player
      live_idnums = [active_players[player].idnum for player in active_players]

      print(live_idnums)

      for key, player in active_players.items():
        player.connection.send(tiles.MessageGameStart().pack())
        player.connection.send(tiles.MessagePlayerTurn(player_turn).pack())

        for _ in range(tiles.HAND_SIZE):
          tileid = tiles.get_random_tileid()
          player.connection.send(tiles.MessageAddTileToHand(tileid).pack())

    chunk = connection.recv(4096)
    if not chunk:
      print('client {} disconnected'.format(address))

      del all_players[idnum]
      return

    buffer.extend(chunk)

    while True:
      msg, consumed = tiles.read_message_from_bytearray(buffer)
      if not consumed:
        break

      buffer = buffer[consumed:]

      #print('received message {}'.format(msg))

      # sent by the player to put a tile onto the board (in all turns except
      # their second)
      if (idnum == player_turn and game_running):
        if isinstance(msg, tiles.MessagePlaceTile):
          if board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
            # notify client that placement was successful
            for key, player in active_players.items():
              player.connection.send(msg.pack())

            # check for token movement
            positionupdates, eliminated = board.do_player_movement(live_idnums)

            for msg in positionupdates:
              for key, player in active_players.items():
                player.connection.send(msg.pack())
            
            for el_idnum in eliminated:
              for key, player in active_players.items():
                player.connection.send(tiles.MessagePlayerEliminated(el_idnum).pack())
              del active_players[el_idnum]
              live_idnums = [active_players[player].idnum for player in active_players]
            if len(live_idnums) < 2:
              game_running = False

            # pickup a new tile
            if game_running:
              tileid = tiles.get_random_tileid()
              connection.send(tiles.MessageAddTileToHand(tileid).pack())

              # start next turn
              player_turn_index = (player_turn_index + 1) % len(live_idnums)
              player_turn = live_idnums[player_turn_index]

              for key, player in active_players.items():
                player.connection.send(tiles.MessagePlayerTurn(player_turn).pack())

        # sent by the player in the second turn, to choose their token's
        # starting path
        elif isinstance(msg, tiles.MessageMoveToken):
          if not board.have_player_position(msg.idnum):
            if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
              # check for token movement
              positionupdates, eliminated = board.do_player_movement(live_idnums)

              for msg in positionupdates:
                for key, player in active_players.items():
                  player.connection.send(msg.pack())
              
              for el_idnum in eliminated:
                for key, player in active_players.items():
                  player.connection.send(tiles.MessagePlayerEliminated(el_idnum).pack())
                del active_players[el_idnum]
                live_idnums = [active_players[player].idnum for player in active_players]
              if len(live_idnums) < 2:
                game_running = False
              
              # start next turn
              if game_running:
                player_turn_index = (player_turn_index + 1) % len(live_idnums)
                player_turn = live_idnums[player_turn_index]

                for key, player in active_players.items():
                  player.connection.send(tiles.MessagePlayerTurn(player_turn).pack())
      else:
        print(f"It is player {player_turn}'s turn. Please wait for your turn player {idnum}.")


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
