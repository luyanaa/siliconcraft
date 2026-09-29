import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pya
import pcells
out = os.environ.get("CNM25_PCELL_GDS") or "/tmp/cnm25_pcell_devices.gds"
ly = pya.Layout()
for (gds, dt) in set(pcells.LAY.values()):
    ly.insert_layer(pya.LayerInfo(gds, dt))
ly.dbu = 0.001
pcells.register(ly)
top = ly.create_cell("TOP")
for name, params, inst in (
    ("cnm25modn_m", dict(w=4.5, l=3.0), (0.0, 0.0)),
    ("cnm25modn_m", dict(w=10.0, l=3.0, mx=2, my=1, common_d=1), (0.0, 30.0)),
    ("cnm25modp_m", dict(w=4.5, l=3.0), (40.0, 0.0)),
    ("cnm25cpoly_m", dict(w=30.0, l=30.0), (40.0, 40.0)),
):
    dev = ly.create_cell(name, params)
    t = pya.Trans(pya.Trans.R0, int(inst[0]*1000), int(inst[1]*1000))
    top.insert(pya.CellInstArray(dev.cell_index(), t))
ly.write(out)
print("wrote", out)
