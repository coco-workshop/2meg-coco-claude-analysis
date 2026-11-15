#!/usr/bin/env python3
"""Dump a readable netlist from an Eagle (XML, v6+) schematic.

Usage: python3 eagle_netlist.py TwoMegCoCo_MMU_v1.1.sch

Each output line is:  NET_NAME : PART.GATE.PIN PART.GATE.PIN ...
Supply symbols (SUPPLYn, GNDn) and decoupling caps (Cn) are omitted.
Pin names come from the schematic's embedded library; use the deviceset
'connect' entries (or the .brd contactrefs) to map them to physical pads.
"""
import sys
import xml.etree.ElementTree as ET


def is_noise(part):
    return (part.startswith("SUPPLY") or part.startswith("GND")
            or (part[0] == "C" and part[1:].isdigit()))


def main(path):
    root = ET.parse(path).getroot()
    for net in root.iter("net"):
        refs = sorted({(p.get("part"), p.get("gate"), p.get("pin"))
                       for p in net.iter("pinref")})
        refs = [r for r in refs if not is_noise(r[0])]
        if not refs:
            continue
        pins = []
        for part, gate, pin in refs:
            show_gate = gate not in ("G$1", "A", "P") or part.startswith("IC")
            pins.append(f"{part}{'.' + gate if show_gate else ''}.{pin}")
        print(net.get("name"), ":", " ".join(pins))


if __name__ == "__main__":
    main(sys.argv[1])
