# TR-1um profile

Tokai-Rika 1um IP62/OpenSUSI process port. The profile uses **standard SCMOS
lambda** (`lambda = 0.5 um`) as the compatibility family, not `scmos_subm`.
The native KLayout drawing DRC/LVS runsets remain the physical authority for
this profile; `rules.yaml` contains explicit native-aligned values for the
shared generator and is not a replacement signoff deck.

## Source boundary

The port is pinned to `OpenSUSI/TR-1um` commit
`d83eb77fcbe8c587809dd9f4532f9464c5501ab2`, under Apache-2.0. Copied native
sources and the license are under `reference/`; source model files are under
`models/source/`. No foundry signoff, complete corner set, or characterized
RC is claimed.

## Devices and models

Core and HV MOS bindings use calibrated-source BSIM primitive cards
`NMOS_mst`, `PMOS_mst`, `MNE_mst`, and `MPE_mst` for ngspice/xschem and Magic
PEX. The native LVS classes remain `NMOS`, `PMOS`, and `NMOSE`, matching the
OpenSUSI writer. Diode and passive subcircuits are ported as source model
contracts.

The source DRC derives `WB` as a bipolar-well recognition region, but the
current public LVS deck has no standalone BJT extractor, symbol, or model
card. `parasitic_npn` is therefore reference-only and simulator-disabled;
adding a fabricated NPN model would make the port less correct.

HVCMOS is available as an exploratory native marker contract. V15/V27 marker
layers are preserved; no generic SCMOS voltage inference is enabled.

## Verification boundary

- `reference/klayout/drc/run.drc` and `reference/klayout/lvs/run.lvs` are the
  current native OpenSUSI decks.
- `reference/klayout/python/cells/` is the native KLayout PCell source.
- `pex/manifest.yaml` is an engineering Magic extraction contract using the
  copied native `TR-1um.tech`; it owns sheet/interconnect RC while junction and
  intrinsic terms remain model-owned.
- `cells.yaml` is a candidate geometry contract derived from the source
  standard-cell access manifest. It is not a qualified standard-cell library.
