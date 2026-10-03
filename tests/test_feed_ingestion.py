"""
Unit tests for the retailer feed ingestion pipeline.
======================================================

Covers:
  VolumeParser
    ✓ ml (no space)              "50ml"     → 50.00
    ✓ ml (with space)            "50 ml"    → 50.00
    ✓ mL (mixed case)            "250 mL"   → 250.00
    ✓ litre                      "1 L"      → 1000.00
    ✓ litre written out          "1 litre"  → 1000.00
    ✓ fluid oz                   "1.7 oz"   → ~50.27
    ✓ fl oz with dot             "1 fl. oz" → 29.57
    ✓ grams                      "100g"     → 100.00
    ✓ kilograms                  "0.5kg"    → 500.00
    ✓ European decimal separator "50,5ml"   → 50.50
    ✓ multipack                  "2 x 50ml" → 100.00
    ✓ multipack ×                "2×50ml"   → 100.00
    ✓ slash-separated            "30ml/1.7oz" → 30.00 (first match wins)
    ✓ invalid string             "large"    → None
    ✓ empty string               ""         → None
    ✓ case-insensitive units     "50ML"     → 50.00

  RawFeedItem schema
    ✓ currency is uppercased
    ✓ empty GTIN coerced to None
    ✓ whitespace-only GTIN coerced to None
    ✓ negative price rejected
    ✓ zero price rejected
    ✓ price coerced from string

  FeedIngestionService (async, mock DB session)
    ── Volume failure ──
    ✓ unparseable raw_size → IngestItemResult.success=False, no add() call

    ── Variant not found ──
    ✓ no GTIN / no variant → skipped=True, no add() call

    ── Append-only invariant (KEY TESTS) ──
    ✓ single ingest → exactly ONE session.add(Offer) call
    ✓ TWO ingests for same variant → TWO separate session.add() calls
    ✓ THREE price-change ingests → THREE separate session.add() calls
    ✓ offer fields (price, currency, in_stock) are set on the new Offer
    ✓ session.execute() never called with "UPDATE" during any ingest run
    ✓ session.execute(update(Offer)) was NEVER called (checked via call inspection)

    ── Price history ──
    ✓ each of N ingest runs records a distinct price value in a new row
    ✓ all N added objects are Offer instances (not session.merge / execute updates)

    ── Batch processing ──
    ✓ batch of 3 items: 2 resolved + 1 skipped → correct FeedIngestResult counts
    ✓ FeedIngestResult.total == inserted + skipped + failed
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.schemas.feed import FeedEnvelope, FeedIngestResult, IngestItemResult, RawFeedItem
from app.services.feed_ingestion import FeedIngestionService, VolumeParser

# ===========================================================================
# Fixtures
# ===========================================================================

RETAILER_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
VARIANT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
GTIN = "8901030910237"


@pytest.fixture()
def mock_variant() -> MagicMock:
    """Minimal mock Variant returned by the DB query."""
    from app.models.variant import Variant

    v = MagicMock(spec=Variant)
    v.id = VARIANT_ID
    v.size_ml = Decimal("30.0")
    v.gtin = GTIN
    return v


@pytest.fixture()
def mock_session(mock_variant: MagicMock) -> AsyncMock:
    """
    Mock AsyncSession where execute() resolves to our fake Variant.
    add() and flush() are no-ops that record calls.
    """
    session = AsyncMock()

    # execute() → result with scalar_one_or_none() → mock_variant
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_variant
    session.execute.return_value = mock_result

    return session


@pytest.fixture()
def mock_session_no_variant() -> AsyncMock:
    """Mock session where no Variant is found for any query."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result
    return session


def _make_item(
    *,
    gtin: str | None = GTIN,
    raw_size: str = "30ml",
    price: str = "599.00",
    currency: str = "INR",
    in_stock: bool = True,
    retailer_sku: str = "NYK-001",
) -> RawFeedItem:
    return RawFeedItem(
        retailer_sku=retailer_sku,
        gtin=gtin,
        title="Test Product 30ml",
        brand_name="Test Brand",
        raw_size=raw_size,
        price=Decimal(price),
        currency=currency,
        in_stock=in_stock,
        affiliate_url="https://example.com/affiliate/test",
    )


def _make_envelope(items: list[RawFeedItem]) -> FeedEnvelope:
    return FeedEnvelope(
        retailer_id=RETAILER_ID,
        retailer_slug="nykaa",
        items=items,
    )


# ===========================================================================
# VolumeParser tests
# ===========================================================================


class TestVolumeParser:
    """Pure unit tests — no DB, no async."""

    def test_ml_no_space(self) -> None:
        assert VolumeParser.parse("50ml") == Decimal("50.00")

    def test_ml_with_space(self) -> None:
        assert VolumeParser.parse("50 ml") == Decimal("50.00")

    def test_ml_mixed_case(self) -> None:
        assert VolumeParser.parse("250 mL") == Decimal("250.00")

    def test_ml_uppercase(self) -> None:
        assert VolumeParser.parse("50ML") == Decimal("50.00")

    def test_litre_capital(self) -> None:
        assert VolumeParser.parse("1 L") == Decimal("1000.00")

    def test_litre_lowercase(self) -> None:
        assert VolumeParser.parse("1 l") == Decimal("1000.00")

    def test_litre_written_out(self) -> None:
        assert VolumeParser.parse("1 litre") == Decimal("1000.00")

    def test_litre_written_out_plural(self) -> None:
        assert VolumeParser.parse("2 litres") == Decimal("2000.00")

    def test_oz_conversion(self) -> None:
        result = VolumeParser.parse("1.7 oz")
        assert result is not None
        # 1.7 × 29.5735 ≈ 50.27
        assert result == Decimal("50.27")

    def test_fl_oz_with_dot_and_space(self) -> None:
        result = VolumeParser.parse("1 fl. oz")
        assert result is not None
        assert result == Decimal("29.57")

    def test_fl_oz_no_space(self) -> None:
        result = VolumeParser.parse("1.7fl oz")
        assert result is not None
        assert result == Decimal("50.27")

    def test_grams_no_space(self) -> None:
        assert VolumeParser.parse("100g") == Decimal("100.00")

    def test_grams_with_space(self) -> None:
        assert VolumeParser.parse("100 g") == Decimal("100.00")

    def test_grams_written_out(self) -> None:
        assert VolumeParser.parse("100 grams") == Decimal("100.00")

    def test_kilograms(self) -> None:
        assert VolumeParser.parse("0.5kg") == Decimal("500.00")

    def test_decimal_value(self) -> None:
        assert VolumeParser.parse("30.5ml") == Decimal("30.50")

    def test_european_decimal_separator(self) -> None:
        """EU labels use comma as decimal separator: "50,5 ml" → 50.50 ml."""
        assert VolumeParser.parse("50,5 ml") == Decimal("50.50")

    def test_multipack_x(self) -> None:
        """2 x 50ml → 100 ml"""
        assert VolumeParser.parse("2 x 50ml") == Decimal("100.00")

    def test_multipack_X_uppercase(self) -> None:
        assert VolumeParser.parse("2X50ml") == Decimal("100.00")

    def test_multipack_unicode_times(self) -> None:
        assert VolumeParser.parse("2×50ml") == Decimal("100.00")

    def test_slash_returns_first_match(self) -> None:
        """'30ml / 1.7 oz' — first valid match (30ml) should be returned."""
        result = VolumeParser.parse("30ml / 1.7 oz")
        assert result == Decimal("30.00")

    def test_invalid_string_returns_none(self) -> None:
        assert VolumeParser.parse("large") is None

    def test_empty_string_returns_none(self) -> None:
        assert VolumeParser.parse("") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert VolumeParser.parse("   ") is None

    def test_number_without_unit_returns_none(self) -> None:
        assert VolumeParser.parse("50") is None

    def test_sephora_style_fl_oz(self) -> None:
        """'1 fl. oz' as it appears on Sephora US feed."""
        result = VolumeParser.parse("1 fl. oz")
        assert result == Decimal("29.57")


# ===========================================================================
# RawFeedItem schema tests
# ===========================================================================


class TestRawFeedItemSchema:
    def test_currency_uppercased(self) -> None:
        item = _make_item(currency="inr")
        assert item.currency == "INR"

    def test_currency_already_uppercase_unchanged(self) -> None:
        item = _make_item(currency="USD")
        assert item.currency == "USD"

    def test_empty_gtin_coerced_to_none(self) -> None:
        item = _make_item(gtin="")
        assert item.gtin is None

    def test_whitespace_gtin_coerced_to_none(self) -> None:
        item = _make_item(gtin="   ")
        assert item.gtin is None

    def test_none_gtin_stays_none(self) -> None:
        item = _make_item(gtin=None)
        assert item.gtin is None

    def test_price_string_coerced_to_decimal(self) -> None:
        item = RawFeedItem(
            retailer_sku="X",
            title="T",
            raw_size="30ml",
            price="599.00",  # string
            currency="INR",
            affiliate_url="https://example.com/a",
        )
        assert item.price == Decimal("599.00")

    def test_negative_price_rejected(self) -> None:
        with pytest.raises(Exception):
            _make_item(price="-1.00")

    def test_zero_price_rejected(self) -> None:
        with pytest.raises(Exception):
            _make_item(price="0.00")


# ===========================================================================
# FeedIngestionService — append-only invariant tests  (KEY TESTS)
# ===========================================================================


class TestFeedIngestionServiceAppendOnly:
    """
    Verifies the core APPEND-ONLY PRICE INVARIANT from gemini.md §1:

        "Never update or overwrite rows in the offer table.
         Every retailer scrape or feed import creates a new
         timestamped observation record."
    """

    async def test_single_ingest_creates_exactly_one_offer(
        self, mock_session: AsyncMock
    ) -> None:
        """One ingest → exactly one session.add(Offer) call."""
        from app.models.offer import Offer

        svc = FeedIngestionService(mock_session)
        result = await svc.ingest_feed(_make_envelope([_make_item()]))

        assert result.inserted == 1
        mock_session.add.assert_called_once()

        added = mock_session.add.call_args[0][0]
        assert isinstance(added, Offer), "Expected an Offer instance, not an update call"

    async def test_two_ingests_create_two_separate_offer_rows(
        self, mock_session: AsyncMock
    ) -> None:
        """
        Running the ingest twice for the exact same variant MUST produce
        two independent Offer rows — not an update to the first row.

        This is the core append-only invariant test.
        """
        from app.models.offer import Offer

        svc = FeedIngestionService(mock_session)
        envelope = _make_envelope([_make_item()])

        result1 = await svc.ingest_feed(envelope)
        result2 = await svc.ingest_feed(envelope)

        assert result1.inserted == 1
        assert result2.inserted == 1

        # Two session.add() calls — two separate Offer inserts
        assert mock_session.add.call_count == 2, (
            f"Expected 2 session.add() calls (two separate Offer rows), "
            f"got {mock_session.add.call_count}"
        )

        for i, call_args in enumerate(mock_session.add.call_args_list, start=1):
            obj = call_args[0][0]
            assert isinstance(obj, Offer), (
                f"Call #{i} to session.add() was not an Offer instance. "
                "An UPDATE path must have been taken — this violates the "
                "append-only invariant."
            )

    async def test_three_price_point_ingests_create_three_rows(
        self, mock_session: AsyncMock
    ) -> None:
        """
        Three consecutive price observations for the same variant
        must each produce a fresh Offer row — price history preserved.
        """
        from app.models.offer import Offer

        prices = ["599.00", "549.00", "579.00"]
        svc = FeedIngestionService(mock_session)

        for price in prices:
            await svc.ingest_feed(_make_envelope([_make_item(price=price)]))

        assert mock_session.add.call_count == 3
        assert all(
            isinstance(c[0][0], Offer) for c in mock_session.add.call_args_list
        )

    async def test_price_history_values_are_distinct_and_ordered(
        self, mock_session: AsyncMock
    ) -> None:
        """Each Offer row records the exact price from its ingest run."""
        prices = [Decimal("599.00"), Decimal("549.00"), Decimal("579.00")]
        svc = FeedIngestionService(mock_session)

        for price in prices:
            await svc.ingest_feed(_make_envelope([_make_item(price=str(price))]))

        added_offers = [c[0][0] for c in mock_session.add.call_args_list]
        recorded_prices = [o.price for o in added_offers]

        assert recorded_prices == prices, (
            "Price history was not faithfully recorded. "
            "Expected each ingest to produce a row with its own price."
        )

    async def test_no_update_statement_ever_issued_on_offer(
        self, mock_session: AsyncMock
    ) -> None:
        """
        Inspect every session.execute() call — none should contain 'UPDATE'.
        This catches any accidental bulk-update path.
        """
        svc = FeedIngestionService(mock_session)
        envelope = _make_envelope([_make_item()])

        await svc.ingest_feed(envelope)
        await svc.ingest_feed(envelope)

        for i, call_args in enumerate(mock_session.execute.call_args_list):
            stmt = call_args[0][0]
            stmt_str = str(stmt).upper()
            assert "UPDATE" not in stmt_str, (
                f"execute() call #{i + 1} contained 'UPDATE': {stmt_str!r}\n"
                "The offer table is append-only — UPDATE is forbidden."
            )


# ===========================================================================
# FeedIngestionService — per-item outcome tests
# ===========================================================================


class TestFeedIngestionServiceItemOutcomes:
    async def test_offer_contains_correct_fields(
        self, mock_session: AsyncMock
    ) -> None:
        """The inserted Offer must carry price, currency, in_stock, and variant_id."""
        from app.models.offer import Offer

        svc = FeedIngestionService(mock_session)
        await svc.ingest_feed(
            _make_envelope([_make_item(price="799.00", currency="INR", in_stock=False)])
        )

        offer: Offer = mock_session.add.call_args[0][0]
        assert offer.price == Decimal("799.00")
        assert offer.currency == "INR"
        assert offer.in_stock is False
        assert offer.variant_id == VARIANT_ID
        assert offer.retailer_id == RETAILER_ID

    async def test_unparseable_raw_size_fails_item(
        self, mock_session: AsyncMock
    ) -> None:
        """If raw_size cannot be parsed, item must be marked failed — not skipped."""
        svc = FeedIngestionService(mock_session)
        result = await svc.ingest_feed(
            _make_envelope([_make_item(raw_size="jumbo size")])
        )

        assert result.failed == 1
        assert result.inserted == 0
        assert result.skipped == 0
        mock_session.add.assert_not_called()

    async def test_no_variant_skips_item(
        self, mock_session_no_variant: AsyncMock
    ) -> None:
        """Feed item with no matching Variant should be skipped, not failed."""
        svc = FeedIngestionService(mock_session_no_variant)
        result = await svc.ingest_feed(
            _make_envelope([_make_item(gtin=None)])
        )

        assert result.skipped == 1
        assert result.inserted == 0
        assert result.failed == 0
        mock_session_no_variant.add.assert_not_called()

    async def test_item_result_contains_offer_id_on_success(
        self, mock_session: AsyncMock
    ) -> None:
        """A successful IngestItemResult must carry offer_id and variant_id."""
        svc = FeedIngestionService(mock_session)
        result = await svc.ingest_feed(_make_envelope([_make_item()]))

        assert result.inserted == 1
        item_result = result.item_results[0]
        assert item_result.success is True
        assert item_result.offer_id is not None
        assert item_result.variant_id == VARIANT_ID

    async def test_item_result_has_parsed_size_ml(
        self, mock_session: AsyncMock
    ) -> None:
        svc = FeedIngestionService(mock_session)
        result = await svc.ingest_feed(_make_envelope([_make_item(raw_size="30ml")]))
        assert result.item_results[0].size_ml == Decimal("30.00")


# ===========================================================================
# FeedIngestionService — batch processing tests
# ===========================================================================


class TestFeedIngestionServiceBatch:
    async def test_batch_two_resolved_one_skipped(
        self, mock_session: AsyncMock, mock_session_no_variant: AsyncMock
    ) -> None:
        """
        Batch of 3: items 1 and 2 match a variant, item 3 has no GTIN.
        Result: inserted=2, skipped=1, failed=0.

        We use a session that returns a variant for the first two calls
        and None for the third.
        """
        session = AsyncMock()
        mock_result_hit = MagicMock()
        from app.models.variant import Variant

        v = MagicMock(spec=Variant)
        v.id = VARIANT_ID
        v.gtin = GTIN
        mock_result_hit.scalar_one_or_none.return_value = v

        mock_result_miss = MagicMock()
        mock_result_miss.scalar_one_or_none.return_value = None

        # Two hits, one miss
        session.execute.side_effect = [
            mock_result_hit,
            mock_result_hit,
            mock_result_miss,
        ]

        items = [
            _make_item(retailer_sku="A", gtin=GTIN, raw_size="30ml", price="599.00"),
            _make_item(retailer_sku="B", gtin=GTIN, raw_size="30ml", price="499.00"),
            _make_item(retailer_sku="C", gtin=None, raw_size="30ml", price="299.00"),
        ]
        svc = FeedIngestionService(session)
        result = await svc.ingest_feed(_make_envelope(items))

        assert result.total == 3
        assert result.inserted == 2
        assert result.skipped == 1
        assert result.failed == 0
        assert session.add.call_count == 2

    async def test_feed_ingest_result_totals_invariant(
        self, mock_session: AsyncMock
    ) -> None:
        """FeedIngestResult.total must always equal inserted + skipped + failed."""
        items = [
            _make_item(retailer_sku="A", raw_size="30ml"),
            _make_item(retailer_sku="B", raw_size="invalid"),  # will fail
        ]
        svc = FeedIngestionService(mock_session)
        result = await svc.ingest_feed(_make_envelope(items))

        assert result.total == result.inserted + result.skipped + result.failed
