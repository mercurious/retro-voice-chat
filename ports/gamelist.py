#!/usr/bin/env python3
"""Add, update or remove the Retro Voice Chat entry in EmulationStation's Ports gamelist.xml (install.sh runs it).

  gamelist.py GAMELIST LAUNCHER NAME DESC DEVELOPER IMAGE MARQUEE    add the entry, or update its fields
  gamelist.py GAMELIST LAUNCHER --remove                             drop it

LAUNCHER, IMAGE and MARQUEE are paths relative to the Ports folder ("./Retro Voice Chat.sh"). Everything else in
the file, and ES's own fields on this entry (playcount, lastplayed, gametime), is kept. The file is only written
when it changes, through a temporary file.
"""
import os
import sys
import xml.etree.ElementTree as ET


def same(a, b):
    strip = lambda p: (p or "").strip().removeprefix("./")
    return strip(a) == strip(b)


def main(argv):
    if len(argv) not in (4, 8):
        print(__doc__, file=sys.stderr)
        return 2
    path, launcher = argv[1], argv[2]
    old = None
    if os.path.exists(path):
        with open(path, "rb") as f:
            old = f.read()
        try:
            root = ET.fromstring(old)
        except ET.ParseError as e:
            print(f"gamelist.py: {path} is not valid XML ({e}); left as it is", file=sys.stderr)
            return 1
    else:
        root = ET.Element("gameList")
    games = [g for g in root.findall("game") if same(g.findtext("path"), launcher)]
    if argv[3] == "--remove":
        for g in games:
            root.remove(g)
    else:
        game = games[0] if games else ET.SubElement(root, "game")
        for g in games[1:]:
            root.remove(g)
        for tag, value in zip(("path", "name", "desc", "developer", "image", "marquee"), [launcher] + argv[3:]):
            el = game.find(tag)
            if el is None:
                el = ET.SubElement(game, tag)
            el.text = value
    ET.indent(root, space="\t")
    new = ('<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n").encode()
    if new != old:
        with open(path + ".tmp", "wb") as f:
            f.write(new)
        os.replace(path + ".tmp", path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
