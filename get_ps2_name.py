#!/usr/bin/python

import sys

sys.path.append('identify_playstation2_games')
from identify_playstation2_games import get_playstation2_game_info

info = get_playstation2_game_info(sys.argv[1])
print(info['title'])
