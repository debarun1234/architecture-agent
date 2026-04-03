# High-Level Design: Global Real-Time Commerce & Analytics Platform

**System Name:** NexaCommerce — Multi-Tenant Global SaaS Platform  
**Document Type:** High-Level Design (HLD)  
**Version:** 2.0  
**Date:** April 2026

---

## 1. Overview

NexaCommerce is a multi-tenant B2C/B2B commerce platform serving **50 million DAU globally** across
3 geographic regions (US, EU, APAC). It provides product discovery, cart & checkout, real-time
inventory, personalised recommendations, seller dashboards, and sub-second analytics.

**Key SLOs**

| Metric | Target |
|---|---|
| API p99 latency (checkout) | ≤ 200 ms |
| API p99 latency (search) | ≤ 80 ms |
| Availability | 99.99 % (≤ 52 min downtime/year) |
| Recovery Time Objective (RTO) | < 2 min |
| Recovery Point Objective (RPO) | < 5 s |
| Peak QPS (global, combined) | 250,000 |
| Data volume | 2 TB new data/day |

---

## 2. Goals & Non-Goals

### Goals
- Active-active multi-region deployment with automatic failover
- Horizontal, stateless services — no single point of failure at any tier
- All read paths served from cache; zero hot-row contention on writes
- Sub-second personalised search across 500 M product SKUs
- Near-real-time analytics dashboards (< 5 s lag)
- Zero-trust security for every service-to-service call
- Full observability: metrics, distributed traces, structured logs

### Non-Goals
- Physical warehouse management (ERP integration only)
- Fraud ML training pipeline (separate MLOps platform)
- Third-party marketplace white-labelling (Phase 2)

---

## 3. System Architecture

### 3.1 Deployment Topology

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │                          Global Load Balancer                          │
   │               (Anycast DNS  ·  BGP Anycast  ·  GeoDNS)                │
   └──────────┬───────────────────────┬───────────────────────┬─────────────┘
              │ us-central1           │ europe-west4          │ asia-east1
   ┌──────────▼──────────┐  ┌─────────▼──────────┐  ┌────────▼──────────────┐
   │  Regional Cluster   │  │  Regional Cluster  │  │  Regional Cluster     │
   │  (GKE Autopilot)    │  │  (GKE Autopilot)  │  │  (GKE Autopilot)      │
   └─────────────────────┘  └────────────────────┘  └───────────────────────┘
         ▲  Active                  ▲  Active                ▲  Active
         └──── Cross-region replication via Spanner / Pub/Sub / GCS ────────┘
```

### 3.2 Request Flow (Checkout Path)

```
Browser / Mobile
      │ HTTPS TLS 1.3
      ▼
┌──────────────┐     Cache HIT      ┌─────────────────────┐
│  Edge CDN    │────────────────────▶  Static Assets       │
│  (Cloudflare │                    │  (Cloudflare R2)     │
│  Enterprise) │                    └─────────────────────┘
│              │  Cache MISS / API
│              ├─────────────────▶ ┌──────────────────────────┐
└──────────────┘                   │  Cloud Armor WAF          │
                                   │  (OWASP Top 10, DDoS,     │
                                   │   Bot Management)         │
                                   └──────────┬───────────────┘
                                              │
                                   ┌──────────▼───────────────┐
                                   │  API Gateway (Apigee X)  │
                                   │  · JWT validation        │
                                   │  · Rate limiting         │
                                   │    (token bucket / tenant)│
                                   │  · Request coalescing    │
                                   │  · gRPC transcoding      │
                                   └──────────┬───────────────┘
                                              │ gRPC (mTLS)
                              ┌───────────────┼───────────────┐
                              │               │               │
                   ┌──────────▼──┐  ┌─────────▼──┐  ┌────────▼──────┐
                   │  Cart Svc   │  │  Order Svc │  │  Catalog Svc  │
                   │  (Go)       │  │  (Go)      │  │  (Rust)       │
                   └──────────┬──┘  └─────────┬──┘  └────────┬──────┘
                              │               │               │
          ┌───────────────────┼───────────────┼───────────────┤
          │                   │               │               │
   ┌──────▼──────┐    ┌───────▼─────┐  ┌─────▼──────┐  ┌────▼────────────┐
   │  Redis      │    │  Cloud      │  │  AlloyDB   │  │  Spanner        │
   │  Cluster    │    │  Pub/Sub    │  │  (OLTP)    │  │  (global orders)│
   │  (L2 cache) │    │  (events)   │  └────────────┘  └─────────────────┘
   └─────────────┘    └─────────────┘
```

### 3.3 Read Path: Catalog & Search

```
Request
  │
  ▼
Cloudflare Cache (TTL 30 s, surrogate keys per SKU)
  │ MISS
  ▼
Catalog Service
  │
  ├─ L1 in-process cache (Ristretto, 256 MB) ─── HIT ──▶ response
  │  MISS
  ├─ Redis Cluster (L2, 128 GB) ──────────────── HIT ──▶ response + backfill L1
  │  MISS
  ├─ AlloyDB read replica (hot data < 90 days)
  │  or
  └─ BigQuery (cold data, archive search)
```

---

## 4. Service Inventory

| Service | Language | Protocol | Instances (min→max) | Bottleneck Mitigations |
|---|---|---|---|---|
| API Gateway (Apigee X) | N/A (managed) | HTTP/2, gRPC | Auto | Rate limiting, coalescing, OAuth |
| Cart Service | Go 1.22 | gRPC | 10 → 500 | Redis-backed sessions, optimistic locking, idempotency keys |
| Order Service | Go 1.22 | gRPC | 10 → 300 | Saga pattern, Spanner TXN, outbox table |
| Catalog Service | Rust 1.77 | gRPC | 5 → 200 | 3-tier cache, read replicas, Bloom filter for negative lookups |
| Inventory Service | Go 1.22 | gRPC | 10 → 200 | Per-SKU sharded counters (Spanner), reservation TTL |
| Payment Service | Python 3.12 | gRPC | 5 → 100 | Stripe async webhooks, idempotency keys, saga rollback |
| Notification Service | Go 1.22 | gRPC | 3 → 50 | Pub/Sub fan-out, deduplication, dead-letter retry |
| Search Service | Java 21 (Elasticsearch) | REST | 6 → 60 | Dedicated data nodes, query caching, async index updates |
| Recommendation Service | Python 3.12 + TF Serving | gRPC | 4 → 40 | Precomputed vectors in Bigtable, ANN index (ScaNN) |
| Analytics Ingest | Rust (Dataflow) | Pub/Sub | Auto (streaming) | Windowed aggregation, column partitioning |
| Analytics Query | BigQuery | SQL | Serverless | Materialized views, BI Engine reservation |
| Identity Service | Go 1.22 | gRPC | 5 → 100 | OIDC, refresh token rotation, short-lived JWTs (15 min) |

---

## 5. Data Architecture

### 5.1 Storage Tiers

| Tier | Technology | Use Case | TTL / Retention |
|---|---|---|---|
| L1 — In-process | Ristretto (per pod) | Hottest catalog data | 60 s |
| L2 — Distributed cache | Redis 7 Cluster (3 shards, 6 nodes) | Sessions, cart, rate limits | 24 h |
| L3 — OLTP | AlloyDB (HA, 3 read replicas/region) | Orders, inventory, users | Indefinite |
| L4 — Global OLTP | Cloud Spanner (multi-region `nam-eur-asia1`) | Cross-region order state | Indefinite |
| L5 — Time-series | Bigtable (HBase API) | Clickstream, event store | 90 days hot, then GCS |
| L6 — Data warehouse | BigQuery (partitioned by day) | Analytics, reporting | 7 years |
| L7 — Object store | GCS (multi-region) | Media, exports, backups | Lifecycle policies |

### 5.2 Write Path (Order Creation — Saga)

```
1. Order Service writes ORDER (status=PENDING) to Spanner
2. Outbox table row inserted in the same Spanner transaction
3. Outbox CDC connector publishes order.created to Pub/Sub
4. Saga orchestrator (Order Service) drives:
   a. Inventory Service: reserve_stock(sku, qty, ttl=15min)
       → on success: publish stock.reserved
       → on failure: publish order.failed  →  compensate above
   b. Payment Service: charge(token, amount)
       → on success: publish payment.captured
       → on failure: publish order.failed  → release_stock compensation
   c. Order Service: update ORDER status=CONFIRMED
5. Notification Service consumes order.confirmed → send email/push
```

### 5.3 Inventory Anti-Contention Pattern

Inventory counters use **Spanner per-SKU counter shards** (10 shards per popular SKU) to eliminate hotspot rows:

```sql
-- Inventory counter table (sharded)
CREATE TABLE inventory_shards (
  sku         STRING(64) NOT NULL,
  shard_id    INT64 NOT NULL,       -- 0..9
  reserved    INT64 NOT NULL DEFAULT 0,
  available   INT64 NOT NULL DEFAULT 0,
) PRIMARY KEY (sku, shard_id);

-- Reserve: pick a random shard for the tenant/session
UPDATE inventory_shards
SET reserved = reserved + @qty
WHERE sku = @sku AND shard_id = @shard
  AND available - reserved >= @qty;

-- Read total: sum across shards (parallelised by Spanner)
SELECT SUM(available - reserved) AS free
FROM inventory_shards
WHERE sku = @sku;
```

---

## 6. API Design

### 6.1 Conventions
- All APIs versioned: `/api/v1/...`, `/api/v2/...`
- gRPC internally; REST+JSON at the API Gateway edge via gRPC-HTTP transcoding
- Idempotency-Key header required on all mutating endpoints
- Cursor-based pagination (no OFFSET) to avoid deep-page performance cliffs

### 6.2 Create Order
```
POST /api/v1/orders
Authorization: Bearer <short-lived-jwt>
Idempotency-Key: <uuid>

{
  "tenant_id": "tnnt_abc123",
  "customer_id": "cust_xyz789",
  "items": [
    { "sku": "SKU-001", "qty": 2, "unit_price_cents": 2999 }
  ],
  "shipping_address": { "line1": "…", "city": "…", "zip": "…", "country": "US" },
  "payment_method_id": "pm_stripe_abc"
}

Response 202 Accepted:
{
  "order_id": "ord_7f3k9p",
  "status": "pending",
  "saga_id": "saga_f8d2",
  "estimated_confirmation_ms": 400
}
```

### 6.3 Stream Order Events (SSE)
```
GET /api/v1/orders/{order_id}/events
Authorization: Bearer <jwt>
Accept: text/event-stream

data: {"event":"stock_reserved","ts":"2026-04-03T10:00:01Z"}
data: {"event":"payment_captured","ts":"2026-04-03T10:00:01.4Z"}
data: {"event":"order_confirmed","ts":"2026-04-03T10:00:01.6Z"}
```

---

## 7. Technology Stack

| Layer | Technology | Justification |
|---|---|---|
| CDN / Edge | Cloudflare Enterprise | Anycast, 300+ PoPs, WAF, cache, Workers for edge routing |
| API Gateway | Apigee X | JWT auth, quota, analytics, gRPC transcoding, threat protection |
| Container Platform | GKE Autopilot (per-region) | Auto-provision nodes, no node pool management |
| Service Mesh | Istio 1.21 | mTLS everywhere, circuit breaking, traffic management, tracing |
| Message Broker | Cloud Pub/Sub + Cloud Dataflow | Managed, QoS guarantees, exactly-once via Dataflow |
| OLTP (regional) | AlloyDB (PostgreSQL-compatible) | 100x faster reads vs Cloud SQL, built-in ColumnStore for analytics |
| OLTP (global) | Cloud Spanner (multi-region) | Linearisable TXNs across regions, global order state |
| Cache | Redis 7 Cluster (Memorystore) | Sub-ms reads, cluster mode, automatic failover |
| Search | Elasticsearch 8 (GKE) | Full-text + vector search (kNN), aggregations |
| OLAP | BigQuery + BI Engine | Serverless, petabyte-scale, no index tuning |
| Time-series | Bigtable (HBase API) | Single-digit ms wide-column reads, 50k+ QPS per node |
| Object Storage | GCS multi-region | 11 nines durability, lifecycle tiering |
| Secrets | Secret Manager | Versioned, IAM-gated, audit-logged — no secrets in env vars |

---

## 8. Scalability Design (Bottleneck Elimination)

### 8.1 API Layer
- **Request coalescing** in Apigee: identical `GET` requests within a 5 ms window collapsed into one upstream call
- **Response caching** for `GET /catalog/:id` with `Surrogate-Control: max-age=30, stale-while-revalidate=60`
- **Adaptive rate limiting**: tenant-scoped token bucket (Apigee quota policies); burst allows 2× steady-state for 60 s

### 8.2 Compute
- **HPA** on CPU (70%) + custom metric `pub_sub_subscription_lag` for event consumers
- **KEDA** for Pub/Sub-driven autoscaling of async workers to zero when idle
- **Pod Disruption Budgets**: minimum 2 pods always available per service during node drain
- **Topology spread constraints**: pods spread across 3 zones, no more than 1 pod per node for critical services

### 8.3 Database
| Bottleneck | Mitigation |
|---|---|
| Hot-row on inventory | Sharded counters (10 shards/SKU) — see §5.3 |
| N+1 queries from catalog | DataLoader pattern (batched `IN` queries), eager joins |
| Deep pagination | Keyset pagination (`WHERE id > :cursor ORDER BY id LIMIT 100`) |
| Connection pool exhaustion | PgBouncer transaction mode in front of AlloyDB |
| Write amplification on orders | Write to Spanner once; fan-out via outbox CDC |
| Analytics load on OLTP | Zero analytics queries hit AlloyDB; all go to BigQuery via Dataflow |

### 8.4 Cache
- **Cache warming**: on deployment, a Kubernetes Job pre-populates top-1000-SKU cache entries before traffic switch
- **Cache stampede prevention**: probabilistic early expiry (PER algorithm) + Redis lock with `SET NX PX 100`
- **Negative caching**: Bloom filter in Catalog Service rejects non-existent SKUs before hitting DB
- **Cache invalidation**: SKU update → Pub/Sub `sku.updated` event → all listening pods flush L1 + invalidate Redis key + purge CDN surrogate key via Cloudflare API

### 8.5 Search
- Dedicated Elasticsearch **hot–warm–cold** architecture: 6 hot nodes (SSDs), 6 warm nodes (HDDs), cold tier to GCS
- Write path: AlloyDB change-data-capture → Pub/Sub → Dataflow → Elasticsearch (async, < 2 s lag)
- No synchronous writes to Elasticsearch from the Order or Catalog service
- Elasticsearch **circuit breaker** tuned: `indices.breaker.request.limit=60%` to prevent OOM on heavy aggregations

---

## 9. Security Architecture

### 9.1 Zero-Trust Network
- All pod-to-pod: **mutual TLS (mTLS)** enforced by Istio with SPIFFE/SPIRE workload identity
- No direct pod-to-pod calls bypass service mesh — all traffic routes through Envoy sidecars
- `PeerAuthentication` set to `STRICT` across all namespaces
- `NetworkPolicy`: default-deny all; explicit allow-list per service

### 9.2 Identity & Access
- Users: **OIDC** (Google Identity) + social login; access tokens: 15-min RSA-256 JWTs; refresh tokens: opaque, server-side rotating, stored in HttpOnly Secure cookies (not localStorage)
- Services: **Workload Identity** (GKE ↔ GCP IAM) — no service account keys on disk
- Secrets: **Secret Manager** with CMEK; zero env-var secrets; accessed via ADC at runtime

### 9.3 Data Protection
- PII fields (`email`, `address`, `phone`) encrypted at column level using Cloud KMS AEAD (`AES-256-GCM`) before writing to AlloyDB
- Payment data: PCI DSS scope minimised — no card numbers stored; Stripe tokenisation only
- Data residency: EU tenant data stays in `europe-west4`; GDPR right-to-erasure implemented via pseudonymisation + deletion of KMS key

### 9.4 Supply Chain
- All container images scanned by **Artifact Registry vulnerability scanning** before deployment
- `SLSA Level 3` provenance attestations attached to every release image
- Admission webhook **Kyverno** enforces: read-only root FS, no `privileged`, approved image registry

---

## 10. Reliability & Failure Modes

| Failure Scenario | Detection | Mitigation |
|---|---|---|
| Catalog pod OOM | Kubernetes liveness probe | Pod restart; Istio retries (max 2, 50 ms backoff); circuit breaker opens after 5 failures/10 s |
| AlloyDB primary failover | Cloud Monitoring cloud_sql/uptime alert | Automatic failover < 30 s; PgBouncer reconnects; P99 chart expected spike then recovery |
| Redis shard failure | `redis_cluster_state != ok` | Cluster auto-promotes replica; cache miss spike absorbed by read replicas |
| Spanner region outage | Spanner SLO burn-rate alert | Multi-region config routes reads to healthy quorum; writes tolerate 1-region loss |
| Pub/Sub consumer lag > 50k | Custom metric alert | KEDA scales consumer pods; Pub/Sub dead-letter after 5 delivery attempts |
| Elasticsearch out of memory | Circuit breaker triggered | Requests fail-open to AlloyDB catalog fallback; page on-call |
| Payment gateway timeout | Stripe webhook missed | Saga timeout (30 s) fires compensating transaction; order status = `failed`; idempotency key prevents double charge |
| Deployment regression | p99 latency burn-rate > 2× | Progressive rollout via Istio traffic splitting (5 % → 25 % → 100 %); automatic rollback on SLO breach |

### 10.1 Chaos Engineering Schedule
- Weekly: random pod kill (LitmusChaos)
- Monthly: regional failover drill (Spanner + Pub/Sub)
- Quarterly: full data-centre evacuation drill

---

## 11. Observability Stack

| Signal | Tooling | Key Dashboards |
|---|---|---|
| Metrics | Cloud Monitoring + Prometheus (federated) | Checkout funnel p99, error rate by service, Kafka/Pub/Sub lag, Redis hit rate |
| Distributed Traces | Cloud Trace + OpenTelemetry SDK | End-to-end checkout trace, DB query spans, cache hit/miss |
| Structured Logs | Fluent Bit → Cloud Logging | Correlation with trace IDs; Security audit log; cost anomaly log |
| Alerting | Cloud Monitoring → PagerDuty | SLO burn-rate alerts (1h + 6h windows); p99 > 500 ms for 5 min; error rate > 0.1% |
| SLO Dashboards | Grafana (Cloud Monitoring data source) | Error budget burn rate per service, time-to-target trend |

**Sampling strategy**: 100 % of errors sampled; 5 % of successful checkout traces; 1 % of search; 100 % of `checkout_confirmation` span.

---

## 12. Deployment & CI/CD

```
Developer push
      │
      ▼
GitHub Actions
  ├─ Unit tests (coverage ≥ 80 %)
  ├─ Integration tests (test AlloyDB emulator + Redis)
  ├─ Security: Trivy image scan, SAST (CodeQL), dependency audit
  └─ Build + push to Artifact Registry (SLSA provenance)
      │
      ▼
Argo CD (GitOps)
  ├─ Staging deployment (100 % traffic)
  ├─ Smoke tests + synthetic transactions
  └─ Progressive production rollout via Istio:
       5 % → soak 10 min (watch SLO burn) → 25 % → soak → 100 %
       Auto-rollback if p99 latency > 2× baseline or error rate > 0.5 %
```

**Feature flags**: LaunchDarkly per-tenant flags gate all new features; no code branches in production.

---

## 13. Cost Optimisation

- **Spot / Preemptible nodes** for batch workloads (Analytics Ingest, nightly exports): 70 % cost reduction
- **Committed-use discounts** for baseline GKE + AlloyDB + Spanner
- **Idle cluster scale-to-zero**: dev/staging clusters scale down at nights/weekends via GKE Node Auto-Provisioning
- **BigQuery slot reservations**: 500 baseline slots; 2000-slot burst for month-end reports
- **CDN offload target**: ≥ 85 % of bytes served from Cloudflare cache; monitored monthly

---

## 14. Open Questions

1. **Global Spanner vs. regional AlloyDB for orders**: Spanner adds ~8 ms due to Paxos quorum — acceptable for checkout confirmation but may need review for high-frequency inventory checks.
2. **Search indexing lag**: 2 s CDC lag for Elasticsearch is acceptable today; if real-time inventory in search is required, explore Elasticsearch change-data-capture on Spanner directly.
3. **Bigtable vs. AlloyDB for clickstream reads**: Bigtable is optimised for write-heavy single-row lookups. If multi-column analytics are added, evaluate AlloyDB ColumnStore extension instead.
4. **Recommendation serving latency**: ScaNN ANN index achieves < 20 ms p99; if < 10 ms is required, move model serving to NVIDIA Triton + GPU node pool.
5. **Cross-region data residency enforcement**: Today enforced per-tenant at application layer; consider Spanner managed encryption with per-region CMEK keys for stronger isolation.
