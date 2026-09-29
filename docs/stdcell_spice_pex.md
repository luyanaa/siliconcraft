# SPICE and PEX readiness for the stdcell generator

The machine-readable preparation contract is [`schema/stdcell_spice_pex_readiness.yaml`](../schema/stdcell_spice_pex_readiness.yaml). The planner now has explicit rule-derived fixed-height geometry candidates for `ami06`, `ami16`, `hp06`, `cnm25`, and `ams_c35`; this is deliberately not a foundry standard-cell library and does not claim timing, power, Liberty, or signoff. The generator can emit a geometry-plan LEF-compatible abstract, but that view is not a signoff library view.

## Current SPICE status

| Profile | SPICE representation | Current model IDs | Current corner contract | Current evidence |
| --- | --- | --- | --- | --- |
| `ami06` | Primitive MOS4 | `ami06N`, `ami06P` | Nominal only in `ami06` section | xschem/ngspice smoke passes; native PEX output simulates; stdcell INV/NAND2/NOR2 DRC/LVS smoke passes |
| `ami16` | Primitive MOS4 | `ami16N`, `ami16P` | Nominal only in `ami16` section | Native PEX output simulates; stdcell INV authoritative DRC/LVS/PEX/LEF smoke passes; no xschem smoke contract |
| `hp06` | Primitive MOS4 | `hp14tbN`, `hp14tbP` | Nominal only in `hp06` section | Native PEX output simulates; stdcell INV authoritative DRC/LVS/PEX/LEF smoke passes; no xschem smoke contract |
| `cnm25` | Primitive MOS4 | `cnm25modN`, `cnm25modP` | Nominal only in `cnm25` section | Stdcell INV authoritative DRC/LVS/LEF smoke passes; no Magic runtime PEX backend |
| `ams_c35` | Primitive MOS4 | `c35N`, `c35P` | Nominal only in `ams_c35` section | Stdcell INV authoritative DRC/LVS/LEF smoke passes; no Magic runtime PEX backend |
| `ls1u` | `LV1UNMOS` / `LV1UPMOS` subcircuits | `LV1UNMOS`, `LV1UPMOS` | No process-corner contract; partial characterization | xschem/ngspice and native Magic MOS smoke pass |
| `openrule1um` | Model-contract-only | `or1_nmos`, `or1_pmos` plus passive variants | No corner contract | Measured primitive model contract; no active canonical bindings |

### Important SPICE details

- AMI06, AMI16, and HP06 generated libraries are public BSIM3v3 nominal cards. The materialized files contain one `.lib` section each; the generator can consume CDK corner directories when supplied, but no fast/slow/fnsp/snfp sections are currently emitted in these artifacts.
- Their canonical binding is stable for a generator: terminal order `d,g,s,b`, primitive `M` representation, and `w/l/nf/m/ad/as/pd/ps` parameter maps.
- LS1u uses `X` subcircuits rather than primitive `M` instances and intentionally exposes only `W/L/PD/PS`. The PMOS fit is low confidence; `NGATE` and `PGATE` remain unmeasured. A generator must not assume the AMI/HP parameter map applies to LS1u.
- OpenRule1um has a useful measured primitive model contract and standard-cell reference catalog, but no active canonical device binding, so it cannot yet be consumed by the shared stdcell characterization path.

## Current PEX status

### AMI06, AMI16, HP06

The active manifests are source-driven Magic extraction contracts:

- model/device identity comes from the profile bindings;
- Magic is the geometry/connectivity backend;
- source coefficients come from the NCSU CDK branch;
- output is ngspice-compatible extracted SPICE;
- transistor intrinsic, gate-overlap, and junction capacitances remain model-owned;
- diffusion sheet resistance and metal interconnect RC are PEX-owned;
- contact/via resistance is emitted per cut from the MOSIS parametric reports (AMI06 N8BN, HP06 N8AG, AMI16 N88Z); direct junction/substrate mappings remain withheld in the current reference profiles;
- the profile capability is `pex_rc=estimated`, not characterized/signoff.

### CNM25 and AMS C35

Both ports are DRC/LVS-first: they carry no Magic extraction backend, so
`pex_runtime`/`pex_rc` stay false and no RC coefficients are emitted yet.

- CNM25: the APDK field-solver path is the intended PEX route — FastCap 3D
  capacitance (cross-section data in `profiles/cnm25/reference/klayout/`
  deck provenance and `docs/cnm25_em_flow.md`) is solid, while the APDK has
  no R extraction; the FastHenry GDS→EM preparation ships in
  `scripts/run_cnm25_em.py`. The 2D parallel-plate densities are recorded in
  the PEX manifest as the fast fallback.
- AMS C35: interconnect PEX is deferred; the ENG-188 RF model topology
  (BSIM3v3.1 + RG/RD/RS + RSUB + external junction diodes) owns the device
  parasitics and is recorded as a contract in `model_contract.yaml`. ams
  model cards are company confidential and user-supplied.

The native extraction smoke verifies model names, primitive MOS count, parasitic capacitors, and an ngspice operating point. It does not prove a standard-cell pin contract, corner coverage, contact-chain calibration, or timing accuracy.

### LS1u

The current manifest provides four-terminal MOS topology and native Magic/ngspice extraction smoke coverage. Its `scmos_legacy` coefficients are explicitly not LS1u calibration, and the HKUST dry/wet profiles are estimates or unparameterized. Treat LS1u PEX as topology-only for stdcell preparation until measured LS1u RC and contact/via data exist.

### OpenRule1um

PEX is explicitly deferred:

```yaml
status: deferred
signoff: false
```

Its 45-cell GDS / 38-symbol catalog is a conformance input, not a characterized standard-cell implementation. LEF and Liberty are unavailable upstream.

### XH035/XH018 public PEX and model boundary

The XH profiles deliberately expose a research-only split instead of
pretending that a public datasheet restores the foundry deck:

1. `profiles/xh035/pex/manifest.yaml` and `profiles/xh018/pex/manifest.yaml`
   provide public-typical metal sheet resistance for `R_wire_only`.
   `scripts/run_r_only_pex.py` applies
   `R = R_sheet * length_um / width_um`; contact and via resistance are
   explicit `unknown` exclusions.
2. `field_solver_estimated` is a separate contract. The BEOL files
   `xh035_beol_public_fit.yaml` and `xh018_beol_public_fit.yaml` describe
   fitted/estimated thickness and ILD parameters, required canonical sweeps,
   and the FastCap/FasterCap/Palace -> research RC table -> OpenRCX/custom
   boundary. `calibrated: false` and `signoff: false` are mandatory.
3. HVCMOS substrate extraction remains an external foundry or calibrated
   distributed-substrate backend. Ordinary SCMOS/Magic RC is not permitted to
   stand in for the substrate network.

The XH model maturity contract is `L0` contract-only, `L1` public surrogate,
`L2` silicon-calibrated, or `L3` foundry-private. Current XH profiles are
`L0`; no official BSIM4 or HiSIM card is restored. L1 candidate model forms
are recorded without enabling simulation until public Vth/Idsat/fT and
geometry evidence exists. XH LDMOS D/S order remains physical and
non-permutable.

The characterization manifests specify MOS W/L matrices, Kelvin metal and
diffusion structures, contact/via chains, PIP/MIM/comb/crossing capacitors,
FO4 fixtures, ring oscillators, and temperature points. Private oracle
overlays are environment-selected and may provide official SPICE, DRC, LVS,
QRC, and stream-map artifacts; no NDA collateral is tracked.

The XH018 `EFXH018D_lite.tech` reference snapshot is represented only as an
ontology/numeric-anchor cross-check. The internal 300/100-series maps are not
tapeout maps; a current foundry-authoritative stream map remains required.

## What the stdcell generator must consume

The generator boundary should be process-parameterized and fail closed. For each selected profile it must resolve:

1. **Geometry contract** — cell height, rail positions, site/grid, legal transistor/contact/via geometry, and profile layer/rule source.
2. **Pin/power/bulk contract** — ordered signal pins, `VDD`/`VSS` rails, substrate/well policy, labels, and top-cell port rules.
3. **Canonical device contract** — binding name, simulator representation, model ID, terminal order, geometry units, and parameter map.
4. **SPICE model contract** — model library path, explicit section, model IDs, nominal/process/voltage/temperature corners, and model limitations.
5. **PEX contract** — generated Magic profile, topology style, terminal order, source units, output format, and model-versus-PEX parasitic ownership.
6. **Characterization fixtures** — inverter, ring oscillator or delay chain, input slew/load grid, leakage/power conditions, and extracted-versus-schematic equivalence checks.
7. **Output views** — GDS, extracted SPICE, a geometry-plan LEF-compatible abstract, Liberty, and catalog metadata. Missing validated LEF/Liberty must block placement/timing claims.

A profile with only topology or nominal SPICE may be used for geometry and connectivity development, but not for signoff timing/power views.

## Generator architecture contract

The generator architecture is recorded separately in
[`schema/stdcell_generator_contract.yaml`](../schema/stdcell_generator_contract.yaml).
It is an architecture contract plus the implemented front-end and first
geometry/routing back-end; it does not claim a complete optimizer or signoff
library.

### Small process-decoupled API

The boundary is intentionally limited to four objects:

| Object | Responsibility |
| --- | --- |
| `CircuitIR` / `CellCircuit` | Parse annotated SPICE/CDL, preserve MOS topology, expose PUN/PDN diffusion graphs, resolve explicit or default `L`, and declare timing arcs. |
| `StdcellProcess` / `Process` | Resolve `ProcessIR` geometry, design rules, logical layer aliases, canonical devices, model identity, and PEX ownership. |
| `ColumnIR` / `Architecture` | Enumerate PMOS/NMOS gate orderings, diffusion breaks, folding-independent columns, row placement, cell height, rails, and legal routing layers. |
| `CandidatePlan` / `Candidate` | Hold sizing, ordering, folding, difference-constraint compaction, routing resources, verification state, and future PEX/characterization/Pareto metadata. |

The initial cell family is deliberately small: `INV`, `NAND2`, `NOR2`,
`AOI21`, `OAI21`, and `MUX2`. The first search keeps `L` at explicit input
values or process `Lmin`; explicit `weak_devices` metadata can add long-L
variants. It searches `Wn`, `Wp`, `nf`, cell height, generalized Euler
ordering, physical line-of-diffusion bridges, contactless internal diffusion,
P/N gate alignment, contact pattern, pin location, and routing candidates.
AOI/OAI, transmission-gate, and pass-transistor options are opt-in topology
records and require a supplied transistor topology plus later PEX/SPICE
characterization; the planner does not synthesize Boolean replacements.

The candidate lifecycle is:

```text
transistor netlist
  -> topology normalization and optional topology hints
  -> Euler ordering / diffusion-break enumeration
  -> folding enumeration
  -> exact geometry compaction
  -> shared-active/contactless diffusion realization
  -> pattern routing -> A*/maze -> negotiated congestion
  -> DRC/LVS
  -> PEX
  -> SPICE characterization
  -> Pareto filtering
```

For the first six cells, exhaustive ordering/folding enumeration is followed
by local/global geometry-Pareto and optional beam selection; `max_candidates`
is not used to truncate nested loops. Difference-constraint/longest-path
compaction remains preferred over MILP. Z3, CP-SAT, or MILP becomes an
escalation path for DFF/latch, multiple-height, or otherwise complex cells.

### Implemented first back-end slice

The repository now contains a process-independent IR path:

- `CircuitIR` plus explicit PMOS/NMOS `DiffusionGraph`;
- `ColumnIR` exhaustive P/N ordering alignment with deterministic LCS gaps;
- fixed-height, rule-derived SCMOS site contracts for AMI06, AMI16, HP06,
  CNM25, and AMS C35, with explicit overflow rejection;
- difference-constraint compaction into `GeometryIR`;
- row-level active/select/poly/contact geometry with shared-active bays and
  containment checks; self-tap geometry is rendered directly by the stdcell
  renderer so profiles without the analog PCell contract do not inherit it;
- a layer-aware rectangular `RoutingGraph` with A*/Dijkstra search,
  negotiated congestion fallback, grammar-compiled architecture policy, and
  via-access landing geometry;
- physical signal pin shapes and GDS text labels sourced from the same
  candidate IR used by LEF; LEF OBS excludes exported port nets;
- rail-correct `R0`/`MX` row metadata and explicit two-metal/three-metal
  architecture selection.

Geometry is resolved through each profile's named SCMOS rule deck
(`6.1`, `4.1`, `5.2.b`, `6.4`, `8.3`, and related rules); missing active
rules fail closed. The stdcell adapter uses the diffusion-contact-to-gate
spacing rule (`6.4`) rather than assuming the analog PCell adapter's optional
poly-contact rule (`5.5.b`). No lambda-derived rule fallback is used.

AMI06, AMI16, HP06, CNM25, and AMS C35 now have generated authoritative
geometry/connectivity INV smoke gates. AMI06 also covers NAND2/NOR2; AMI16
and HP06 additionally pass Magic PEX plus ngspice operating-point smoke.
CNM25 and AMS C35 remain DRC/LVS/LEF-only because their runtime PEX
backends are intentionally absent. Public native DRC macro decks for CNM25
and AMS C35 did not produce a report in this KLayout batch environment, so
they are not promoted to native signoff evidence.

The larger `nor2.spice` sizing fixture remains useful for folding/search
coverage. `--beam-width N` retains local and global geometry-Pareto fronts
before detailed graph routing; `max_candidates` is applied only after
detailed candidates are built and ranked. Generated manifests distinguish
geometry-estimated feedthrough resources from native verification, include
physical pin shapes, shared diffusion, rail/orientation, tap, supply-contact,
and feedthrough contracts; `--lef` emits a LEF-compatible abstract with
explicit non-signoff status. PEX-driven timing and power characterization,
Liberty emission, and signoff remain intentionally unimplemented.

### Routing grammar and search policy

The machine-readable routing-capability boundary is
[`schema/routing_grammar_contract.yaml`](../schema/routing_grammar_contract.yaml).
The importer first inspects `ProcessIR` and readable KLayout `.lylvs` sources,
then optionally generates deterministic positive/negative micro-layout probes.
Native DRC and native LVS/extraction are run once per probe, outside all
placement and router search. The evidence state is one of:
`SUPPORTED`, `EXPERIMENTAL`, `UNKNOWN`, or `FORBIDDEN`. Missing LVS support
remains `UNKNOWN`; it is not promoted to `FORBIDDEN`.

Probe categories include wire continuity, T-junctions, contact/transition,
active/diffusion crossings, same-layer shorts, inter-layer isolation, and
accidental MOS detection. Optional monotonic local sweeps cover width,
same-layer spacing, and contact/via enclosure. Process-specific butting
contacts, alternate enclosure/spacing patterns, and local-interconnect
shortcuts are profile-gated and require native evidence. Conditional and
density rules remain native-deck rules. Electrical fields stay explicitly
unknown unless supplied by the profile or characterization.

The implemented router stack is intentionally small and deterministic:

```text
pattern straight/L/Z
  -> A* / maze search
  -> negotiated-congestion rip-up/reroute
```

Multi-terminal nets use a Manhattan-distance MST followed by incremental
two-terminal routes. `RoutingPolicy.for_architecture_grammar()` compiles the
architecture's legal layers/directions together with grammar continuity,
transition, resistance, and maximum-useful-length evidence. Unknown static
evidence is accepted only for pre-native geometry search and is recorded in
the candidate manifest; native probes remain the verification boundary.
Resistance evidence contributes a linear or `log1p(R)` route desirability
term and optional maximum-useful-length penalty; it never overrides native
legality. The graph does not infer Poly/TiN semantics from names. AMI06
currently has no calibrated layer/contact resistance fields, so its generated
grammar carries unknown electrical values rather than fabricated costs.

The router treats previously materialized route metal and via landings as
physical obstacles: candidate graph edges are dilated by the exact profile
width/spacing/enclosure rules before subsequent nets are searched.  The
manifest and LEF `OBS` use the same final-shape IR; exported port nets are
subtracted rather than represented as center-point blockers.  Row topology
guards remain separate from this physical-obstacle map.

AMI06 has no readable KLayout `.lylvs` source in this repository. That only
limits static pre-inference: the existing generic SCMOS LVS backend is still
usable native extraction evidence, and the probe runner invokes it. A DRC
pass plus the expected extracted port/device relation is `SUPPORTED`; a DRC
pass without sufficient extraction evidence remains `EXPERIMENTAL` or
`UNKNOWN`. The Python LVS backend does not retroactively create a static
KLayout declaration, but it is not disabled by that absence.

### Two-metal routing contract

`M1` and `M2` in the architecture contract are logical layer aliases. The
`Process` object resolves them to actual profile layers; the generator must
not hard-code a process-specific layer name.

The physical policy is:

- Metal over active is allowed unless a contact, via, enclosure, spacing, or
  profile-specific rule forbids it. Active geometry is not a blanket M1
  blockage.
- Diffusion is a topology-constrained connection, not an ordinary routing
  layer. Shared diffusion remains the preferred low-cost connection when an
  Euler ordering permits it.
- Poly may be used for short local connections with a high resistance
  penalty; it is not inter-cell routing.
- M1 is the primary cell-internal layer and rail layer.
- M2 is preserved primarily for vertical inter-cell routing and feedthrough.
- Buried/local interconnect is unsupported unless the selected process
  explicitly supplies such a layer and rules.

Two architectures remain candidates:

1. `two_metal_classic`: M1 internal/rails, M2 external/feedthrough, at least
   one legal M2 transparent column, and at most two short internal M2
   segments for combinational cells.
2. `two_metal_dense`: permits more internal M2, but must export exact metal
   and via blockage maps and does not guarantee transparent feedthrough.

3. `three_metal_classic`: M1 local/rails, M2 local pin-access, and M3
   global/feedthrough. M2 is not forced to remain transparent; M3 is the
   global vertical layer and must export the legal global feedthrough columns.

Every candidate must export:

- metal and via blockage maps;
- M2 feedthrough columns;
- pin-access regions;
- diffusion/poly keepouts.

The initial routability metric is:

$$
P_\mathrm{route} =
\frac{N_\mathrm{legal\ M2\ pass\text{-}through\ tracks}}
     {W_\mathrm{cell}}
$$

Internal M2 length and via count are explicit optimization metrics. DRC,
LVS, pin access, rail/bulk connectivity, and the routing contract remain
hard constraints, not soft excuses for a compact but unusable cell.

### Characterization and Pareto policy

The cell-level metric set is at least:

$$
(A_\mathrm{cell},\ D,\ C_\mathrm{in},\ R)
$$

where:

$$
A_\mathrm{cell}=W_\mathrm{cell}H_\mathrm{cell}
$$

and:

$$
D=\max_{\text{timing arcs}} t_{pd}.
$$

`Cin` is retained so that widening a transistor cannot appear unconditionally
better. `R` includes route permeability, pin-access margin, internal M2
length, and via cost. Characterization uses extracted SPICE at FO1/FO2/FO4
and a profile-declared slew/load grid. PEX must precede characterization;
schematic-only delay is not a cell Pareto result.

Dominated candidates are removed when every tracked metric is no worse and
at least one is strictly better. `X1`, `X2`, and `X4` are library labels
selected after Pareto filtering; they are not a forced 1:2:4 physical
width ratio.

After cell-level filtering, OpenROAD evaluates area-oriented, balanced, and
speed-oriented library families on small SoC, ALU, FIFO, and multiplier
benchmarks. The baseline is fixed-lambda geometry with a fixed `Wp/Wn`
ratio. The retained result is the block-level non-dominated library in
`(post_route_area, Fmax)`, not necessarily the library containing the
fastest isolated cell.


## Recommended order

1. **Geometry candidates.** AMI06, AMI16, HP06, CNM25, and AMS C35 now
   resolve explicit fixed-height contracts; those contracts are derived
   candidates, not foundry row libraries.
2. **AMI06 bootstrap gate.** It remains the only profile with completed
   authoritative stdcell DRC/LVS/PEX gates, shared MOS PCells, and
   xschem/ngspice smoke in one path.
3. **AMI16 and HP06.** Their source-reference PEX and nominal model cards are
   available; native stdcell pin/bulk/corner/characterization fixtures remain.
4. **CNM25 and AMS C35.** Their geometry candidates are available, but PEX is
   topology-only and the licensed/native process decks remain authoritative.
5. **LS1u separately; OpenRule1um as a reference oracle only.**

The implemented slice intentionally stops before shared-active geometry for
folded wide complex cells, PEX-driven timing/power characterization, Liberty
emission, and timing/power signoff. A geometry-plan LEF-compatible abstract is
available, but it does not establish placement, pin-access, or signoff
library claims.

## Verification snapshot

Passed in the current workspace:

```bash
python3 scripts/test_process_ir.py
python3 scripts/run_pex_ci.py --static-only
python3 scripts/run_xschem.py --profile ami06
python3 scripts/run_xschem.py --profile ls1u
nix-shell ~/Documents/librelane --run \
  "python3 scripts/run_pex_ci.py"
python3 scripts/test_stdcell_spice_pex.py
python3 scripts/test_stdcell_generator.py
nix-shell -p klayout netgen python3 --run \
  "python3 scripts/run_stdcell_inv_gate.py"
nix-shell -p klayout netgen python3 --run \
  "python3 scripts/run_stdcell_gate.py --profile ami06
  --architecture two_metal_classic --cell nand2_drc
  --input common/tests/spice/stdcell/nand2_drc.spice
  --schematic common/tests/spice/stdcell/nand2_drc_reference.spice
  --workdir build/stdcell/ami06/nand2_gate"
nix-shell ~/Documents/librelane --run \
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

The native PEX gates passed for AMI06/AMI16/HP06 source-reference PEX,
SCMOS legacy/well-routing checks, LS1u extraction, and ngspice simulation.
The AMI06 stdcell gates above passed authoritative DRC and Netgen LVS for
INV, NAND2, and NOR2; the NAND2 gate also passed the persistent Magic/ngspice
PEX smoke and emitted the geometry-plan LEF abstract. The readiness regression
still reports missing PEX-driven stdcell characterization, validated
Liberty, and timing/power contracts as blockers.
