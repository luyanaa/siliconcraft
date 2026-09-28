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

- `common/devices/canonical/mos.yaml` defines the process-independent MOS4
  terminals, D/S symmetry, geometry units, `w`/`nf`/`m` semantics, and
  parasitic ownership.
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
profile. `meta.rule_family` is one of `scmos` or `scmos_subm`; non-SCMOS
profiles use `native`. `SCMOS_DEEP`, `deep_rules`, and `submicron_rules` are
not normalized assets. The shared DRC/PCell engines implement only the
standard-vs-SUBM split.

`schema/scmos_process_matrix.yaml` records the supported NCSU target mapping:
TSMC 0.35 4M/2P and 4M options, `tsmc03` (`SCN5M_SUBM`, lambda 0.15), and
`tsmc02` (`SCN6M_SUBM`, lambda 0.10). The matrix also records
`DEEP_N_WELL` as a layer capability. The upstream CDK DEEP techfiles remain
provenance-only and are explicitly forbidden by the matrix; this policy does
not remove unrelated `DEEP` controls in LS1u/OpenRule1um reference decks.

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

The 2001a and 2002a Magic archives are separate from the bundled `scmos.tech`;
release, target label, and conditional source context are preserved.

### SPICE/PEX stdcell preparation

[`schema/stdcell_spice_pex_readiness.yaml`](schema/stdcell_spice_pex_readiness.yaml)
and [`docs/stdcell_spice_pex.md`](docs/stdcell_spice_pex.md) record the
generator-facing model, corner, canonical-device, Magic PEX, parasitic
ownership, and signoff blockers. AMI06 now has process-independent INV and
two-input combinational geometry loops with authoritative DRC/LVS gates: INV
and NAND2 use the two-metal classic path; the legal NOR2 fixture uses the
three-metal classic path.

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


- AMI06 is the first bootstrap candidate: it has MOS PCells, xschem/ngspice
  smoke, and source-reference Magic PEX in one path.
- AMI16 and HP06 have native source-reference PEX and nominal model cards but
  no stdcell geometry or xschem characterization contract.
- LS1u is a subcircuit/topology reference with partial model evidence.
- OpenRule1um's 45-cell GDS/38-symbol catalog is reference-only; LEF, Liberty,
  and PEX are unavailable/deferred.



## Current SCMOS behavior

The active AMI06, HP06, and AMI16 PEX manifests retain their source-driven
`pearlriver-scmos.tech` carrier and process-specific coefficient sections. Each
manifest also declares a matched legacy SCMOS backend for geometry/connectivity
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
AMI_ABN/N77H.

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
nix-shell -p klayout netgen magic ngspice python3 --run \
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
nix-shell -p magic ngspice python3 --run \
  "python3 scripts/run_pex_ci.py"
```

The native gate covers AMI06, HP06, AMI16, and LS1u extraction/model smokes,
legacy SCMOS backend checks, and normal-vs-`scmosWR` well-routing checks.

xschem UI/netlist binding and ngspice smoke:

```bash
nix-shell -p xschem ngspice python3 --run \
  "python3 scripts/run_xschem.py --profile ami06"
```

The same gate can be run for `ls1u`; its subcircuit binding keeps simulator
parameters in `devices/symbol_netlist.yaml`, separate from symbol geometry.

## Repository map

- `profiles/`: process layer maps, rules, models, Magic PEX manifests, and generated views;
- `common/`: process-neutral renderers, runtime helpers, fixtures, and shared tool logic;
- `scripts/`: generators, conformance checks, and runtime gates;
- `schema/`: metadata schema;
- `adapters/`: ecosystem integration points;
