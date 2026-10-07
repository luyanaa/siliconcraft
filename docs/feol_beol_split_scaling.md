# FEOL / BEOL split scaling: OpenRule1um vs CSMC

Status: **analysis only — no rule value changed.**

## The claim being tested

OpenRule1um's rule deck turned out to scale its FEOL and BEOL differently: the
FEOL fits the classic SCMOS arm, the BEOL fits the SUBM arm at a shrunk lambda
(see `openrule1um_scmos_override_review.md`). That was *inferred* from the rule
values. CSMC's document is the clean test case because it **declares** a split
node in its own title.

## Source

`eetop.cn_0.5um_FEOL_0.35um_BEOL_Mixed_Signal_Process_Design_Rule_WPI_73D78_4K08.pdf`
— CSMC QRA controlled document WPI-73D78(2), version 4K08, 45 pages:

> "0.5um FEOL/0.35um BEOL Double Poly Mixed Signal Technology Topological Design
> Rule" ... "topological layout rules for 0.5um FEOL/0.35um BEOL CMOS Twin well
> double poly quartus metal mixed signal technology."

It also states the shrinkage convention explicitly (section 8.0, general
comment 2):

> "All rules in this section are referred to the minimum **as drawn** dimensions.
> They are in micron. **If a design involves shrinkage, the shrunk dimensions
> should meet the rules in this section.**"

and comment 3:

> "When circuit density is not limited by these rules, increase the minimum rule
> values by 15% to 20% as applicable during layout."

## As-drawn values read off the document

FEOL (section 8.2 Active, 8.3 Poly1, 8.9 Contact):

| rule | um |
| --- | --- |
| active width (interconnect) | 0.5 |
| active width NMOS / PMOS | 0.5 / 0.6 |
| active spacing N+ to N+ | 0.8 |
| poly1 width / space | 0.5 / 0.5 |
| poly1 channel length NMOS | 0.5 |
| contact size | 0.4 |
| contact to contact space | 0.4 |
| active overlap contact P / N | 0.3 / 0.15-0.3 |
| poly1 overlap contact | 0.2 |

BEOL (section 8.10 Metal1, 8.12 Metal2, 8.15 Metal3, 8.11/8.14/8.17 Via):

| rule | um |
| --- | --- |
| metal1 width / space | 0.5 / 0.45 |
| metal2 width / space | 0.6 / 0.5 |
| metal3 width / space | 0.6 / 0.5 |
| via1/via2/via3 size | 0.5 x 0.5 |
| via to via space | 0.45 |
| metal1 overlap contact | 0.15 |
| metal1/metal3 overlap via | 0.2 |
| metal2 overlap via1 | 0.15 |

Note the vias (0.5um) are **larger** than the FEOL contacts (0.4um), and the metal
widths (0.5-0.6um) are larger than the poly/active minimum (0.5um). The BEOL is
not drawn at 0.35um; the "0.35um BEOL" label describes the process capability,
while the published as-drawn rules are conservative and the shrink is applied
afterwards.

## Result: same split, same direction

Applying the same test — solve `lambda_eff = value_um / branch_multiple`, and the
branch whose implied lambda is the most *consistent* is the better fit:

| domain | branch | lambda_eff median | stdev | implied node |
| --- | --- | --- | --- | --- |
| **FEOL** | **classic** | 0.2000 | **0.0421** | 0.400 um |
| FEOL | SUBM | 0.2000 | 0.0502 | 0.400 um |
| **BEOL** | classic | 0.1583 | 0.0429 | 0.317 um |
| **BEOL** | **SUBM** | 0.1583 | **0.0337** | 0.317 um |

Per-rule detail, discriminating rules only (where classic != SUBM):

| domain | rule | um | implied @0.25 | classic | SUBM | winner |
| --- | --- | --- | --- | --- | --- | --- |
| FEOL | poly1 space | 0.5 | 2.00 | 2.0 (err 0%) | 3.0 (err 33%) | **classic** |
| FEOL | contact-contact space | 0.4 | 1.60 | 2.0 (err 20%) | 3.0 (err 47%) | **classic** |
| BEOL | metal1 space | 0.45 | 1.80 | 2.0 (err 10%) | 3.0 (err 40%) | **classic** |
| BEOL | metal3 width | 0.6 | 2.40 | 6.0 (err 60%) | 5.0 (err 52%) | **SUBM** |
| BEOL | metal3 space | 0.5 | 2.00 | 4.0 (err 50%) | 3.0 (err 33%) | **SUBM** |

So: **FEOL fits classic, BEOL fits SUBM** — the same split found in OpenRule1um,
independently, on a process that declares its FEOL and BEOL nodes up front.

The implied nodes also reproduce the declared ratio. Declared 0.5 / 0.35 = 0.70;
observed 0.400 / 0.317 = **0.79**. Both are close to 1, and both put the BEOL
meaningfully below the FEOL — consistent with a BEOL that is shrunk relative to
the FEOL rather than processed at the same geometry.

## What this means

1. **The OpenRule1um inference is corroborated.** The FEOL/BEOL split is not an
   artefact of one deck; it reappears in a foundry document whose title states the
   two nodes.

2. **A single per-profile `scmos_variant` is the wrong shape.** Both processes need
   one branch for FEOL and another for BEOL. OpenRule1um currently declares
   `scmos_variant: non_submicron`, which is right for its FEOL and wrong for its
   BEOL.

3. **It explains why `beol: native_override` is the correct policy**, not merely a
   conservative one: the BEOL's own numbers already carry the shrunk scaling, so
   layering an unshrunk SCMOS envelope over them would be comparing different
   nodes.

4. **The wells stay on the FEOL side** in both processes, so the well rules keep
   the classic value and the earlier concern that SUBM would double them does not
   apply.

## Caveats

- CSMC's document is marked "REFERENCE ONLY (FOR FAB2)" and "REVISION
  UNAVAILABLE", and states electronic versions are uncontrolled. It is a design
  rule reference, not a run-qualified signoff deck, and is used here only as
  evidence about *scaling structure*, never as signoff data for any profile.
- The `lambda_eff` medians are partly driven by rules where classic and SUBM
  agree (identical multiples), which is why the stdev column and the
  discriminating-rules table carry the argument rather than the median alone.
- CSMC is not one of this repository's profiles; nothing here adds a CSMC profile
  or any CSMC rule value to `siliconcraft`.
