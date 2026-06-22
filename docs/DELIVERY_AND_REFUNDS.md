# Delivery Tracking And Refund Verification

> Status: roadmap/design notes. The hackathon repo implements the demo slice; this document lists production work that is not complete yet.


The hackathon demo exposes a merchant-estimated delivery window. Production
should distinguish that from real carrier tracking.

## Delivery States

```text
quoted -> ordered -> processing -> shipped -> in_transit -> delivered
                         \-> delayed
                         \-> cancelled
```

## Tracking Adapter Interface

Merchant status endpoint should return:

```json
{
  "order_id": "40",
  "state": "processing",
  "estimated_delivery": "2026-06-22",
  "delivery_window": {
    "earliest_date": "2026-06-20",
    "latest_date": "2026-06-22",
    "source": "merchant_estimate"
  },
  "tracking": {
    "carrier": "DHL",
    "tracking_number": "0034...",
    "tracking_url": "https://...",
    "status": "in_transit",
    "source": "woocommerce_tracking_plugin",
    "last_checked_at": "2026-06-18T12:00:00Z"
  }
}
```

## WooCommerce Sources

The plugin can read common metadata:

- `_wc_shipment_tracking_items`
- `_tracking_provider`
- `_tracking_number`
- `_tracking_url`

Real carrier status requires either:

- a WooCommerce shipment/tracking plugin that writes status back to the order;
- a merchant-side DHL/UPS/DPD/etc. API integration;
- a logistics provider webhook that updates WooCommerce metadata.

## Refund State Machine

```text
requested -> verifier_pending -> rail_refunded -> woo_refund_recorded
                         \-> verifier_rejected
                         \-> manual_review
```

## Cancellation State

ShopBridge cancellations are separate from refunds:

```text
requested -> merchant_approved -> woo_order_cancelled -> refund_required
                                  \-> no_refund_due
```

The WooCommerce plugin rejects cancellation after terminal order states or when
shipment tracking is already attached. A successful cancellation can change the
WooCommerce order status to `cancelled`, but it does not move card, Tempo,
stablecoin, or EUR funds. Paid orders still need a separate verified refund
flow before the agent can say money was returned.

## Refund Verification Requirements

ShopBridge refunds require an idempotency key. Exact replays return the
existing WooCommerce refund, conflicting replays are rejected, and amounts above
the remaining refundable amount fail closed before verifier or Woo refund
creation.

For Stripe/card:

- use Stripe refund APIs;
- bind refund to original payment intent/reference;
- return `refund_reference`;
- handle partial refunds and chargeback/dispute state.

For Tempo/stablecoin:

- verify transfer back to source or agreed refund recipient;
- bind refund transfer to original order/quote;
- return refund transaction reference;
- handle FX and network fee disclosure.

For demo mode:

- create WooCommerce refund record;
- set `real_refund_verified=false`;
- do not claim funds moved.

## User-Facing Rule

The agent should say:

- "Estimated delivery" when only merchant estimate exists.
- "Carrier tracking" only when a carrier/tracking source is present.
- "Refund recorded" for demo refunds.
- "Refund executed" only when the rail verifier returned a real refund
  reference.
- "Order cancelled" only for Woo order state; mention separately when a refund
  is still required.
