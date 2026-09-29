#!/usr/bin/env python3
"""Shared Diva-compatible derived-layer computation (port of divaLayerDef.il).

Used by both the reference DRC deck (common/drc/scmos_reference.py) and the
reference LVS extractor (common/lvs/scmos_reference_lvs.py) so both tools see
identical geometry semantics.

derive(L, F, WELL, TECH, LAMBDA, DBU, UNIVERSE) -> dict[str, pya.Region]

  L(name)    -> Region for an input layer (from the profile layer map)
  F(flag)    -> bool feature flag (from the profile layers.yaml `features`)
  WELL       -> "N" | "P" | "E"  (well type, from mosis code)
  TECH       -> technology id, e.g. "AMI_C5N"
  LAMBDA     -> process lambda in um (informational)
  DBU        -> database unit in um
  UNIVERSE   -> Region covering the whole cell (Diva geomNot complement)
"""

import pya

DBU = 0.001  # set by derive(); used by butting()


# ---------------------------------------------------------------- Diva geom helpers

def inside(a, b):
    """Diva geomInside(a, b): parts of a inside b."""
    return a.inside(b)


def outside(a, b):
    """Diva geomOutside(a, b): a not overlapping b."""
    return a.not_interacting(b)


def avoiding(a, b):
    """Diva geomAvoiding(a, b): a not touching/overlapping b."""
    return a.not_interacting(b)


def overlap(a, b):
    """Diva geomOverlap(a, b): a overlapping b."""
    return a.interacting(b)


def straddle(a, b):
    """Diva geomStraddle(a, b) ~: a parts overlapping b but sticking out of b."""
    return a.interacting(b) - a.inside(b)


def butting(a, b, keep=1):
    """Diva geomButting(a, b, keep==N) ~: region-level approximation.
    keep==2 -> a regions within 1 nm of b (shared/touching edges);
    keep==1/ignore -> a interacting with b.  Used for markers and
    resistor-body recognition; transistor channel butting (LVS) is a
    different port and stays edge-based."""
    eps = max(1, int(round(0.001 / DBU)))  # 1 nm in database units
    if keep == 2:
        return a.interacting(b.sized(eps))
    return a.interacting(b)


def holes(r):
    return r.holes()


def sized(r, d):
    return r.sized(d)


def or_(*rs):
    out = pya.Region()
    for r in rs:
        out += r
    return out


def and_(*rs):
    out = rs[0]
    for r in rs[1:]:
        out = out & r
    return out


def andnot(a, b):
    return a - b


# ------------------------------------------------------------------ derivation

def derive(L, F, WELL, TECH, LAMBDA, DBU_, UNIVERSE):
    """Compute all Diva derived layers (divaLayerDef.il port)."""
    global DBU
    DBU = DBU_

    gwell = andnot(L("gwell"), L("nodrc"))
    nwell = andnot(L("nwell"), L("nodrc"))
    pwell = andnot(L("pwell"), L("nodrc"))
    deep_nwell = andnot(L("deep_nwell"), L("nodrc"))
    deep_pwell = andnot(L("deep_pwell"), L("nodrc"))
    hv_nwell = andnot(L("hv_nwell"), L("nodrc"))
    hv_pwell = andnot(L("hv_pwell"), L("nodrc"))
    hv_n_marker = andnot(
        or_(L("hv_n_marker"), L("cvn")), L("nodrc")
    )
    hv_p_marker = andnot(
        or_(L("hv_p_marker"), L("cvp")), L("nodrc")
    )
    hv_marker = andnot(L("hv_marker"), L("nodrc"))
    drift_n = andnot(L("drift_n"), L("nodrc"))
    drift_p = andnot(L("drift_p"), L("nodrc"))
    tactive = pya.Region()
    if F("hvAvailable"):
        tactive = andnot(L("tactive"), L("nodrc"))
        hv_n_marker = or_(hv_n_marker, and_(tactive, L("nactive")))
        hv_p_marker = or_(hv_p_marker, and_(tactive, L("pactive")))
    hv_n_marker = andnot(hv_n_marker, L("nodrc"))
    hv_p_marker = andnot(hv_p_marker, L("nodrc"))
    hvNMarker = hv_n_marker
    hvPMarker = hv_p_marker
    hvMarker = or_(hv_marker, hvNMarker, hvPMarker)
    isoPwell = and_(pwell, deep_nwell)
    isoNwell = and_(nwell, deep_pwell)
    active = or_(andnot(L("active"), L("nodrc")), L("nactive"), L("pactive"))
    gselect = andnot(L("gselect"), L("nodrc"))
    nselect = andnot(L("nselect"), L("nodrc"))
    pselect = andnot(L("pselect"), L("nodrc"))
    if F("pselectFromActive"):
        # Processes without an explicit p+ mask (e.g. CNM25: P+ regions are
        # GASAD not covered by NPLUS) derive P-select from active minus
        # N-select.  Opt-in only; raw pselect still wins when both exist.
        pselect = or_(pselect, andnot(active, nselect))
    poly = andnot(L("poly"), L("nodrc"))
    metal1 = andnot(L("metal1"), L("nodrc"))
    cc = andnot(L("cc"), L("nodrc"))
    metal2 = andnot(L("metal2"), L("nodrc"))
    via = andnot(L("via"), L("nodrc"))
    glass = andnot(L("glass"), L("nodrc"))
    pad = andnot(L("pad"), L("nodrc"))
    nolpe = L("nolpe")

    if F("metal3Available"):
        metal3 = andnot(L("metal3"), L("nodrc"))
        via2 = andnot(L("via2"), L("nodrc"))
    if F("metal4Available"):
        metal4 = andnot(L("metal4"), L("nodrc"))
        via3 = andnot(L("via3"), L("nodrc"))
    if F("metal5Available"):
        metal5 = andnot(L("metal5"), L("nodrc"))
        via4 = andnot(L("via4"), L("nodrc"))
    if F("metal6Available"):
        metal6 = andnot(L("metal6"), L("nodrc"))
        via5 = andnot(L("via5"), L("nodrc"))
    if F("metalcapAvailable"):
        metalcap = andnot(L("metalcap"), L("nodrc"))
    if F("ccdAvailable"):
        ccd = andnot(L("ccd"), L("nodrc"))
    if F("cwellAvailable"):
        cwell = andnot(L("cwell"), L("nodrc"))
    if F("polycapAvailable"):
        polycap = andnot(L("polycap"), L("nodrc"))
        # Diva computes cpolycap before cp/ca/ce classification; cp is unbound
        # (nil = empty) there, so cpolycap = polycap & cc.
        cpolycap = and_(polycap, cc)
    if F("sblockAvailable"):
        sblock = andnot(L("sblock"), L("nodrc"))
    if F("highresAvailable"):
        highres = andnot(L("highres"), L("nodrc"))
    if F("memsAvailable"):
        pstop = andnot(L("pstop"), L("nodrc"))
        open_ = andnot(L("open"), L("nodrc"))

    # contact classification (elec -> poly -> active order matters)
    if F("elecAvailable"):
        elec = andnot(L("elec"), L("nodrc"))
        ce = or_(andnot(L("ce"), L("nodrc")), and_(cc, elec))
        cp = or_(andnot(L("cp"), L("nodrc")), and_(cc, andnot(poly, ce)))
        ca = or_(andnot(L("ca"), L("nodrc")), and_(cc, andnot(active, or_(ce, cp))))
    else:
        cp = or_(andnot(L("cp"), L("nodrc")), and_(cc, poly))
        ca = or_(andnot(L("ca"), L("nodrc")), and_(cc, andnot(active, cp)))
    if F("npnAvailable"):
        pbase = andnot(L("pbase"), L("nodrc"))
        cactive = andnot(L("cactive"), L("nodrc"))
        ca = or_(ca, and_(cc, cactive))

    nActive = and_(active, nselect)
    pActive = and_(active, pselect)
    if F("ccdAvailable"):
        nActive = andnot(nActive, ccd)
        pActive = andnot(pActive, ccd)
    if F("cwellAvailable"):
        nActive = andnot(nActive, cwell)
        pActive = andnot(pActive, cwell)
    if F("hvAvailable"):
        tactive = andnot(L("tactive"), L("nodrc"))
        hvNMarker = or_(hvNMarker, and_(tactive, nActive))
        hvPMarker = or_(hvPMarker, and_(tactive, pActive))
        hvMarker = or_(hvMarker, tactive)

    # bulk/ohmic per well type (N default per MOSIS)
    if WELL == "P":
        nBulk = or_(andnot(UNIVERSE, pwell), andnot(nwell, pwell))
        pBulk = pwell
        nOhmic = andnot(nActive, pwell)
        pOhmic = and_(pActive, pwell)
        nNotOhmic = and_(nActive, pwell)
        pNotOhmic = andnot(pActive, pwell)
    elif WELL == "E":
        nBulk = nwell
        pBulk = pwell
        nOhmic = and_(nActive, nwell)
        pOhmic = and_(pActive, pwell)
        nNotOhmic = and_(nActive, pwell)
        pNotOhmic = and_(pActive, nwell)
    else:
        if F("npnAvailable"):
            nBulk = outside(nwell, cactive)
        else:
            nBulk = nwell
        pBulk = or_(andnot(UNIVERSE, nwell), andnot(pwell, nwell))
        nOhmic = and_(nActive, nwell)
        pOhmic = andnot(pActive, nwell)
        nNotOhmic = andnot(nActive, nwell)
        pNotOhmic = and_(pActive, nwell)
    # HVCMOS bulk domains are explicit derived regions.  They remain part of
    # the conventional bulk union for legacy 4T extraction, while
    # ``isoPwell``/``isoNwell`` preserve the isolated-domain lookup.
    nBulk = or_(nBulk, deep_nwell, hv_nwell)
    pBulk = or_(pBulk, deep_pwell, hv_pwell)

    if F("elecAvailable"):
        nDiff = andnot(nNotOhmic, or_(poly, elec))
        pDiff = andnot(pNotOhmic, or_(poly, elec))
        nChannel = outside(and_(nNotOhmic, poly), elec)
        pChannel = outside(and_(pNotOhmic, poly), elec)
        nElecChannel = outside(and_(nNotOhmic, elec), poly)
        pElecChannel = outside(and_(pNotOhmic, elec), poly)
        nElecChannelTran = butting(nElecChannel, nDiff, 2)
        pElecChannelTran = butting(pElecChannel, pDiff, 2)
        nElecChannelCap = butting(nElecChannel, nDiff, 1)
        pElecChannelCap = butting(pElecChannel, pDiff, 1)
        Space = andnot(UNIVERSE, or_(active, poly, elec))
    else:
        nDiff = andnot(nNotOhmic, poly)
        pDiff = andnot(pNotOhmic, poly)
        nChannel = and_(nNotOhmic, poly)
        pChannel = and_(pNotOhmic, poly)
        Space = andnot(UNIVERSE, or_(active, poly))

    nChannelTran = butting(nChannel, nDiff, 2)
    pChannelTran = butting(pChannel, pDiff, 2)
    nChannelTranBase = nChannelTran
    pChannelTranBase = pChannelTran
    nChannelCap = butting(nChannel, nDiff, 1)
    pChannelCap = butting(pChannel, pDiff, 1)
    hvnChannelTran = pya.Region()
    hvpChannelTran = pya.Region()
    nHVDiff = pya.Region()
    pHVDiff = pya.Region()
    if F("hvAvailable") or F("hvcmosAvailable"):
        hvnChannelTran = and_(nChannelTranBase, hvNMarker)
        nChannelTran = andnot(nChannelTran, hvnChannelTran)
        hvpChannelTran = and_(pChannelTranBase, hvPMarker)
        pChannelTran = andnot(pChannelTran, hvpChannelTran)
        nHVDiff = and_(nDiff, hvNMarker)
        pHVDiff = and_(pDiff, hvPMarker)
    nDrift = and_(nDiff, drift_n)
    pDrift = and_(pDiff, drift_p)
    nDmosChannel = and_(nChannelTranBase, and_(hvNMarker, drift_n))
    pDmosChannel = and_(pChannelTranBase, and_(hvPMarker, drift_p))
    nDmosDiff = nDrift
    pDmosDiff = pDrift

    nDiffContact = and_(ca, nDiff)
    pDiffContact = and_(ca, pDiff)
    nOhmicContact = and_(ca, nOhmic)
    pOhmicContact = and_(ca, pOhmic)
    Gate = and_(or_(nNotOhmic, pNotOhmic), poly)
    fieldPoly = avoiding(poly, Gate)

    m1pCap = and_(and_(poly, metal1), L("cap_id"))
    m1sCap = and_(andnot(metal1, poly), L("cap_id"))
    m2m1Cap = and_(and_(metal1, metal2), L("cap_id"))
    if F("metal3Available"):
        m3m2Cap = and_(and_(metal2, metal3), L("cap_id"))
    if F("metal4Available"):
        m4m3Cap = and_(and_(metal3, metal4), L("cap_id"))
    if F("metal5Available"):
        m5m4Cap = and_(and_(metal4, metal5), L("cap_id"))
    if F("metal6Available"):
        m6m5Cap = and_(and_(metal5, metal6), L("cap_id"))
    if F("metalcapAvailable"):
        if F("metal6Available"):
            metalcapBottom = straddle(metal5, metalcap)
            metalcapCap = and_(metalcap, metal5)
            via5metalcap = and_(via5, metalcapBottom)
            via5 = andnot(via5, via5metalcap)
        elif F("metal5Available"):
            metalcapBottom = straddle(metal4, metalcap)
            metalcapCap = and_(metalcap, metal4)
            via4metalcap = and_(via4, metalcapBottom)
            via4 = andnot(via4, via4metalcap)

    NPdiode = and_(L("dio_id"), outside(nNotOhmic, poly))
    PNdiode = and_(L("dio_id"), outside(pNotOhmic, poly))
    if not (WELL == "P" or WELL == "E"):
        NwPdiode = and_(L("dio_id"), outside(nwell, pNotOhmic))

    if F("elecAvailable"):
        elecGate = and_(or_(nNotOhmic, pNotOhmic), elec)
        fieldElec = avoiding(elec, elecGate)
        CapacitorElec = inside(elec, poly)
        polyElecCap = and_(elec, poly)  # poly1-poly2 overlap (PiP), CNM25/AMS
        TransistorElec = overlap(elec, pya.Region() - poly)

    if F("polycapAvailable"):
        polycapCap = and_(poly, polycap)
    if F("sblockAvailable"):
        sGateWidthCheck = sized(sized(and_(Gate, sblock), -2.9), 2.9)
    if F("npnAvailable"):
        npnCollector = and_(nwell, and_(nselect, cactive))
        npnCollectorContact = and_(ca, npnCollector)
        npnBaseImplant = and_(nwell, pbase)
        npnEmitter = and_(nselect, npnBaseImplant)
        npnBase = andnot(npnBaseImplant, npnEmitter)
        npnBaseTap = and_(npnBase, pselect)
        npnBaseContact = and_(or_(cc, ca), npnBaseTap)
        npnEmitterContact = and_(or_(cc, ca), npnEmitter)
        npnTran = inside(nwell, or_(npnCollector, npnBase, npnEmitter))
    if F("ccdAvailable"):
        ccdDiff = and_(active, ccd)
        ccdContact = and_(ca, ccdDiff)
    if F("cwellAvailable"):
        lcDiff = straddle(cwell, active)
        lcContact = and_(ca, lcDiff)
        lcCap = and_(poly, and_(lcDiff, active))

    # resistors
    if F("sblockAvailable"):
        fieldPoly = andnot(fieldPoly, or_(sblock, L("res_id")))
        polySRes = butting(and_(sblock, poly), fieldPoly, 2)
        polyRes = butting(andnot(and_(L("res_id"), poly), polySRes), fieldPoly, 2)
        poly = andnot(poly, or_(sblock, L("res_id")))
    else:
        fieldPoly = andnot(fieldPoly, L("res_id"))
        polyRes = butting(and_(L("res_id"), poly), fieldPoly, 2)
        poly = andnot(poly, L("res_id"))

    if F("elecAvailable"):
        if F("highresAvailable"):
            fieldElec = andnot(fieldElec, or_(L("res_id"), highres))
            elecRes = butting(and_(L("res_id"), elec), fieldElec, 2)
            elecHighres = butting(and_(highres, elec), fieldElec, 2)
            elec = andnot(elec, or_(L("res_id"), highres))
        else:
            fieldElec = andnot(fieldElec, L("res_id"))
            elecRes = butting(and_(L("res_id"), elec), fieldElec, 2)
            elec = andnot(elec, L("res_id"))

    nBulk = andnot(nBulk, L("res_id"))
    nwellRes = butting(and_(L("res_id"), nwell), nBulk, 2)
    nwell = andnot(nwell, L("res_id"))

    return {k: v for k, v in locals().items() if isinstance(v, pya.Region)}
