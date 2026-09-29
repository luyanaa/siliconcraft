# CNM25 EM flow: FastCap (C) + FastHenry (R/L) from GDS

## Toolchain coverage (APDK library bridging)

Beyond the EM bridge below, the APDK Glade libraries are bridged into
siliconcraft:

- **xschem symbols** — `profiles/cnm25/symbols.gen.yaml` +
  `devices/symbol_netlist.gen.yaml`, emitted by
  `scripts/gen_cnm25_apdk_symbols.py` (parses the Glade binary symbols and
  the XSpice `.ifs` port tables), merged by `scripts/gen_symbols.py` into
  `generated/xschem/`. 116 APDK symbols: 34 SPICE3Lib primitives (native
  SPICE prefixes), 72 XSpiceLib instances (resolved to their code models,
  instance line + `.model` code-model line), 11 XtendedLib elements, plus
  `ground`. The PiP `cap` symbol keeps the handwritten cnm25 binding.
  XSpice digital elements need an ngspice/SpiceOpus build with XSpice
  enabled; symbols are UI/netlist contracts, verified by
  `scripts/test_cnm25_apdk_symbols.py`.
- **KLayout PCells** — `profiles/cnm25/reference/klayout/pcells.py`, a hand
  port of the APDK Glade pcells (cnm25modn_m/modp_m/cpoly_m with w/l/mx/my
  and common-* options; NMOS bulk on PWELL, PMOS on NTUB). Validated by
  `scripts/test_cnm25_pcells.py`; a 4-device GDS run through
  `cnm25_native.lydrc` reports **zero DRC violations**.

## Cross section (from `glade/cnm25.tch`)

The CNM25 APDK ships a **field-solver PEX path** (Glade → FastCap) whose
capacitance extraction is solid but whose **R extraction is weak**: the 2D
deck (`cnm25pex_2d.py`) is parallel-plate C only, FastCap is a pure
capacitance solver, and no resistance/inductance deck ships with the APDK.
This document records the prepared GDS→EM bridge for the next stage
(parasitic R/L and post-layout RF re-simulation).

## Cross section (from `glade/cnm25.tch`)

| Conductor | GDS | Height (bottom z) [um] | Thickness [um] |
| --- | ---: | ---: | ---: |
| METAL  (metal1) | 7/0 | 1.000 | 1.000 |
| VIA    (m1-m2)  | 10/0 | 2.000 | 0.800 |
| METAL2 (metal2) | 9/0 | 2.800 | 1.100 |

Insulator stack (manual Fig. 44): field oxide 1060 nm, inter-metal oxide
1300 nm; SiO2 er ≈ 3.9.

## Converters

`scripts/run_cnm25_em.py --layout in.gds --workdir build/em`

- reads the layout with the KLayout Python API;
- assigns net names from text labels on GDS layer 64/0 (APDK pin/net layers
  20..25 are UI purposes; the converter uses text labels like the siliconcraft
  LVS);
- emits `build/em/cnm25_caps.lst` (FastCap: per-net rectangular conductors
  with the cross section above; bulk/ref node `vss` per APDK convention) and
  `build/em/cnm25_rl.lst` (FastHenry: Manhattan filament segments from the
  orthogonal rectangle decomposition, vertical via segments, 1 MHz–10 GHz
  frequency sweep).

## Running the solvers

FastCap and FastHenry are the MIT FastField solvers (not bundled here):

```sh
fastcap -f build/em/cnm25_caps.lst      # capacitance matrix (good accuracy)
fasthenry build/em/cnm25_rl.lst         # R/L matrix (verify mesh density)
```

`--meshn/--meshw` control FastHenry filament counts; wide power buses need
more filaments than minimum-width signal wires.

## Known limits

- **C is trustworthy** (FastCap boundary-element field solve over the
  CNM25 cross section); the 2D parallel-plate densities remain the fast
  fallback and are recorded in the PEX manifest (`profiles/cnm25/pex/
  manifest.yaml`).
- **R is the weak spot of the APDK flow**: FastHenry needs the full 3-D
  conductor geometry and a decent mesh, and the APDK itself ships no R
  extraction. For timing-oriented RC, use the sheet-resistance fallback
  (PEX manifest) and reserve FastHenry for RF/interconnect R/L.
- Substrate coupling is not modeled by FastCap/FastHenry; the APDK folds
  bulk/infinite-boundary couplings into node `vss`.
- The converter emits straight-line filaments without bends: polygons are
  rectangle-decomposed, so corners are approximate. Acceptable for first
  pass; refine with `FastHenry2`-style 3-D boxes if corners matter.

## Next step (post-layout simulation)

Convert the FastCap/FastHenry matrices to a SPICE subcircuit per net pair
(e.g. with `fastcap2spice`/`fasthenry2spice`-style scripts) and re-run the
`test_oa_*.sp3`-style benches against the extracted netlist, exactly like
the APDK post-layout flow (`apdk_cnm25_v2024_04_09.pdf`, §3.10–3.11).
