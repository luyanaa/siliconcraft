"""Emit a mixed OpenRule1um primitive geometry fixture for LVS regression."""

from pathlib import Path

# Reuse the canonical four-MOS geometry and add isolated primitive structures.
exec(Path(__file__).with_name("make_openrule1um_portable.py").read_text(), globals())

# Poly resistor with terminal contacts overlapping the resistor ends.
rect("res", 122.0, 40.0, 138.0, 44.0)
rect("pol", 122.0, 40.0, 138.0, 44.0)
for cx in (121.0, 139.0):
    rect("cnt", cx - 1.0, 41.0, cx + 1.0, 43.0)
    rect("ml1", cx - 2.0, 40.0, cx + 2.0, 44.0)

# Metal1-on-poly capacitor.
rect("cap", 120.0, 10.0, 130.0, 20.0)
rect("pol", 118.0, 8.0, 132.0, 22.0)
rect("ml1", 122.0, 12.0, 132.0, 18.0)

# Metal2-on-metal1 capacitor.
rect("cap", 140.0, 10.0, 150.0, 20.0)
rect("ml1", 138.0, 8.0, 152.0, 22.0)
rect("ml2", 142.0, 12.0, 152.0, 18.0)

# N-diff/poly capacitor.  The narea marker selects ndiff_cap semantics.
rect("cap", 160.0, 10.0, 170.0, 20.0)
rect("diff", 158.0, 8.0, 172.0, 22.0)
rect("narea", 158.0, 8.0, 172.0, 22.0)
rect("pol", 162.0, 12.0, 168.0, 18.0)

# P-diff/poly capacitor.  The parea marker selects pdiff_cap semantics.
rect("cap", 180.0, 10.0, 190.0, 20.0)
rect("diff", 178.0, 8.0, 192.0, 22.0)
rect("parea", 178.0, 8.0, 192.0, 22.0)
rect("pol", 182.0, 12.0, 188.0, 18.0)

# P-diff resistor inside nwell.  The RES marker selects r_pdiff semantics.
rect("nwell", 225.0, 35.0, 247.0, 55.0)
rect("res", 228.0, 40.0, 244.0, 44.0)
rect("diff", 227.0, 40.0, 245.0, 44.0)
rect("parea", 226.0, 39.0, 246.0, 45.0)
for cx in (227.0, 245.0):
    rect("cnt", cx - 1.0, 41.0, cx + 1.0, 43.0)
    rect("ml1", cx - 2.0, 40.0, cx + 2.0, 44.0)

# Nwell resistor.  The RES marker selects r_nwell semantics.
rect("nwell", 260.0, 40.0, 282.0, 44.0)
rect("res", 263.0, 40.0, 279.0, 44.0)
for cx in (262.0, 280.0):
    rect("diff", cx - 1.0, 40.0, cx + 1.0, 44.0)
    rect("narea", cx - 1.0, 40.0, cx + 1.0, 44.0)
    rect("cnt", cx - 1.0, 41.0, cx + 1.0, 43.0)
    rect("ml1", cx - 2.0, 40.0, cx + 2.0, 44.0)


# P+ diode inside nwell plus a separate nwell tie.
rect("nwell", 202.0, 37.0, 218.0, 53.0)
rect("diff", 206.0, 41.0, 214.0, 49.0)
rect("parea", 205.0, 40.0, 215.0, 50.0)
rect("dio", 207.0, 42.0, 213.0, 48.0)
for cx in (208.0, 212.0):
    rect("cnt", cx - 0.75, 43.0, cx + 0.75, 44.5)
    rect("ml1", cx - 1.25, 42.5, cx + 1.25, 45.0)
rect("diff", 202.0, 48.0, 205.0, 51.0)
rect("narea", 201.0, 47.0, 206.0, 52.0)
rect("cnt", 202.5, 48.5, 204.5, 50.5)
rect("ml1", 202.0, 48.0, 205.0, 51.0)

background = layout.layer(200, 0)
top.shapes(background).insert(
    pya.Box(pya.DBox(0.0, 0.0, 300.0, 110.0).to_itype(DBU))
)

OUT.parent.mkdir(parents=True, exist_ok=True)
layout.write(str(OUT))
print(f"wrote OpenRule1um primitive LVS fixture {OUT}")
