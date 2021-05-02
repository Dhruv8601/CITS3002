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

board = tiles.Board()
players = {}

playerTurn = 0
playerTurnId = 0

class Player:
  def __init__(self, connection, name, idnum):
    self.connection = connection
    self.name = name
    self.idnum = idnum



def client_handler(connection, address, idnum):
  host, port = address
  name = '{}:{}'.format(host, port)
  
  global playerTurnId
  global playerTurnIdId

  new_player = Player(connection, name, idnum)
  players[idnum] = new_player
  
  live_idnums = [players[player].idnum for player in players]
  print(live_idnums)

  connection.send(tiles.MessageWelcome(idnum).pack())

  for player in players:
    player = players[player]
    connection.send(tiles.MessagePlayerJoined(player.name, player.idnum).pack())
    
    if player.idnum != idnum:
      player.connection.send(tiles.MessagePlayerJoined(name, idnum).pack())

  
  connection.send(tiles.MessageGameStart().pack())
  if len(live_idnums) > 0:
    for player in players:
      player = players[player]
      player.connection.send(tiles.MessageGameStart().pack())
      player.connection.send(tiles.MessagePlayerTurn(playerTurn).pack())

      for _ in range(tiles.HAND_SIZE):
        tileid = tiles.get_random_tileid()
        player.connection.send(tiles.MessageAddTileToHand(tileid).pack())

  current_player = players[live_idnums[playerTurnId]]
  
  # for player in players:
  #   player = players[player]
  #   player.connection.send(tiles.MessagePlayerTurn(current_player.idnum).pack())
  # connection.send(tiles.MessageGameStart().pack())
  # for _ in range(tiles.HAND_SIZE):
  #   tileid = tiles.get_random_tileid()
  #   connection.send(tiles.MessageAddTileToHand(tileid).pack())
  #current_player.connection.send(tiles.MessagePlayerTurn(current_player.idnum).pack())
  

  buffer = bytearray()

  while True:
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
      if (idnum == live_idnums[playerTurnId]):
        if isinstance(msg, tiles.MessagePlaceTile):
          if board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
            # notify client that placement was successful
            connection.send(msg.pack())

            # check for token movement
            positionupdates, eliminated = board.do_player_movement(live_idnums)

            for msg in positionupdates:
              connection.send(msg.pack())
            
            if idnum in eliminated:
              connection.send(tiles.MessagePlayerEliminated(idnum).pack())
              return

            # pickup a new tile
            tileid = tiles.get_random_tileid()
            connection.send(tiles.MessageAddTileToHand(tileid).pack())

            # start next turn
            live_idnums = [players[player].idnum for player in players]
            playerTurnId = (playerTurnId + 1) % len(live_idnums)
            print()
            print(live_idnums)
            print()
            print(playerTurnId)
            next_player = players[live_idnums[playerTurnId]]
            next_player.connection.send(tiles.MessagePlayerTurn(next_player.idnum).pack())

        # sent by the player in the second turn, to choose their token's
        # starting path
        elif isinstance(msg, tiles.MessageMoveToken):
          if not board.have_player_position(msg.idnum):
            if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
              # check for token movement
              positionupdates, eliminated = board.do_player_movement(live_idnums)

              for msg in positionupdates:
                connection.send(msg.pack())
              
              if idnum in eliminated:
                connection.send(tiles.MessagePlayerEliminated(idnum).pack())
                return
              
              # start next turn
              live_idnums = [players[player].idnum for player in players]
              playerTurnId = (playerTurnId + 1) % len(live_idnums)
              print(playerTurnId)
              next_player = players[live_idnums[playerTurnId]]
              next_player.connection.send(tiles.MessagePlayerTurn(next_player.idnum).pack())


# create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# listen on all network interfaces
server_address = ('', 30020)
sock.bind(server_address)

print('listening on {}'.format(sock.getsockname()))

sock.listen(5)

idCount = 0

while True:
  # handle each new connection independently
  connection, client_address = sock.accept()

  thread = threading.Thread(target=client_handler, args=(connection, client_address, idCount))
  thread.start()

  idCount += 1
  print('received connection from {}'.format(client_address))
  #client_handler(connection, client_address)
