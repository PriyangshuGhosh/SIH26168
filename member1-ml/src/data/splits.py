"""Group-level train/val/test splits and leave-one-vehicle-out (LOVO) folds.

Splits are assigned per ``trip_id`` (never per row or window) using regex rules from the
config. Default design:

    train: Vw family (Vw2 ... Vw17) + Vfa02
    val:   M
    test:  S series (S1, S2, S3a, S3b, S3c, S4)

Trips matching no rule (in the current NPZ: Vfa01, Vta1a, Vta1b, Y1) are left unassigned
and excluded from the fixed split.

The NPZ has no explicit vehicle identifier. LOVO therefore holds out a *group* at a
configurable level: ``"family"`` (alphabetic prefix of trip_id: M, S, Vfa, Vta, Vw, Y) or
``"trip"`` (the trip_id itself). ``"family"`` is the conservative proxy for a vehicle.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

SPLIT_NAMES: tuple[str, ...] = ("train", "val", "test")


def trip_family(trip_id: str) -> str:
    m = re.match(r"[A-Za-z]+", trip_id)
    if m is None:
        raise ValueError(f"Cannot derive family from trip_id {trip_id!r}")
    return m.group(0)


def group_of(trip_id: str, level: str) -> str:
    if level == "trip":
        return trip_id
    if level == "family":
        return trip_family(trip_id)
    raise ValueError(f"Unknown group level {level!r}")


def assign_trips(trip_ids: np.ndarray | list[str], rules: dict[str, list[str]]) -> dict[str, str | None]:
    """Map each unique trip to exactly one split name, or ``None`` if no rule matches."""
    assignment: dict[str, str | None] = {}
    for trip in sorted({str(t) for t in np.unique(np.asarray(trip_ids).astype(str))}):
        matched = [s for s in SPLIT_NAMES if any(re.fullmatch(p, trip) for p in rules.get(s, []))]
        if len(matched) > 1:
            raise ValueError(f"Trip {trip!r} matches multiple splits: {matched}")
        assignment[trip] = matched[0] if matched else None
    return assignment


@dataclass(frozen=True)
class GroupSplit:
    """Row masks and group membership for a fixed train/val/test split."""

    masks: dict[str, np.ndarray]        # split -> bool (N,)
    trips: dict[str, list[str]]         # split -> sorted trip_ids
    sessions: dict[str, list[str]]      # split -> sorted session_ids
    unassigned_trips: list[str]


def make_split(trip_id: np.ndarray, session_id: np.ndarray, rules: dict[str, list[str]]) -> GroupSplit:
    trip_id = np.asarray(trip_id).astype(str)
    session_id = np.asarray(session_id).astype(str)
    assignment = assign_trips(trip_id, rules)
    masks, trips, sessions = {}, {}, {}
    for split in SPLIT_NAMES:
        split_trips = sorted(str(t) for t, s in assignment.items() if s == split)
        mask = np.isin(trip_id, split_trips)
        masks[split] = mask
        trips[split] = split_trips
        sessions[split] = sorted({str(s) for s in np.unique(session_id[mask])})
    result = GroupSplit(masks, trips, sessions, sorted(t for t, s in assignment.items() if s is None))
    assert_no_group_leakage(result, trip_id, session_id)
    return result


def assert_no_group_leakage(split: GroupSplit, trip_id: np.ndarray, session_id: np.ndarray) -> None:
    """Fail if any row, session, trip or trip family is shared between two splits."""
    for i, a in enumerate(SPLIT_NAMES):
        for b in SPLIT_NAMES[i + 1:]:
            ma, mb = split.masks[a], split.masks[b]
            if np.any(ma & mb):
                raise AssertionError(f"rows shared between {a} and {b}")
            for name, col in (("session", session_id), ("trip", trip_id)):
                shared = set(col[ma]) & set(col[mb])
                if shared:
                    raise AssertionError(f"{name} leakage between {a} and {b}: {sorted(shared)}")
            fam = {trip_family(t) for t in split.trips[a]} & {trip_family(t) for t in split.trips[b]}
            if fam:
                raise AssertionError(f"trip-family leakage between {a} and {b}: {sorted(fam)}")


@dataclass(frozen=True)
class LovoFold:
    held_out: str
    train_mask: np.ndarray  # bool (N,)
    test_mask: np.ndarray   # bool (N,)


def lovo_folds(trip_id: np.ndarray, level: str = "family", include_trips: list[str] | None = None) -> Iterator[LovoFold]:
    """Yield one fold per group: train on all other included groups, test on the held-out one."""
    trip_id = np.asarray(trip_id).astype(str)
    included = np.ones(len(trip_id), dtype=bool) if include_trips is None else np.isin(trip_id, include_trips)
    uniq, inverse = np.unique(trip_id, return_inverse=True)
    groups = np.array([group_of(t, level) for t in uniq], dtype=str)[inverse]
    for g in sorted(set(groups[included])):
        test_mask = included & (groups == g)
        train_mask = included & (groups != g)
        if set(trip_id[train_mask]) & set(trip_id[test_mask]):
            raise AssertionError(f"LOVO fold {g!r}: trip shared between train and test")
        yield LovoFold(g, train_mask, test_mask)
