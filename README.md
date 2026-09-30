# siliconcraft — an open-EDA PDK from the NCSU CDK

Siliconcraft converts NCSU CDK 1.6.0 SCMOS-era process collateral into a
source-driven, multi-process PDK for the open toolchain: KLayout, xschem,
ngspice, Magic, netgen, LibreLane, and SiliconCompiler.

Process data intentionally remains split into reviewable source fragments:
`layers.yaml`, `rules.yaml`, `devices.yaml`, model contracts, PEX manifests,
and UI geometry. `common/process_ir.py` composes those fragments into one
normalized `ProcessIR` at generator/runtime boundaries. There is no required
monolithic process YAML.

## ProcessIR and canonical contracts

- `common/devices/canonical/mos.yaml` defines the process-independent
  `mos4` family (`nmos_core`/`pmos_core`, symmetric HV, and isolated variants)
  plus the separate asymmetric `asymmetric_mos4` family for `nldmos`/`pldmos`.
  Voltage class, gate stack, isolation domain, topology, and terminal semantics
  are canonical attributes; LDMOS D/S terminals are never LVS-permutable.
- `profiles/*/devices/bindings.yaml` binds canonical devices to layout,
  simulator, and LVS identities. `common/devices/netlist.py` exposes the
  validated typed contract.
- `profiles/*/symbols.yaml` contains only xschem UI geometry and pin placement.
  Netlist formatting/defaults are in `devices/symbol_netlist.yaml`.
- `common/devices/models.py` separates model identity, simulation/LVS
  capability, evidence, maturity, and fit parameters while preserving the
  source model YAML.
- PEX topology device identity comes from canonical bindings; PEX manifests
  retain extraction coefficients and explicitly declare model-vs-PEX parasitic
  ownership.

- CI selects profiles from `ProcessCapabilities` (`pex_runtime`, `pcells`,
  and related contracts), not from a hard-coded process tuple. New profiles
  enter a gate only when their fragments provide the required capability.

The MOS PCell uses `nf` for physical gate fingers and `m` for electrical
multiplicity. `m` does not change one-instance layout geometry; effective
simulation width is `w * nf * m`.

### SCMOS rule families and target profiles

The normalized SCMOS contract separates the rule family from the process
profile. `meta.rule_family` is one of `scmos`, `scmos_subm`, or the explicit
source-backed `scmos_deep`; non-SCMOS profiles use `native`. `scmos_deep` is
reserved for the NCSU CDK `SCN5M_DEEP`/`SCN6M_DEEP` contracts and their
source-backed rule overlays. It is not a generic small-lambda switch.
See [`docs/scmos_deep.md`](docs/scmos_deep.md) for the DRC/LVS and PEX boundary.

### XH035/XH018 authority and HVCMOS boundary

XH profiles keep rule authority explicit at runtime:
`public_native` contains only native-datasheet geometry,
`scmos_compat` adds SCMOS compatibility overrides and the
`provisional_hv_policy`, and `foundry_private` is reserved for unreleased
foundry collateral. Generate the named XH decks with:

```bash
python3 scripts/gen_drc.py --profile xh035 --authority public_native
python3 scripts/gen_drc.py --profile xh035 --authority scmos_compat \
  --output profiles/xh035/generated/drc/xh035-scmos-compat.drc
```

The `.drc` files preserve release naming; generated Python companions are the
KLayout-runnable decks. XH voltage classification is strict in production:
`HV:<potential>` and `LV:<potential>` annotations are required, `UNKNOWN` is
reported, and marker inference is exploratory-only. XH035/XH018 remain outside
the supported stdcell profile list; their LV semantic adapters are smoke-test
contracts only, and HV cells are not ordinary stdcells.

### XH public PEX, model, and tapeout boundary

The XH035/XH018 public PEX contract is intentionally split:

- `public_r_only` uses public-typical sheet resistance and emits
  `R_wire_only = R_sheet * length / width`. Contact and via resistance remain
  `unknown`; they are never guessed or folded into wire resistance.
- `field_solver_estimated` emits canonical FastCap/FasterCap/Palace sweep
  descriptions and consumes a parameterized public BEOL fit. It produces no
  foundry QRC table and is not calibrated or signoff-qualified.
- Active substrate extraction remains
  `external_foundry_or_calibrated_substrate_extractor`; ordinary SCMOS/Magic
  RC is forbidden for the HVCMOS substrate network.

Run a deterministic wire-only estimate with:

```bash
python3 scripts/run_r_only_pex.py --profile xh018 \
  --segment metal1:10:0.56
python3 scripts/gen_field_solver_sweep.py --profile xh018
```

XH model records use maturity levels `L0` contract-only, `L1` public
surrogate, `L2` silicon-calibrated, and `L3` foundry-private. Both profiles
remain at `L0`; no official BSIM/HiSIM card is claimed. Candidate L1 forms
are explicit (`bsim3v3` for core, `bsim4_external_hv_elements` or `HiSIM_HV`
for HV, and a MOS4 + drift-resistor + body-diode topology for LDMOS).

`profiles/xh018/characterization.yaml` and
`profiles/xh035/characterization.yaml` define MPW structures for MOS W/L,
Kelvin interconnects, contact/via chains, PIP/MIM/comb capacitors, FO4, ring
oscillators, and temperature points. The tracked
`oracle_overlay.yaml` files define an environment-selected private overlay;
NDA model cards, runsets, QRC databases, and foundry stream maps stay outside
Git.

XH018's `reference_maps/EFXH018D_lite.yaml` is a public ontology/numeric-anchor
cross-check only. The XH 300/100-series profile maps remain
`internal_logical`; a current foundry-authoritative map is required for
tapeout.

`schema/scmos_process_matrix.yaml` records the supported NCSU target mapping:
TSMC 0.35 4M/2P and 4M options, `tsmc03` (`SCN5M_SUBM`, lambda 0.15),
`tsmc02` (`SCN6M_SUBM`, lambda 0.10), plus the explicit DEEP profiles
`tsmc025_deep` (`SCN5M_DEEP`, lambda 0.12) and `tsmc018_deep`
(`SCN6M_DEEP`, lambda 0.09). The DEEP profiles have shared reference
DRC/LVS coverage and deferred TSMC PEX; they are not foundry signoff PDKs.
No 130 nm or other DEEP profile is inferred from node size or lambda.

### Historical SCMOS reference matrix

The requested historical ports are recorded separately in
[`schema/historical_scmos_process_matrix.yaml`](schema/historical_scmos_process_matrix.yaml)
and summarized in [`docs/historical_scmos.md`](docs/historical_scmos.md). This
reference matrix covers Orbit 2.0, AMI ABN 1.2, HP CMOS34, AMI CWL,
historical HP CMOS26B and HP CMOS26G standard/SUBM, HP MOS14TB
standard/SUBM, and HP GMOS10QA standard/SUBM. It records MOSIS option codes,
lambda, feature layers, tight metal/SUBM overlays, historical Magic PEX
methods, and provenance.

The matrix is intentionally `reference_only`: it creates no active profile,
calibrated model, signoff DRC/LVS, or signoff PEX claim. In particular:

- Orbit's exact historical PEX is the bundled `SCNA20(ORB)` branch; archive
  `SCNA.80` is labeled `AMIabn` and is not silently treated as Orbit.
- `SCNPC`/`CPC` AMI CWL poly capacitors are distinct from `SCNLC`/`CWC`
  cap-well/linear capacitors.
- Bundled `SCN08(HP)` is retained as the historical HP CMOS26B rich 3M
  extraction branch, while archive `SCN3M.50.tech27` says `HPcmos26g`.
- No exact GMOS10QA Magic target was found; `SCN4M_SUBM.20.tech27` is retained
  only as a TSMC35-labeled 4M/SUBM backend grammar reference.

Non-TSMC PEX source discovery and promotion blockers are tracked in
[`schema/scmos_legacy_pex_audit.yaml`](schema/scmos_legacy_pex_audit.yaml).
Internet SCMOS rules and Magic technology files provide geometry/extraction
grammar; active coefficients remain paired to local MOSIS reports and model
cards. TSMC DEEP PEX is intentionally deferred.

### SCMOS 7.2 device extensions

[`docs/scmos72_device_extensions.md`](docs/scmos72_device_extensions.md) plus the
`option_rule_families` registry in the historical matrix record the three-way
status (defined / DRC+LVS / λ-scalable) of every SCMOS 7.2 option family:
electrode capacitor/transistor/contact, vertical NPN, linear capacitor, buried
CCD, silicide-block poly resistor, SCNPC `POLY_CAP1`, HVCMOS (CVP/CVN —
undeclared option, no official λ rules and **none implemented by default**;
the Magic AMI 1.5 µm 20.x set applies only under an explicit
`hvcmosLambdaOverride` opt-in enforced by `common/process_ir.py`), and MEMS
(declared option, no rules, process-specific µm guidelines only).

The 2001a and 2002a Magic archives are separate from the bundled `scmos.tech`;
release, target label, and conditional source context are preserved.

### All-profile collateral coverage

[`schema/profile_collateral_matrix.yaml`](schema/profile_collateral_matrix.yaml)
is the coverage contract for every materialized profile. Each profile now has
an xschem UI symbol set plus explicit device netlist identities. Simulatable
profiles have a named ngspice library/section; XH018/XH035 deliberately expose
contract-only identities because no public simulator cards were found. Each
profile also names its primary Magic PEX, external field-solver, public-R-only,
or deferred route; missing contact/via, substrate, corner, and calibration
terms remain blocked.

The general engineering default is `ami06`: it is the integrated bootstrap
path combining source-backed DRC/LVS, nominal SPICE, xschem/ngspice smoke,
native Magic PEX, and the existing conformance gates. AMI16 and HP06 are
source-backed SCMOS alternate candidates, but their process-specific
device/row/corner contracts remain narrower. `field_solver_default` remains
`none`; field-solver reconstructions are external research RC inputs and never
become signoff defaults automatically.

The matrix contracts are checked by
`scripts/test_profile_collateral_matrix.py` and
`scripts/test_field_solver_contracts.py`.

### SPICE/PEX stdcell preparation

[`schema/stdcell_spice_pex_readiness.yaml`](schema/stdcell_spice_pex_readiness.yaml)
and [`docs/stdcell_spice_pex.md`](docs/stdcell_spice_pex.md) record the
generator-facing model, corner, canonical-device, Magic PEX, parasitic
ownership, and signoff blockers. AMI06 has process-independent INV and
two-input combinational geometry loops with authoritative DRC/LVS gates: INV
and NAND2 use the two-metal classic path; the legal NOR2 fixture uses the
three-metal classic path.

The fixed-height geometry planner now has explicit, rule-derived candidate
contracts for `ami06`, `ami16`, `hp06`, `cnm25`, `ams_c35`, and `tr1um`. These
contracts are not foundry standard-cell row libraries: public process/rule
sources did not establish universal row heights for the newly covered
profiles.
AMI16/HP06 use a stdcell-only SCMOS rule adapter instead of inheriting the
shared analog PCell technology assumptions. Pin, power, bulk, PEX, corner,
LEF, Liberty, and signoff claims remain gated separately.

The implemented IR path covers CircuitIR, explicit PUN/PDN diffusion graphs,
Euler/line-of-diffusion ordering, folding enumeration, P/N gate-column
alignment, contactless internal diffusion with explicit shared-active bridges,
difference-constraint compaction, fixed-height VSS/VDD rails, layer-aware
A*/Dijkstra routing, congestion-aware track selection, feedthrough resource
reservation, and a KLayout renderer. The process-decoupled search,
two-metal/three-metal routing architectures, Pareto metrics, and OpenROAD
block-level evaluation boundary are defined in
[`schema/stdcell_generator_contract.yaml`](schema/stdcell_generator_contract.yaml).
Generated candidate manifests expose diffusion sharing/breaks, gate alignment,
contactless sides, supply-contact planning, row-orientation policy, and
feedthrough columns. `gen_stdcell.py --beam-width N` applies cheap
routing estimates and placement-first bounded Pareto pruning before detailed
routing. The generic gate's optional `--lef` flag emits a syntax-complete
geometry-plan abstract; it is explicitly not a validated placement, Liberty,
timing, or power view.

### Routing grammar import and native probes

[`schema/routing_grammar_contract.yaml`](schema/routing_grammar_contract.yaml)
defines the conservative PDK import boundary. `scripts/inspect_routing_grammar.py`
first reads `ProcessIR` and any readable KLayout `.lylvs` connectivity/device
declarations. `scripts/run_routing_grammar.py` can then generate deterministic
positive/negative micro-layout probes and run native DRC plus native
LVS/extraction once per probe (`--require-native` turns missing native evidence
into a failing command). The classifier has four states:
`SUPPORTED`, `EXPERIMENTAL`, `UNKNOWN`, and `FORBIDDEN`; a missing LVS
declaration is `UNKNOWN`, never physical impossibility.

The probe suite covers lateral continuity, contact/transition, active
crossings, same-layer shorts, inter-layer isolation, T-junctions, and
accidental MOS detection. Optional monotonic sweeps cover local width,
same-layer spacing, and contact/via enclosure only; conditional and density
rules remain owned by the native deck. Process-specific butting contacts,
alternate enclosure/spacing patterns, and local-interconnect shortcuts are
not inferred from layer names: they run only when the profile explicitly
declares the feature and the native probe result supports it.
`common/stdcell/routing.py` compiles the resulting conductor IDs, transition
edges, region constraints, and conservative costs into the existing
pattern-routing → A*/maze → negotiated-congestion path. If a profile provides
sheet resistance, resistance-per-length, nominal width, or maximum useful
length, the graph adds a bounded linear or `log1p(R)` desirability cost;
missing electrical data leaves the value unknown and never invents a timing,
power, reliability, or signoff claim.

AMI06 currently has no readable KLayout `.lylvs` source, which only limits
static pre-inference. Its generic SCMOS LVS backend remains usable native
extraction evidence and is invoked by the probe runner: DRC pass plus the
expected extracted port/device relation is `SUPPORTED`; insufficient
extraction evidence remains `EXPERIMENTAL` or `UNKNOWN`. The Python backend
does not create a missing static declaration, but its native extraction is
not disabled.


- AMI06 is the bootstrap reference: it has MOS PCells, xschem/ngspice smoke,
  and source-reference Magic PEX in one path.
- AMI16 and HP06 now have explicit fixed-height, rule-derived stdcell
  candidate contracts, native source-reference PEX, and nominal model cards.
  Their generated geometry remains blocked from signoff by missing native
  pin/bulk/corner/characterization evidence.
- CNM25 (IMB-CNM academic 2.5 µm, 2-poly/2-metal) has a conservative
  fixed-height candidate contract in addition to its two DRC abstractions:
  the classic-SCMOS deck (lambda=1.5 µm, native 2.5 µm contact cut) and the
  native APDK deck. LVS uses the shared SCMOS engine; Magic PEX is unavailable.
  Its prepared FastCap/FastHenry flow (`scripts/run_cnm25_em.py`) is an
  external field-solver reconstruction and emits sweep manifests, not
  calibrated RC coefficients.
- AMS C35 (0.35 µm mixed-signal, TSMC-licensed base) has a rule-derived
  fixed-height candidate contract. Its ENG-183 exceptions (VIA 0.5 µm,
  select/active 0.45 µm, N+/P+ enclosure 0.25 µm, stacked vias), generated
  xschem/ngspice MOS symbols, and analog PCells remain process-specific.
  Magic PEX is unavailable; the ENG-182/stack-based field-solver route is
  estimated only, and the licensed kit is the tapeout authority.
- TR-1um is a Tokai-Rika 1um/OpenSUSI IP62 port using standard SCMOS lambda
  (`lambda=0.5um`, not SUBM) plus explicit native AP/AN/WN/HVCMOS overrides.
  Its native KLayout DRC/LVS and PCell sources are preserved under
  `profiles/tr1um/reference/`; Magic PEX and ngspice models are engineering
  references only. The native deck recognizes bipolar-well material but does
  not expose a standalone BJT extractor or model, so the BJT contract remains
  reference-only.
  The checked-in TR source-reference smoke fixture is
  `common/tests/gds/tr1um_inv_x1.gds` with
  `common/tests/spice/tr1um_inv_x1.spice`; its native DRC, native LVS adapter,
  and engineering Magic PEX are runnable without the external OpenSUSI
  checkout. The native stdcell gate selects the reference DRC/LVS decks from
  `profiles/tr1um/cells.yaml`; Liberty remains unavailable, so this is not a
  signoff library.
- LS1u is a subcircuit/topology reference with partial model evidence.
  Its checked-in `ls1u_mos_pair` GDS/SPICE fixture passes the native
  reference DRC/LVS decks; model/PEX evidence remains provisional.
- OpenRule1um's 45-cell GDS/38-symbol catalog is reference-only; LEF, Liberty,
  and PEX are unavailable/deferred.



## Current SCMOS behavior

The active AMI06, HP06, AMI16, CNM25, AMS C35, and TR-1um DRC/PEX
contracts retain their source-driven, process-specific limits and coefficients
where declared. AMI06/HP06/AMI16 carry the `pearlriver-scmos.tech` Magic
carrier; CNM25 and AMS C35 are DRC/LVS-first profiles with external
field-solver contracts but no Magic backend, while TR-1um uses its copied
native `TR-1um.tech` Magic carrier. Native decks live under
`profiles/<name>/reference/` where provided. Each manifest also declares a
matched legacy SCMOS backend where applicable for geometry/connectivity
cross-checking:

- AMI06 and HP06: `scmos-sub`, extraction style `lambda=0.30`;
- AMI16: `scmos`, extraction style `lambda=0.8(scna16_ami)`.

`common/pex/magic.py` validates that the selected legacy backend matches the
profile lambda. The legacy gate
(`scripts/run_scmos_legacy_check.py`) runs the installed Magic technology on
`common/tests/magic/scmos_crosscheck.mag` and requires both NMOS and PMOS
extraction, equal primitive-device counts, and matching drain/gate/source
connectivity between the active and legacy technologies.

This is a geometry/connectivity cross-check. It does not replace the
process-specific source coefficients and is not a calibrated or signoff PEX
deck.

### Well-routing diagnostic

`common/pex/magic.py` provides `without_well_routing()`. It removes only the
normal nwell/pwell self-connect rules while preserving high-voltage well rules,
other connectivity, each profile's GDS input map, and its generated extract
section. This mirrors the archived `scmosWR.tech` diagnostic semantics without
replacing the active process technology.

`scripts/run_scmos_well_route_check.py` extracts the AMI06 DRC fixture with
normal and diagnostic technologies for AMI06, HP06, and AMI16. The gate requires
a changed connectivity signature so accidental routing through wells remains
observable.

Both SCMOS gates run from `scripts/run_pex_ci.py`.

### Archived SCMOS references

- [Magic technology catalog](https://opencircuitdesign.com/magic/tech.html)
- [Magic 2001a archive](https://opencircuitdesign.com/magic/archive/2001a.tar.gz)
- [Magic 2002a archive](https://opencircuitdesign.com/magic/archive/2002a.tar.gz)
- [`scmos-sub.tech`](https://opencircuitdesign.com/magic/archive/scmos-sub.tech)
- [`scmos-tm.tech`](https://opencircuitdesign.com/magic/archive/scmos-tm.tech)
- [`scmos.tech`](https://opencircuitdesign.com/magic/archive/scmos.tech)
- [`scmosWR.tech`](https://opencircuitdesign.com/magic/archive/scmosWR.tech)

The archived decks are conservative historical references. The active process
manifests remain authoritative for AMI_C5N/N8BN, HP_AMOS14TB/N8AG, and
AMI_ABN/N88Z.

## Verification

Static PEX contracts:

```bash
python3 scripts/run_pex_ci.py --static-only
```

Rule-family and ProcessIR contracts:

```bash
python3 scripts/test_process_ir.py
python3 scripts/test_scmos_rule_families.py
```
OpenRule1um portable legality/efficiency contract:

```bash
python3 scripts/test_openrule1um_portable.py
```


Historical SCMOS matrix contract:

```bash
python3 scripts/test_historical_scmos.py
```

Stdcell SPICE/PEX readiness contract:

```bash
python3 scripts/test_stdcell_spice_pex.py
```

Stdcell generator architecture contract:

```bash
python3 scripts/test_stdcell_generator_contract.py
```

Stdcell generator implementation smoke:

```bash
python3 scripts/test_stdcell_generator.py
nix-shell -p klayout netgen python3 --run \
  "python3 scripts/run_stdcell_inv_gate.py"
nix-shell -p klayout netgen python3 --run \
  "python3 scripts/run_stdcell_gate.py --profile ami06
  --architecture two_metal_classic --cell nand2_drc
  --input common/tests/spice/stdcell/nand2_drc.spice
  --schematic common/tests/spice/stdcell/nand2_drc_reference.spice
  --workdir build/stdcell/ami06/nand2_gate"
nix-shell -p klayout netgen magic-vlsi ngspice python3 --run \
  "python3 scripts/run_stdcell_gate.py --profile ami06
  --architecture two_metal_classic --cell nand2_drc
  --input common/tests/spice/stdcell/nand2_drc.spice
  --schematic common/tests/spice/stdcell/nand2_drc_reference.spice
  --workdir build/stdcell/ami06/nand2_gate_pex_lef --pex --lef"
nix-shell -p klayout netgen python3 --run \
  "python3 scripts/run_stdcell_gate.py --profile ami06
  --architecture three_metal_classic --cell nor2_drc
  --input common/tests/spice/stdcell/nor2_drc.spice
  --schematic common/tests/spice/stdcell/nor2_drc_reference.spice
  --workdir build/stdcell/ami06/nor2_gate"
```


KLayout PCell `nf`/`m` round-trip:

```bash
nix-shell -p klayout python3 --run \
  "python3 scripts/test_primitive_roundtrip.py --profile ami06"
```

Native Magic/ngspice contracts, including the SCMOS gates:

```bash
nix-shell -p magic-vlsi ngspice python3 --run \
  "python3 scripts/run_pex_ci.py"
```

The native gate covers AMI06, HP06, AMI16, TR-1um source-reference PEX,
and LS1u extraction/model smokes, plus legacy SCMOS backend checks and
normal-vs-`scmosWR` well-routing checks for profiles with a compatible
legacy backend.
TR-1um source-reference DRC/LVS/PEX and native stdcell candidate smoke:

```bash
nix develop ~/Documents/librelane --command bash -lc '
  python3 scripts/run_drc.py --profile tr1um --deck reference \
    --layout common/tests/gds/tr1um_inv_x1.gds --top-cell INV_X1 \
    --out /tmp/tr1um.drc.lyrdb --summary /tmp/tr1um.drc.json && \
  python3 scripts/run_lvs.py --profile tr1um --deck reference \
    --layout common/tests/gds/tr1um_inv_x1.gds \
    --schematic common/tests/spice/tr1um_inv_x1_lvs.spice --top-cell INV_X1 \
    --workdir /tmp/tr1um.lvs && \
  python3 scripts/run_magic_pex_smoke.py --profile tr1um && \
  python3 scripts/run_stdcell_gate.py --profile tr1um \
    --architecture two_metal_classic --cell inv \
    --input common/tests/spice/stdcell/tr1um_inv.spice \
    --schematic common/tests/spice/stdcell/tr1um_inv_lvs.spice \
    --workdir /tmp/tr1um.stdcell --pex --lef'
```

`run_stdcell_gate.py` defaults to the profile's `verification` deck contract;
AMI06-style profiles continue to default to authoritative decks.


xschem UI/netlist binding and ngspice smoke:

```bash
nix-shell -p xschem ngspice python3 --run \
  "python3 scripts/run_xschem.py --profile ami06"
```

The same gate can be run for `ls1u`; its subcircuit binding keeps simulator
parameters in `devices/symbol_netlist.yaml`, separate from symbol geometry.
CNM25 uses the checked-in connected inverter fixture and a positive
`-i(v2)` supply-current probe because its subcircuit instances do not expose
ngspice primitive `@instance[id]` vectors:

```bash
nix-shell -p xschem ngspice python3 --run \
  "python3 scripts/run_xschem.py --profile cnm25"
```


AMS C35 xschem and KLayout analog-PCell smoke:

```bash
nix-shell -p xschem ngspice python3 --run \
  "python3 scripts/run_xschem.py --profile ams_c35"
python3 scripts/test_ams_c35_pcells.py
```

The AMS PCell fixture can also be checked with the native reference DRC:

```bash
nix develop ~/Documents/librelane --command bash -c \
  'SILICONCRAFT_PROFILE=ams_c35 SILICONCRAFT_OUTPUT=build/pcells/ams_c35.gds \
   klayout -b -r scripts/run_pcells.py && \
   klayout -b -r profiles/ams_c35/reference/klayout/ams_c35_native.lydrc \
   -rd input=build/pcells/ams_c35.gds -rd output=build/pcells/ams_c35.lyrdb'
```

## Repository map

- `profiles/`: process layer maps, rules, models, Magic PEX manifests, and generated views;
- `common/`: process-neutral renderers, runtime helpers, fixtures, and shared tool logic;
- `scripts/`: generators, conformance checks, and runtime gates;
- `schema/`: metadata schema;
- `adapters/`: ecosystem integration points;
