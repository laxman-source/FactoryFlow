"""ECN records and revision selection for the fictional FactoryFlow simulator.

This module records planning decisions. It never posts inventory transactions or
changes the legacy BOM in factoryflow.data.
"""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime


DISPOSITIONS = frozenset({"use-up", "hold", "return", "scrap"})


def _day(value, label):
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{label} must be a calendar date")


def _quantity(value, label, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, int) or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{label} must be a {qualifier} whole number")


def _code(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonblank string")


@dataclass(frozen=True)
class BOMRevision:
    finished_sku: str
    revision: str
    components: tuple[tuple[str, int], ...]

    def __post_init__(self):
        _code(self.finished_sku, "Finished SKU")
        _code(self.revision, "BOM revision")
        if not isinstance(self.components, (tuple, list)) or not self.components:
            raise ValueError("BOM revision must have component lines")
        lines = tuple(self.components)
        seen = set()
        for line in lines:
            if not isinstance(line, (tuple, list)) or len(line) != 2:
                raise ValueError("BOM lines must contain component SKU and quantity")
            component, per_unit = line
            _code(component, "Component SKU")
            _quantity(per_unit, "BOM quantity", positive=True)
            if component in seen:
                raise ValueError(f"Duplicate BOM component: {component}")
            seen.add(component)
        object.__setattr__(self, "components", tuple((sku, qty) for sku, qty in lines))

    @property
    def usage(self):
        return dict(self.components)


@dataclass(frozen=True)
class ECNChangeLine:
    old_component_sku: str
    new_component_sku: str
    old_qty_per_unit: int
    new_qty_per_unit: int

    def __post_init__(self):
        _code(self.old_component_sku, "Old component")
        _code(self.new_component_sku, "New component")
        _quantity(self.old_qty_per_unit, "Old BOM quantity", positive=True)
        _quantity(self.new_qty_per_unit, "New BOM quantity", positive=True)


@dataclass(frozen=True)
class ECN:
    reference: str
    finished_sku: str
    from_revision: str
    to_revision: str
    proposed_effective_date: date
    changes: tuple[ECNChangeLine, ...]
    disposition: str | None = None
    status: str = "draft"
    approval_date: date | None = None
    effective_date: date | None = None
    approved_by: str | None = None
    cancellation_date: date | None = None
    cancellation_reason: str | None = None

    def __post_init__(self):
        for value, label in ((self.reference, "ECN reference"),
                             (self.finished_sku, "Finished SKU"),
                             (self.from_revision, "From revision"),
                             (self.to_revision, "To revision")):
            _code(value, label)
        if self.from_revision == self.to_revision:
            raise ValueError("ECN must change the BOM revision")
        _day(self.proposed_effective_date, "Proposed effective date")
        if not isinstance(self.changes, (tuple, list)) or not self.changes:
            raise ValueError("ECN must list its component changes")
        if not all(isinstance(line, ECNChangeLine) for line in self.changes):
            raise ValueError("ECN changes must be ECNChangeLine records")
        object.__setattr__(self, "changes", tuple(self.changes))
        if self.disposition is not None and self.disposition not in DISPOSITIONS:
            raise ValueError("Old-stock disposition must be use-up, hold, return, or scrap")
        if self.status not in {"draft", "approved", "cancelled"}:
            raise ValueError("ECN status must be draft, approved, or cancelled")
        if self.status == "approved":
            if self.approval_date is None or self.effective_date is None:
                raise ValueError("Approved ECN needs approval and effective dates")
            _day(self.approval_date, "Approval date")
            _day(self.effective_date, "Effective date")
            if self.approval_date >= self.effective_date:
                raise ValueError("Effective date must be later than approval date")
            _code(self.approved_by, "Approver")
            if self.disposition is None:
                raise ValueError("Approved ECN needs an old-stock disposition plan")
            if self.cancellation_date is not None or self.cancellation_reason is not None:
                raise ValueError("Approved ECN cannot have cancellation fields")
        elif self.status == "draft":
            if any(value is not None for value in (self.approval_date, self.effective_date,
                                                    self.approved_by, self.cancellation_date,
                                                    self.cancellation_reason)):
                raise ValueError("Draft ECN cannot contain approval or cancellation fields")
        else:
            _day(self.cancellation_date, "Cancellation date")
            _code(self.cancellation_reason, "Cancellation reason")
            if self.effective_date is not None:
                _day(self.effective_date, "Effective date")
                _day(self.approval_date, "Approval date")
                _code(self.approved_by, "Approver")
                if self.approval_date >= self.effective_date:
                    raise ValueError("Effective date must be later than approval date")
                if self.cancellation_date < self.approval_date:
                    raise ValueError("Cancellation cannot precede approval")
                if self.cancellation_date >= self.effective_date:
                    raise ValueError("Effective ECN cannot be cancelled retroactively")
            elif self.approval_date is not None or self.approved_by is not None:
                raise ValueError("Cancelled draft cannot contain approval fields")


@dataclass(frozen=True)
class StockHold:
    component_sku: str
    qty: int
    effective_date: date
    authorized_by: str
    authorized_date: date

    def __post_init__(self):
        _code(self.component_sku, "Held component")
        _quantity(self.qty, "Held quantity", positive=True)
        _day(self.effective_date, "Hold effective date")
        _code(self.authorized_by, "Hold approver")
        _day(self.authorized_date, "Hold authorization date")
        if self.authorized_date > self.effective_date:
            raise ValueError("Hold authorization cannot follow its effective date")


@dataclass(frozen=True)
class ProductionLot:
    order_id: str
    finished_sku: str
    qty: int
    created_date: date
    state: str = "new"
    pinned_revision: str | None = None

    def __post_init__(self):
        _code(self.order_id, "Order ID")
        _code(self.finished_sku, "Finished SKU")
        _quantity(self.qty, "Lot quantity")
        _day(self.created_date, "Order creation date")
        if self.state not in {"new", "released", "wip"}:
            raise ValueError("Lot state must be new, released, or wip")
        if self.state == "new" and self.pinned_revision is not None:
            raise ValueError("New lot cannot pin a BOM revision")
        if self.state != "new":
            _code(self.pinned_revision, "Pinned BOM revision")


def build_revisions(base_bom, proposed_revisions=()):
    """Preserve the current unversioned BOM as Revision A for each product."""
    if not isinstance(base_bom, (list, tuple)):
        raise ValueError("Base BOM must be a list or tuple")
    if not isinstance(proposed_revisions, (list, tuple)):
        raise ValueError("Proposed revisions must be a list or tuple")
    grouped = defaultdict(lambda: defaultdict(int))
    for line in base_bom:
        if not isinstance(line, Mapping):
            raise ValueError("Base BOM lines must be mappings")
        product, component, qty = (line.get("finished_sku"),
                                   line.get("component_sku"), line.get("qty_per_unit"))
        _code(product, "Finished SKU")
        _code(component, "Component SKU")
        _quantity(qty, "BOM quantity", positive=True)
        grouped[product][component] += qty
    revisions = {
        (product, "A"): BOMRevision(product, "A", tuple(usage.items()))
        for product, usage in grouped.items()
    }
    for revision in proposed_revisions:
        if not isinstance(revision, BOMRevision):
            raise ValueError("Proposed revisions must be BOMRevision records")
        key = revision.finished_sku, revision.revision
        if key in revisions:
            raise ValueError(f"Duplicate BOM revision: {key}")
        revisions[key] = revision
    return revisions


def _inventory_master(inventory):
    if not isinstance(inventory, (list, tuple)):
        raise ValueError("Inventory must be a list or tuple")
    masters = {}
    for item in inventory:
        if not isinstance(item, Mapping):
            raise ValueError("Inventory records must be mappings")
        sku = item.get("sku")
        _code(sku, "Inventory SKU")
        _code(item.get("name"), f"Name for {sku}")
        if sku in masters:
            raise ValueError(f"Duplicate inventory SKU: {sku}")
        for field in ("on_hand", "reserved", "safety_stock", "lead_days"):
            _quantity(item.get(field), f"{field} for {sku}")
        _quantity(item.get("pack_size"), f"pack_size for {sku}", positive=True)
        if item["reserved"] > item["on_hand"]:
            raise ValueError(f"Reserved stock exceeds on-hand for {sku}")
        masters[sku] = item
    return masters


def _validate_change(ecn, revisions, masters):
    before = revisions.get((ecn.finished_sku, ecn.from_revision))
    after = revisions.get((ecn.finished_sku, ecn.to_revision))
    if before is None or after is None:
        raise ValueError(f"Missing BOM revision for {ecn.reference}")
    expected = before.usage
    changed_old = set()
    for line in ecn.changes:
        old, new = line.old_component_sku, line.new_component_sku
        if old in changed_old or expected.get(old) != line.old_qty_per_unit:
            raise ValueError(f"ECN change does not match old BOM: {old}")
        changed_old.add(old)
        if new != old and new in expected:
            raise ValueError(f"ECN replacement already exists in BOM: {new}")
        del expected[old]
        expected[new] = line.new_qty_per_unit
    if expected != after.usage:
        raise ValueError(f"ECN changes do not match complete Revision {ecn.to_revision} BOM")
    missing = (set(before.usage) | set(after.usage)) - set(masters)
    if missing:
        raise ValueError(f"Missing inventory master for BOM components: {', '.join(sorted(missing))}")


def validate_ecn_calendar(ecns, revisions, inventory):
    """Reject duplicate references, incomplete approvals, gaps, and overlaps."""
    masters = _inventory_master(inventory)
    references = set()
    by_product = defaultdict(list)
    for ecn in ecns:
        if not isinstance(ecn, ECN):
            raise ValueError("ECNs must be ECN records")
        if ecn.reference in references:
            raise ValueError(f"Duplicate ECN reference: {ecn.reference}")
        references.add(ecn.reference)
        if ecn.status == "approved":
            _validate_change(ecn, revisions, masters)
            by_product[ecn.finished_sku].append(ecn)
    for product, changes in by_product.items():
        active = "A"
        prior_day = None
        for ecn in sorted(changes, key=lambda item: item.effective_date):
            if prior_day == ecn.effective_date:
                raise ValueError(f"Conflicting approved ECNs for {product} on {prior_day}")
            if ecn.from_revision != active:
                raise ValueError(f"Overlapping or disconnected BOM revision for {product}")
            active = ecn.to_revision
            prior_day = ecn.effective_date
    return masters


def approve_ecn(ecn, *, approval_date, effective_date, approved_by,
                base_bom, proposed_revisions, inventory, existing_ecns=()):
    """Return a new approved record; the original draft remains unchanged."""
    if not isinstance(ecn, ECN) or ecn.status != "draft":
        raise ValueError("Only a draft ECN can be approved")
    _day(approval_date, "Approval date")
    _day(effective_date, "Effective date")
    if approval_date >= effective_date:
        raise ValueError("Effective date must be later than approval date")
    _code(approved_by, "Approver")
    approved = replace(ecn, status="approved", approval_date=approval_date,
                       effective_date=effective_date, approved_by=approved_by)
    revisions = build_revisions(base_bom, proposed_revisions)
    validate_ecn_calendar((*existing_ecns, approved), revisions, inventory)
    return approved


def cancel_ecn(ecn, *, cancellation_date, reason):
    """Cancel a draft or a not-yet-effective approval, preserving its history."""
    if not isinstance(ecn, ECN) or ecn.status == "cancelled":
        raise ValueError("Cancelled ECN cannot transition again")
    _day(cancellation_date, "Cancellation date")
    _code(reason, "Cancellation reason")
    if ecn.status == "approved":
        if cancellation_date < ecn.approval_date:
            raise ValueError("Cancellation cannot precede approval")
        if cancellation_date >= ecn.effective_date:
            raise ValueError("Effective ECN cannot be cancelled retroactively")
    return replace(ecn, status="cancelled", cancellation_date=cancellation_date,
                   cancellation_reason=reason)


def resolve_revision(finished_sku, production_date, ecns):
    """Return active revision and ECN reference for one production day."""
    _day(production_date, "Production date")
    active, reference = "A", None
    for ecn in sorted((item for item in ecns if item.status == "approved"
                       and item.finished_sku == finished_sku),
                      key=lambda item: item.effective_date):
        if ecn.effective_date <= production_date:
            active, reference = ecn.to_revision, ecn.reference
    return active, reference
