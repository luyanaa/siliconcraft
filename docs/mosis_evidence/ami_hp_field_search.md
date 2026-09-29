# AMI (C5N/CWL/ABN) and HP (AMOS14TB/GMOS10QA) field-stack search log

Retrieved 2026-09-29. Conclusion: no first-hand foundry thickness document
(conductor/ILD thickness, epsilon_r, substrate rho) is publicly available for
any of these five processes. The only physical-thickness value found is the
AMI C5N polysilicon figure from a NIST journal paper (below). Everything else
must be built `derived` from era ranges, per the policy in
`docs/process_flow_audit.md`.

## Sources checked (this session)

| Source | What it is | Thickness content |
| --- | --- | --- |
| NIST J. Res. 111(3):243-253 (2006), Geist et al., "Simple Thermal-Efficiency Model for CMOS-Microhotplate Design" (nvlpubs.nist.gov/nistpubs/jres/111/3/V111.N03.A05.pdf) | US-government journal, MOSIS-AMI C5N thermal model | **Polysilicon 0.4 um; glass encapsulation 3.2 um** (Table 1, thermal-model values; poly sheet 25 ohm/sq agrees with NCSU). No metal/IMD/FOX values. |
| UConn "AMI C5N Process Design Rules" v1.1 (2000-09, khan.engr.uconn.edu, sourced from mosis.org) | AMI C5N SCMOS rules + cross-section figure | None (lambda rules only; figure without numbers) |
| AMI C5X 0.5um design rules Rev T (2005-05-18) | ON Semi rules; revision history mentions metalization-thickness updates | Thickness table not accessible (studylib login wall; direct download requires auth) |
| iastate EE435 "AMI 0.5 V37P.pdf" | MOSIS lot report (AMI 0.5) | Electrical only; TOX 141 A matches N8BN report TOX 141 A |
| EE Times (1992): "AMI's 0.8 and 1.2 processes chosen by MOSIS" | Contemporary news | Process identity only: CWL = 0.8 um single-poly double-metal + poly-cap; ABN = 1.2 um double-poly double-metal. No thickness. |
| MOSIS SCMOS 7.2 + UConn C5N deck | Lambda rules | No thickness anywhere (incl. antenna section: rules reference per-fabricator numbers only) |
| MOSIS CMP and Antenna Rules page (mosis.com, archived) | Generic guidance | No per-process thickness tables |
| Auburn "SBook" SPICE text + VT thesis Chap.6 + Berkeley ERL-95-38 | Textbooks/theses using HP 0.5 um BSIM3 | None; confirm HP 0.5 um was MOSIS-available, no stack |
| Web synthesis of HP 0.5 um (CMOSP14/AMOS14TB) | Aggregated ranges from course material | M1 0.6-0.7 um, M2 0.6-0.8 um, M3 (top) 1.0-1.2 um, IMD 0.8-1.2 um, poly 0.25-0.4 um, FOX 0.4-0.6 um — consistent with N8AG sheet pattern (M1-2 0.07, M3 0.05 ohm/sq = thicker top tier) |
| Web synthesis of HP 0.35 um (GMOS10QA) | Aggregated ranges | M1 0.4-0.6 um, ILD 0.8-1.2 um — consistent with N88W sheet pattern (M1-3 0.06, M4 0.03 = thick top tier) |

## Per-process status

| Process / run | Found first-hand | Derived-stack anchors |
| --- | --- | --- |
| AMI05 C5N (N8BN) | poly 0.4 um (NIST); TOX 141 A (report); glass 3.2 um (NIST) | M1-M3 0.6-0.7/0.6-0.8/1.0-1.2 um era; IMD 0.8-1.2 um; FOX 0.5-0.6 um; substrate p-sub 10-20 ohm-cm era |
| AMI10 CWL (N87R) | none | 1.0 um-era: poly 0.4 um, M1 0.6-1.0 um, M2 0.8-1.0 um, IMD 0.8-1.2 um, FOX 0.6-0.7 um |
| AMI12 ABN (N88Z) | none | 1.2 um-era: poly 0.35-0.4 um (double-poly), M1 0.6-1.0 um, M2 0.8-1.0 um, IMD 0.8-1.2 um, FOX 0.6-0.7 um |
| HP05 AMOS14TB (N8AG) | none | M1 0.6-0.7, M2 0.6-0.8, M3 1.0-1.2 um; IMD 0.8-1.2 um; poly 0.25-0.4 um; FOX 0.4-0.6 um |
| HP035 GMOS10QA (N88W) | none | M1 0.4-0.6 um; ILD 0.8-1.2 um; 4M stack with M4 top tier 0.9-1.2 um |

## Sanity constraints available

For every run, the measured C table constrains the derived stack:
M1 area-C-to-substrate / implied ILD height must give effective epsilon_r in
3.5-4.2; M3/M4 top-tier thickness must be consistent with the measured sheet
resistance and aluminum resistivity (2.7-3.0 uohm-cm). These two checks turn
every derived stack into a bounded hypothesis instead of an arbitrary guess.
