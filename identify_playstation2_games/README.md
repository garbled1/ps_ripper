
identify_playstation2_games
==========

https://github.com/workhorsy/identify_playstation2_games

A module for identifying Sony Playstation 2 games with Python 2 &amp; 3

Works with CD ISO, DVD ISO, and Binary files.


Example use:
-----
~~~python

from identify_playstation2_games import get_playstation2_game_info

info = get_playstation2_game_info("E:\Sony\Playstation2\Armored Core 3\Armored Core 3.iso")
print(info['serial_number'])
print(info['region'])
print(info['disc_type'])
print(info['title'])


# outputs:
# "SLUS-20435"
# "USA"
# "DVD"
# u"Armored Core 3"
~~~


