# High-Level Design: Real-Time Order Management System

## 1. Overview

This document describes the high-level architecture for a **Real-Time Order Management System (OMS)** for an e-commerce platform processing ~50,000 orders/day with peak bursts of 500 orders/minute.

---

## 2. Goals & Non-Goals

### Goals
- Accept and process orders in real time with < 500ms end-to-end latency
- Guarantee exactly-once order processing (no duplicates, no drops)
- Support horizontal scaling to handle 10× traffic spikes
- Provide a real-time dashboard for ops teams

### Non-Goals
- Payment processing (handled by external payment gateway)
- Warehouse fulfillment (out of scope, via ERP integration)

---

## 3. System Architecture

### 3.1 Components

```
┌─────────────┐     HTTPS      ┌──────────────────┐
│  Mobile App │──────────────▶│  API Gateway      │
│  Web App    │               │  (Kong / AWS APIGW)│
└─────────────┘               └────────┬─────────┘
                                        │ REST
                               ┌────────▼─────────┐
                               │  Order Service    │
                               │  (Node.js)        │
                               └────────┬─────────┘
                          ┌─────────────┼──────────────┐
                          │             │              │
                 ┌────────▼──┐  ┌───────▼────┐  ┌────▼──────────┐
                 │  Postgres  │  │  Kafka     │  │  Redis Cache  │
                 │  (primary) │  │  (events)  │  │  (sessions)   │
                 └────────────┘  └───────┬────┘  └───────────────┘
                                         │
                          ┌──────────────┼───────────────┐
                          │              │               │
                 ┌────────▼──┐  ┌────────▼───┐  ┌───────▼──────┐
                 │ Inventory  │  │ Notification│  │  Analytics   │
                 │ Service    │  │ Service     │  │  Service     │
                 │ (Python)   │  │ (Go)        │  │  (Python)    │
                 └────────────┘  └─────────────┘  └──────────────┘
```

### 3.2 Data Flow

1. Client sends `POST /orders` to API Gateway
2. API Gateway authenticates via JWT, rate-limits, and forwards to Order Service
3. Order Service validates payload, writes to PostgreSQL (`orders` table), publishes `order.created` event to Kafka
4. Three consumers process in parallel:
   - **Inventory Service**: reserves stock, publishes `stock.reserved` or `stock.insufficient`
   - **Notification Service**: sends confirmation email/SMS via SendGrid/Twilio
   - **Analytics Service**: writes to ClickHouse for real-time dashboard
5. Order Service polls for `stock.reserved` event and updates order status to `confirmed` or `failed`

---

## 4. Technology Stack

| Layer | Technology | Justification |
|---|---|---|
| API Gateway | Kong (self-hosted) | Plugin ecosystem, rate limiting, JWT auth |
| Order Service | Node.js 20 + Fastify | Low latency, async I/O, team familiarity |
| Inventory Service | Python 3.11 + FastAPI | ML team owns it, already Python |
| Notification Service | Go 1.22 | High throughput, low memory footprint |
| Message Broker | Apache Kafka 3.6 | Exactly-once semantics, replay capability |
| Primary DB | PostgreSQL 16 on AWS RDS | ACID, row-level locking for inventory |
| Cache | Redis 7 (ElastiCache) | Session store, idempotency keys |
| Analytics DB | ClickHouse | Columnar, fast aggregations for dashboard |
| Container Platform | Kubernetes (EKS) | Auto-scaling, blue/green deployments |
| Service Mesh | Istio | mTLS, circuit breaking, observability |

---

## 5. API Design

### 5.1 Create Order
```
POST /api/v1/orders
Authorization: Bearer <jwt>

{
  "customer_id": "cust_123",
  "items": [
    { "sku": "PROD-001", "qty": 2, "price": 29.99 },
    { "sku": "PROD-042", "qty": 1, "price": 9.99 }
  ],
  "shipping_address": {
    "line1": "123 Main St",
    "city": "San Francisco",
    "zip": "94105",
    "country": "US"
  },
  "payment_token": "tok_visa_4242"
}

Response 202 Accepted:
{
  "order_id": "ord_xkcd9999",
  "status": "pending",
  "estimated_confirmation_ms": 500
}
```

### 5.2 Get Order Status
```
GET /api/v1/orders/{order_id}
Response 200:
{
  "order_id": "ord_xkcd9999",
  "status": "confirmed",
  "items": [...],
  "total": 69.97,
  "created_at": "2026-04-03T10:00:00Z"
}
```

---

## 6. Database Schema (simplified)

```sql
CREATE TABLE orders (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id VARCHAR(64) NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'pending',
    total_cents INTEGER NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE order_items (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id   UUID REFERENCES orders(id),
    sku        VARCHAR(64) NOT NULL,
    qty        INTEGER NOT NULL,
    unit_cents INTEGER NOT NULL
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_status   ON orders(status);
```

---

## 7. Scalability

- **Order Service**: Horizontal pod autoscaler triggers at 70% CPU; scales from 3 → 20 replicas
- **Kafka**: 12 partitions for `order.created` topic, 3 consumer group replicas per service
- **PostgreSQL**: Read replicas for analytics queries; connection pooling via PgBouncer
- **Redis**: Cluster mode with 3 shards; TTL of 24h on idempotency keys

---

## 8. Security Considerations

- All inter-service communication over mTLS via Istio
- JWT tokens signed with RS256, 15-minute expiry
- PII (customer address, email) encrypted at rest using AWS KMS
- No secrets in environment variables — all via AWS Secrets Manager
- Rate limiting: 100 req/min per customer, 10,000 req/min per API key

---

## 9. Failure Modes & Mitigations

| Failure | Detection | Mitigation |
|---|---|---|
| Order Service crash | Kubernetes liveness probe | Pod restart + traffic rerouted via Istio |
| Kafka lag spike | Prometheus alert > 10k messages | Scale consumer pods, page on-call |
| PostgreSQL primary failover | RDS Multi-AZ | Automatic failover < 60s |
| Inventory Service slow | Istio circuit breaker | Fail-open: mark order `pending_inventory` and retry async |
| Duplicate order submission | Redis idempotency key (order hash) | Return cached 202, skip processing |

---

## 10. Observability

- **Metrics**: Prometheus + Grafana (order rate, p99 latency, Kafka lag)
- **Tracing**: Jaeger with OpenTelemetry SDK on all services
- **Logging**: Structured JSON → Fluent Bit → OpenSearch
- **Alerting**: PagerDuty for p99 > 1s, error rate > 1%, Kafka lag > 10k

---

## 11. Open Questions

1. Should we use Outbox Pattern for Kafka publishing to guarantee DB + Kafka atomicity?
2. Is ClickHouse overkill — would Postgres with TimescaleDB suffice for analytics?
3. Should Notification Service move to a managed service (AWS SNS/SES) to reduce ops burden?
