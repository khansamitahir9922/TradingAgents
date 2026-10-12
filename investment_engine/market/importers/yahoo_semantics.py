"""Field-specific Yahoo evidence and transformations (M1-12).

These decisions concern one instrument and one vendor-library version. An
unknown field is blocked, even after the last split. Continuity and summed
hourly volume are diagnostic evidence only; they never establish semantics.
"""

import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from numbers import Integral
from pathlib import Path
from statistics import median
from types import MappingProxyType
from zoneinfo import ZoneInfo

from investment_engine.market.corporate_actions import ActionType, CorporateAction
from investment_engine.money import PRICE_QUANTUM, SHARE_QUANTUM, from_float64, quantize

PROVENANCE_DOCUMENT = "docs/data-provenance/yfinance.md"


class FieldKey(StrEnum):
    SPLIT_RATIO = "SPLIT_RATIO"
    D1_PRICE = "D1_PRICE"
    D1_VOLUME = "D1_VOLUME"
    H1_PRICE = "H1_PRICE"
    H1_VOLUME = "H1_VOLUME"
    DIVIDEND_AMOUNT = "DIVIDEND_AMOUNT"


class Semantics(StrEnum):
    UNADJUSTED = "UNADJUSTED"
    SPLIT_ADJUSTED_AS_OF_DOWNLOAD = "SPLIT_ADJUSTED_AS_OF_DOWNLOAD"
    OTHER = "OTHER"
    UNDETERMINED = "UNDETERMINED"


class Transformation(StrEnum):
    IDENTITY = "IDENTITY"
    SPLIT_RECONSTRUCTION = "SPLIT_RECONSTRUCTION"
    IDENTITY_IF_NO_LATER_SPLIT = "IDENTITY_IF_NO_LATER_SPLIT"
    BLOCKED = "BLOCKED"


class FieldBlocked(ValueError):
    """The evidence does not permit this field to be stored."""


class VersionMismatch(ValueError):
    """The vendor version has not been verified."""


class OutsideVerifiedRange(ValueError):
    """A date precedes the independently verified range."""


class SplitHistoryMismatch(ValueError):
    """Reconstruction cannot use incomplete, changing or uncited history."""


@dataclass(frozen=True)
class FieldVerification:
    field: FieldKey
    semantics: Semantics
    transformation: Transformation
    evidence: tuple[str, ...]
    max_error: Decimal | None
    precision_note: str


@dataclass(frozen=True)
class VerificationRecord:
    verified_on: date
    yfinance_version: str
    instrument_id: str
    verified_from: date
    cited_splits: tuple[tuple[date, Decimal], ...]
    split_history_call: str
    fields: Mapping[FieldKey, FieldVerification]
    document: str

    def __post_init__(self):
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


def _field(key, semantics, transformation, evidence, error, note):
    return FieldVerification(key, semantics, transformation, tuple(evidence), error, note)


YAHOO_VERIFICATION = VerificationRecord(
    verified_on=date(2026, 10, 12), yfinance_version="1.7.0", instrument_id="EQ_US_NVDA",
    verified_from=date(2019, 1, 1),
    cited_splits=((date(2021, 7, 20), Decimal("4")), (date(2024, 6, 10), Decimal("10"))),
    split_history_call="Ticker(symbol).splits", document=PROVENANCE_DOCUMENT,
    fields={
        FieldKey.SPLIT_RATIO: _field(FieldKey.SPLIT_RATIO, Semantics.UNADJUSTED, Transformation.IDENTITY,
                                   ["NVDA-8K-2021-05-21", "NVDA-8K-2024-05-22"], Decimal("0"),
                                   "Cited dates and exact ratios; pre-2019 events are excluded."),
        FieldKey.D1_PRICE: _field(FieldKey.D1_PRICE, Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD,
                                Transformation.SPLIT_RECONSTRUCTION,
                                ["FOOL-2021-07-20", "MASSIVE-BLOG-2024-06-11", "test_daily_prices_are_split_adjusted_and_reconstruct_exactly"],
                                Decimal("0.0029"), "Stored 0.0001 is a quantum, not a claim of vendor accuracy."),
        FieldKey.D1_VOLUME: _field(FieldKey.D1_VOLUME, Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD,
                                 Transformation.SPLIT_RECONSTRUCTION, ["MASSIVE-BLOG-2024-06-11"],
                                 Decimal("0.0169"), "Maximum decisive relative error rounded to four decimals; 3% tolerance."),
        FieldKey.H1_PRICE: _field(FieldKey.H1_PRICE, Semantics.UNDETERMINED, Transformation.BLOCKED,
                                ["nvda_1h_730d.json", "test_hourly_prices_stay_undetermined_with_unexplained_differences"],
                                None, "169 sessions differ in vendor units; 181 under raw reconstruction. Unexplained."),
        FieldKey.H1_VOLUME: _field(FieldKey.H1_VOLUME, Semantics.UNDETERMINED, Transformation.BLOCKED,
                                 ["nvda_1h_730d.json", "test_hourly_volume_is_blocked_without_comparable_hourly_references"],
                                 None, "No comparable independent hourly anchors or explicit provider statement."),
        FieldKey.DIVIDEND_AMOUNT: _field(FieldKey.DIVIDEND_AMOUNT, Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD,
                                       Transformation.SPLIT_RECONSTRUCTION,
                                       ["NVDA-8K-2021-05-26", "NVDA-8K-2024-02-21", "NVDA-8K-2024-05-22"], Decimal("0"),
                                       "Declared per-share amounts match exactly after 0.0001 quantization."),
    },
)


def plain_date(value, name):
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{name} must be a date")
    return value


def decimal_value(value) -> Decimal:
    """The M1-02 boundary: float64 conversion, exact integers, no guessed strings."""
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("vendor values must be finite")
        # Preserve the delivered float's decimal representation until AFTER
        # reconstruction. Rounding a price or dividend to 0.0001 before
        # multiplying by 40 would invent an avoidable reconstruction error.
        exponent = Decimal(float.__repr__(value)).as_tuple().exponent
        result = from_float64(value, Decimal("1").scaleb(exponent))
    elif isinstance(value, Integral) and not isinstance(value, bool):
        result = Decimal(int(value))
    else:
        raise TypeError(f"unsupported vendor number {type(value).__name__}")
    if not result.is_finite():
        raise ValueError("vendor values must be finite")
    return result


def transformation_of(field, semantics, *, at_most_split_adjusted=False):
    field, semantics = FieldKey(field), Semantics(semantics)
    if semantics is Semantics.UNADJUSTED:
        return Transformation.IDENTITY
    if semantics is Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD:
        return Transformation.SPLIT_RECONSTRUCTION
    if semantics is Semantics.UNDETERMINED and at_most_split_adjusted and field in (FieldKey.D1_PRICE, FieldKey.H1_PRICE):
        return Transformation.IDENTITY_IF_NO_LATER_SPLIT
    return Transformation.BLOCKED


def transformation_for(field, yfinance_version, verification=YAHOO_VERIFICATION):
    if yfinance_version != verification.yfinance_version:
        raise VersionMismatch(f"yfinance {yfinance_version} differs from verified {verification.yfinance_version}")
    key = FieldKey(field)
    result = verification.fields[key].transformation
    if result is Transformation.BLOCKED:
        raise FieldBlocked(f"{key} is blocked; see {verification.document}")
    return result


def in_range_splits(splits, verification=YAHOO_VERIFICATION):
    result = []
    for d, ratio in splits:
        plain_date(d, "split ex-date")
        if d < verification.verified_from:
            continue
        ratio = decimal_value(ratio)
        if ratio <= 0 or ratio == 1:
            raise ValueError("split ratio must be positive and not 1")
        result.append((d, ratio))
    if len({d for d, _ in result}) != len(result):
        raise SplitHistoryMismatch("duplicate split ex-date")
    return tuple(sorted(result))


def check_cited_splits(splits, verification=YAHOO_VERIFICATION):
    actual = in_range_splits(splits, verification)
    expected = tuple(sorted(verification.cited_splits))
    a, e = dict(actual), dict(expected)
    if e.keys() - a.keys():
        raise SplitHistoryMismatch("missing cited split: full-history request required")
    if a.keys() - e.keys():
        raise SplitHistoryMismatch("extra uncited split; add its citation and obtain review before importing")
    if actual != expected:
        raise SplitHistoryMismatch("split ratio differs from citation")
    return actual


def check_same_split_history(before, after, verification=YAHOO_VERIFICATION):
    if in_range_splits(before, verification) != in_range_splits(after, verification):
        raise SplitHistoryMismatch("split history changed mid-run; nothing may be written")


def split_factor(splits: Sequence[CorporateAction], d: date, download_date: date,
                 verification=YAHOO_VERIFICATION) -> Decimal:
    plain_date(d, "d")
    plain_date(download_date, "download_date")
    if d < verification.verified_from:
        raise OutsideVerifiedRange(f"{d} is before {verification.verified_from}")
    factor = Decimal("1")
    seen = set()
    identity = None
    for action in splits:
        if action.action_type is not ActionType.SPLIT:
            raise ValueError("split_factor accepts SPLIT actions only")
        if action.ex_date < verification.verified_from:
            raise OutsideVerifiedRange("split precedes verified_from")
        current = (action.source, action.instrument_id)
        if identity is not None and current != identity:
            raise ValueError("split history must belong to one provider and instrument")
        identity = current
        if action.ex_date in seen:
            raise SplitHistoryMismatch("duplicate split ex-date")
        seen.add(action.ex_date)
        if d < action.ex_date <= download_date:
            factor *= action.ratio
    return factor


def factor_from_history(splits, d, download_date, verification):
    """`split_factor` for (ex_date, ratio) pairs, with the same verified-range rules.

    The record is required, so no importer can compute F without naming the
    range it was verified for.
    """
    plain_date(d, "d")
    plain_date(download_date, "download_date")
    if d < verification.verified_from:
        raise OutsideVerifiedRange(f"{d} is before {verification.verified_from}")
    factor = Decimal("1")
    seen = set()
    for ex_date, ratio in splits:
        plain_date(ex_date, "split ex-date")
        if ex_date < verification.verified_from:
            raise OutsideVerifiedRange(f"split on {ex_date} precedes {verification.verified_from}")
        if ex_date in seen:
            raise SplitHistoryMismatch("duplicate split ex-date")
        seen.add(ex_date)
        if d < ex_date <= download_date:
            factor *= ratio
    return factor


def reconstruct_price(value, factor):
    return quantize(decimal_value(value) * decimal_value(factor), PRICE_QUANTUM)


def reconstruct_volume(value, factor):
    factor = decimal_value(factor)
    if factor <= 0:
        raise ValueError("factor must be positive")
    return quantize(decimal_value(value) / factor, SHARE_QUANTUM)


@dataclass(frozen=True)
class Recording:
    metadata: dict
    columns: tuple[str, ...]
    rows: tuple[tuple, ...]

    def by_date(self):
        return [(datetime.fromisoformat(row[0]).date(), row[1:]) for row in self.rows]


def load_recording(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Recording(raw["metadata"], tuple(raw["columns"]), tuple(tuple(r) for r in raw["rows"]))


def recorded_series(recording, column):
    i = recording.columns.index(column) + 1
    return [(datetime.fromisoformat(row[0]).date(), decimal_value(row[i])) for row in recording.rows if row[i] != 0]


def series_values(series, timezone, *, verified_from=None):
    """Require aware vendor timestamps; normalize dates in the instrument's exchange."""
    result = []
    seen = set()
    for timestamp, value in series.items():
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("vendor timestamps must be timezone-aware")
        d = timestamp.astimezone(ZoneInfo(timezone)).date()
        if verified_from is not None and d < verified_from:
            result.append((d, value))  # never use or validate an excluded old event's ratio/amount
            continue
        value = decimal_value(value)
        if value == 0:
            continue
        if d in seen:
            raise ValueError("duplicate action date")
        seen.add(d)
        result.append((d, value))
    return result


@dataclass(frozen=True)
class PriceAnchor:
    date: date
    vendor: Decimal
    factor: Decimal
    cited: Decimal


@dataclass(frozen=True)
class VolumeAnchor:
    date: date
    vendor: Decimal
    factor: Decimal
    cited: Decimal


@dataclass(frozen=True)
class DividendAnchor:
    ex_date: date
    vendor: Decimal
    factor: Decimal
    declared: Decimal


@dataclass(frozen=True)
class Decision:
    semantics: Semantics
    max_error: Decimal | None = None
    errors: Mapping | None = None
    control_gaps: tuple[Decimal, ...] = ()
    supporting: tuple[Decimal, ...] = ()


def close_is_dividend_adjusted(close, adjusted_close):
    if not close or len(close) != len(adjusted_close):
        raise ValueError("matching nonempty close series required")
    return all(decimal_value(a) == decimal_value(b) for a, b in zip(close, adjusted_close, strict=True))


def decide_prices(anchors, *, dividend_adjusted):
    if dividend_adjusted:
        return Decision(Semantics.OTHER)
    errors = {
        Semantics.UNADJUSTED: tuple(abs(reconstruct_price(a.vendor, Decimal("1")) - a.cited) for a in anchors),
        Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD: tuple(abs(reconstruct_price(a.vendor, a.factor) - a.cited) for a in anchors),
    }
    matches = [s for s, e in errors.items() if e and all(x <= Decimal("0.01") for x in e)]
    if len(matches) != 1:
        return Decision(Semantics.UNDETERMINED, errors=errors)
    return Decision(matches[0], max(errors[matches[0]]), errors)


def decide_split_ratios(vendor, cited):
    return Semantics.UNADJUSTED if tuple(sorted(vendor)) == tuple(sorted(cited)) else Semantics.UNDETERMINED


def _relative(value, reference):
    if reference <= 0:
        raise ValueError("a volume reference must be positive")
    return abs(value - reference) / reference


def decide_daily_volume(anchors, controls, *, documented=None, continuity_ratio=None):
    supporting = () if continuity_ratio is None else (continuity_ratio,)
    if any(a.factor <= 1 for a in anchors):
        raise ValueError("decisive anchors require F > 1")
    if any(a.factor != 1 for a in controls):
        raise ValueError("control anchors require F == 1")
    errors = {
        Semantics.UNADJUSTED: tuple(_relative(a.vendor, a.cited) for a in anchors),
        Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD: tuple(_relative(a.vendor / a.factor, a.cited) for a in anchors),
    }
    gaps = tuple(_relative(a.vendor, a.cited) for a in controls)
    matches = []
    if not any(g > Decimal("0.03") for g in gaps):
        for candidate, e in errors.items():
            other = next(s for s in errors if s != candidate)
            if e and all(x <= Decimal("0.03") for x in e) and all(x >= Decimal("0.50") for x in errors[other]):
                matches.append(candidate)
    semantics = matches[0] if len(matches) == 1 else Semantics.UNDETERMINED
    if documented in (Semantics.UNADJUSTED, Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD) and not anchors:
        semantics = documented
    error = max(errors[semantics]) if semantics in errors and errors[semantics] else None
    return Decision(semantics, error, errors, gaps, supporting)


def decide_hourly_volume(anchors, *, controls=(), documented=None, hourly_sum_ratios=(), comparable=False):
    # Comparable means the cited references establish identical sessions,
    # bar boundaries and auction/late-trade coverage. Summed daily comparisons do not.
    decision = decide_daily_volume(anchors if comparable else [], controls if comparable else [], documented=documented)
    return Decision(decision.semantics, decision.max_error, decision.errors, decision.control_gaps,
                    tuple(hourly_sum_ratios))


def decide_dividends(anchors):
    errors = {
        Semantics.UNADJUSTED: tuple(abs(reconstruct_price(a.vendor, Decimal("1")) - a.declared) for a in anchors),
        Semantics.SPLIT_ADJUSTED_AS_OF_DOWNLOAD: tuple(abs(reconstruct_price(a.vendor, a.factor) - a.declared) for a in anchors),
    }
    matches = [s for s, e in errors.items() if e and all(x == 0 for x in e)]
    if len(matches) != 1:
        return Decision(Semantics.UNDETERMINED, errors=errors)
    return Decision(matches[0], Decimal("0"), errors)


def dollar_volume_continuity(before_prices, before_volumes, after_prices, after_volumes):
    before = median(p * v for p, v in zip(before_prices, before_volumes, strict=True))
    after = median(p * v for p, v in zip(after_prices, after_volumes, strict=True))
    return after / before


@dataclass(frozen=True)
class HourlyDifference:
    session: date
    extreme: str
    difference: Decimal
    hourly: Decimal
    daily: Decimal


def hourly_differences(hourly, daily, *, factor=None):
    grouped = defaultdict(list)
    for row in hourly.rows:
        stamp = datetime.fromisoformat(row[0]).astimezone(ZoneInfo("America/New_York"))
        grouped[stamp.date()].append(dict(zip(hourly.columns, row[1:], strict=True)))
    differences = []
    for d, values in daily.by_date():
        if d not in grouped:
            continue
        daily_row = dict(zip(daily.columns, values, strict=True))
        f = Decimal("1") if factor is None else factor(d)
        for extreme, column, operation in (("high", "High", max), ("low", "Low", min)):
            h = operation(decimal_value(r[column]) for r in grouped[d]) * f
            v = decimal_value(daily_row[column]) * f
            difference = abs(h - v)
            if difference > Decimal("0.01"):
                differences.append(HourlyDifference(d, extreme, difference, h, v))
    return differences


def decide_hourly_prices(differences, *, explained, split_method):
    if differences and not explained:
        return Semantics.UNDETERMINED
    return Semantics(split_method)
