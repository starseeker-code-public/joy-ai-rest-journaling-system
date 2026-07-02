# Joy --- AI Manifestation Journal Platform

![Status](https://img.shields.io/badge/status-active_development-blue)
![Architecture](https://img.shields.io/badge/architecture-event_driven_microservices-green)
![Cloud](https://img.shields.io/badge/cloud-kubernetes-blue)
![AI](https://img.shields.io/badge/AI-NLP-orange)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

------------------------------------------------------------------------

# Table of Contents

1.  General Description\
2.  Project Goals\
3.  Project Status\
4.  System Architecture\
5.  Architecture Diagram\
6.  Microservices Overview\
7.  Event‑Driven Messaging System\
8.  AI Processing Pipeline\
9.  Database Design (MongoDB)\
10. MongoDB Schema Diagrams\
11. API Design & OpenAPI Documentation\
12. Technology Stack\
13. Third Party Integrations\
14. Observability & Monitoring\
15. Deployment Architecture\
16. Development Workflow (Docker)\
17. Testing Workflow\
18. Feature Backlog\
19. Contribution Guidelines\
20. Contributors\
21. Full Testing Analysis\
22. Extended Feature Ideas\
23. License

------------------------------------------------------------------------

# General Description

## Joy

**Joy** is a distributed AI‑powered journaling platform designed to
demonstrate **advanced backend engineering, distributed systems design,
and cloud‑native architecture**.

The platform allows users to write personal journal entries reflecting
on:

-   emotions
-   habits
-   progress toward goals
-   personal reflections

Entries are processed through an **AI analysis pipeline** capable of
generating:

-   emotional insights
-   sentiment analysis
-   behavioral patterns
-   habit correlations
-   long‑term trend analytics

This project intentionally simulates **production-grade backend
infrastructure**, combining:

-   microservices
-   asynchronous event pipelines
-   polyglot backend architecture
-   multiple database paradigms
-   AI/NLP analysis pipelines
-   containerized deployment
-   observability tooling

The system serves as a **technical portfolio demonstrating senior
backend engineering skills**.

------------------------------------------------------------------------

# Project Goals

The platform is built with the explicit objective of showcasing
real-world engineering capabilities.

## Distributed Systems Engineering

Demonstrates:

-   event driven architecture
-   asynchronous workflows
-   decoupled service communication
-   scalable microservices

## Polyglot Backend Development

The system includes services implemented using:

-   Python
-   Go
-   Rust
-   Node.js
-   .NET

Each ecosystem highlights different performance and architectural
characteristics.

## AI System Integration

The project integrates NLP capabilities including:

-   sentiment classification
-   emotion detection
-   topic extraction
-   AI insight generation

## Cloud Native Infrastructure

Infrastructure demonstrates:

-   containerized services
-   Kubernetes orchestration
-   service observability
-   horizontal scalability

------------------------------------------------------------------------

# Project Status

Project Name:

Joy --- AI Manifestation Journal Platform

Current Status:

Active Development

Architecture:

Distributed Microservices

Current Version:

v0.5.0

Development Version:

v0.6.0-dev

Repository Structure:

    joy-platform
     ├ gateway
     ├ auth-service
     ├ user-service
     ├ journal-service
     ├ habit-service
     ├ goal-service
     ├ ai-analysis-service
     ├ insight-service
     ├ analytics-service
     └ frontend

Last Major Feature:

Habit Service with check-ins and streak tracking

Last Update:

July 2026

------------------------------------------------------------------------

# Roadmap

The platform evolves in phases. Each phase introduces **one** new piece of
technology (or one new domain service) so the system grows in small,
reviewable increments. Within a phase, work is split into a sublist of
focused, incremental steps.

## Completed

### v0.0.x --- Scaffolding *(done)*

Initial Flask project skeleton, layout, and tooling.

### v0.1.x --- Basic CRUD *(done)*

Single-user journal entries stored in local JSON files.

-   Journal model, service, and routes
-   In-memory and file-based storage
-   Health endpoint
-   First round of tests

### v0.2.x --- Multi-user Foundation *(done)*

MongoDB persistence, JWT authentication, per-user ownership, and Docker.

-   MongoDB migration (JSON files → pymongo)
-   Docker + Compose with Mongo service
-   User registration with Argon2id hashing
-   JWT login / logout / me
-   Route protection and ownership scoping
-   Enriched journal model (mood, tags, kind)
-   Validation, rate limiting, startup-key guard, shared utilities

### v0.3.x --- Event Bus (RabbitMQ) *(done)*

Asynchronous messaging foundation. Journal writes emit events that downstream
services will consume.

-   RabbitMQ container in docker-compose with healthcheck
-   EventPublisher wrapping pika with `joy.events` topic exchange
-   `journal.created` emitted from JournalService on create
-   EventConsumer and stub `consumer.py` service in compose
-   End-to-end integration test with an in-memory fake broker

### v0.4.x --- Sentiment Analysis (HuggingFace Transformers) *(done)*

First AI capability: sentiment scoring on journal content.

-   Add transformers dependency and model bootstrap script
-   AnalysisService wrapping a deterministic sentiment pipeline
-   Wire AnalysisService as `journal.created` consumer
-   Persist sentiment to the journal `ai` subdocument
-   `GET /api/journals/<id>/sentiment` endpoint
-   Tests with a stub model for deterministic CI

### v0.5.x --- Habit Service *(done)*

Second domain entity: trackable habits with streaks. No new technology ---
proves the stack scales to more services.

-   Habit data model (name, frequency, user_id, timestamps)
-   HabitService CRUD with user scoping
-   `/api/habits` routes (auth-gated)
-   Habit-check endpoint to record a completion (idempotent per date)
-   Daily and weekly streak calculation with a one-period grace window
-   Tests for ownership isolation and streak math

### v0.6.x --- Goal Service *(done)*

Third domain entity: goals with milestones.

-   Goal data model (title, description, milestones\[\], target_date, user_id)
-   GoalService CRUD with user scoping
-   `/api/goals` routes (auth-gated)
-   Add-milestone and milestone-complete endpoints (idempotent)
-   Progress calculation derived from milestones
-   Tests for ownership isolation and progress math

### v0.7.x --- Full-text Search (OpenSearch) *(done)*

Make journal content searchable.

-   OpenSearch container with healthcheck
-   `journal.updated` / `journal.deleted` events emitted by JournalService
-   search_indexer worker syncing the index from the event bus
-   `/api/journals/search?q=` endpoint (503 when the backend is down)
-   Filter by tags, date range, kind; result limit capped at 100
-   Tests using a fake OpenSearch client

### v0.8.x --- Analytics Store (ClickHouse) *(done)*

Aggregate analytics separated from the operational database.

-   ClickHouse container and `journal_events` MergeTree schema
-   `journal.analyzed` event published by the analysis worker
-   analytics_sink worker mirroring created/updated/analyzed events
-   `/api/analytics/mood-trend` endpoint (daily average mood)
-   `/api/analytics/tag-frequency` endpoint
-   Tests with a fake ClickHouse client; live verification via compose

### v0.9.x --- Insight Service *(done)*

Weekly behavioral insights derived from analytics. Builds on v0.4 + v0.8.

-   Standalone insight_worker consuming `journal.analyzed`
-   Hourly scheduler materializing the previous completed week
-   Insight model (period, summary, highlights, stats) upserted per user-week
-   `/api/insights` endpoint
-   Aggregation tests on canned analytics data

### v0.10.x --- Distributed Cache & Rate Limiting (Redis) *(done)*

Replace the in-memory rate limiter with a shared, durable backend; add a
caching layer.

-   Redis container with healthcheck (published on 6380)
-   RedisRateLimiter implementing the existing `allow()` interface (fails open)
-   Login limiter switched to Redis in `create_app`
-   `/auth/me` lookups cached with a 60s TTL
-   Tests using fakeredis

### v0.11.x --- API Gateway *(done)*

Unified entry point in front of services.

-   Nginx reverse proxy container on port 8080
-   Central route registry (`gateway/nginx.conf`)
-   Per-route edge rate limits (`/auth/login` stricter than `/api/*`)
-   Aggregated `/health` reporting Mongo, Redis, RabbitMQ, OpenSearch, ClickHouse
-   JWT verification stays service-side (nginx would need njs; documented)

### v0.12.x --- Structured Logging (structlog) *(done)*

Production-grade logs.

-   structlog config shared by the API and all workers (stdlib routed through it)
-   Request-id middleware (honors inbound `X-Request-ID`, echoes it back)
-   JSON output via `LOG_FORMAT=json`; console renderer by default
-   Per-request log context (request_id, user_id, path, status, duration_ms)

### v0.13.x --- Metrics (Prometheus) *(done)*

Operational visibility.

-   prometheus_client and `/metrics` endpoint on the API
-   Latency histograms per route (`joy_http_request_duration_seconds`)
-   Business metrics: entries/habit checks/goals counters, sentiment
    distribution and 7-day active users pulled from ClickHouse at scrape time
-   Grafana dashboard JSON at `grafana/joy-dashboard.json`

## Planned

### v0.14.x --- Distributed Tracing (OpenTelemetry)

End-to-end request tracing across services.

-   OTel SDK and Flask/pika auto-instrumentation
-   Trace-context propagation across the event bus
-   Jaeger backend container
-   Sampled traces for slow-request endpoints
-   Docs on reading the trace UI

### v0.15.x --- Object Storage (MinIO / S3)

Binary attachment storage.

-   MinIO container with bucket bootstrap
-   Presigned-URL upload endpoint
-   Attachment metadata persisted on journal entries
-   Background cleanup for orphaned objects
-   Tests using a fake S3 client

### v0.16.x --- Voice Notes (Whisper STT)

Audio capture and transcription.

-   Whisper-based transcription service or external API client
-   New `kind: voice` journal flow with audio attachment
-   Transcription event reuses the sentiment pipeline
-   Per-voice-note cost recorded for v0.17
-   Tests with a stub transcriber

### v0.17.x --- AI Cost Tracking

Per-user accounting of every AI call.

-   AICall ledger collection (model, tokens, cost_usd, request_id, user_id)
-   Wrapper recording usage on every AI call
-   `/api/me/usage` endpoint with daily and monthly rollups
-   Budget-enforcement hooks (soft warn, hard block)
-   Tests

### v0.18.x --- PWA Frontend

Standalone Progressive Web App client.

-   New `frontend/` workspace (framework TBD: React / Svelte / Vue)
-   Auth flow against existing JWT endpoints
-   Journal compose and list views
-   Service worker for offline caching
-   App manifest and install prompt

### v0.19.x --- Kubernetes Manifests

Cloud-native deployment.

-   One Deployment + Service per microservice
-   ConfigMap and Secret externalization
-   Horizontal Pod Autoscaler on journal and AI services
-   Helm chart or kustomize overlay
-   Load test with k6 to validate scaling

### v1.0.0 --- Public Release

Hardening, polish, and launch.

-   Performance budgets verified (p50 / p95 / p99 per route)
-   Security audit pass (dependency scan, headers, secrets review)
-   Documentation freeze
-   Demo environment with seeded sample data
-   Public landing page

------------------------------------------------------------------------

# System Architecture

The platform follows a **cloud-native event-driven microservices
architecture**.

Design principles:

-   loose coupling
-   high cohesion
-   horizontal scalability
-   independent deployability
-   fault tolerance
-   asynchronous messaging

Services communicate through:

-   REST APIs
-   event messages via RabbitMQ

------------------------------------------------------------------------

# Architecture Diagram

``` mermaid
flowchart TD

Client[Client Applications]
Gateway[API Gateway]

Client --> Gateway

Gateway --> AuthService
Gateway --> UserService
Gateway --> JournalService
Gateway --> HabitService
Gateway --> GoalService

JournalService --> RabbitMQ[(RabbitMQ)]

RabbitMQ --> AIService
AIService --> InsightService
AIService --> AnalyticsService

InsightService --> MongoDB[(MongoDB)]
JournalService --> MongoDB

AnalyticsService --> ClickHouse[(ClickHouse)]

JournalService --> OpenSearch[(OpenSearch)]
Gateway --> Memcached[(Memcached)]
```

------------------------------------------------------------------------

# Microservices Overview

## API Gateway

Responsibilities:

-   unified entry point
-   request routing
-   rate limiting
-   authentication verification

## Auth Service

Handles:

-   authentication
-   JWT issuance
-   refresh tokens
-   session validation

## User Service

Handles:

-   user profiles
-   account preferences
-   profile settings

## Journal Service

Core application service responsible for:

-   creating entries
-   editing entries
-   retrieving history

Publishes events:

    journal.created

## Habit Service

Handles:

-   habit creation
-   habit tracking
-   streak calculation

## Goal Service

Handles:

-   goals
-   milestones
-   progress tracking

## AI Analysis Service

Processes journal content.

Capabilities:

-   sentiment analysis
-   emotion detection
-   topic extraction
-   embeddings generation

## Insight Service

Generates weekly behavioral insights.

Consumes:

    journal.analyzed

## Analytics Service

Processes aggregated data for dashboards.

------------------------------------------------------------------------

# Event‑Driven Messaging System

The system uses **RabbitMQ** as the event broker.

Benefits:

-   asynchronous communication
-   decoupled services
-   reliable message delivery
-   scalable background processing

Example Event Flow:

1.  Journal entry created\
2.  Event `journal.created` published\
3.  AI Service processes entry\
4.  Event `journal.analyzed` published\
5.  Insight Service generates insights

------------------------------------------------------------------------

# AI Processing Pipeline

The AI analysis pipeline contains several stages.

1 Text preprocessing\
2 Sentiment classification\
3 Emotion detection\
4 Topic extraction\
5 Behavioral insight generation

Future enhancements:

-   transformer models
-   LLM insight generation
-   semantic search embeddings

------------------------------------------------------------------------

# Database Design (MongoDB)

MongoDB is used as the **primary application database**.

Reasons:

-   flexible schema
-   natural representation of document data
-   easy schema evolution
-   nested data structures for AI outputs

Other supporting databases:

ClickHouse --- analytics\
OpenSearch --- full text search\
Memcached --- caching

------------------------------------------------------------------------

# MongoDB Schema Diagrams

``` mermaid
erDiagram

USERS {
ObjectId _id
string email
string password_hash
date created_at
bool ai_enabled
object vapid_subscription
object settings
}

JOURNALS {
ObjectId _id
ObjectId user_id
string kind
string body
date created_at
string entry_date
int mood
array tags
object ai
array attachments
bool encrypted
}

HABITS {
ObjectId _id
ObjectId user_id
string name
string frequency
date created_at
}

HABIT_LOGS {
ObjectId _id
ObjectId habit_id
ObjectId user_id
date date
bool completed
}

GOALS {
ObjectId _id
ObjectId user_id
string title
string description
date created_at
array milestones
}

AI_CALLS {
ObjectId _id
ObjectId user_id
ObjectId entry_id
string model
string kind
int input_tokens
int output_tokens
float cost_usd
date called_at
}

USERS ||--o{ JOURNALS : writes
USERS ||--o{ HABITS : owns
USERS ||--o{ GOALS : defines
HABITS ||--o{ HABIT_LOGS : logs
USERS ||--o{ AI_CALLS : generates
JOURNALS ||--o{ AI_CALLS : triggers
```

------------------------------------------------------------------------

# API Design & OpenAPI Documentation

All REST APIs will be documented using **OpenAPI specification**.

Documentation endpoint:

    /api/docs

Example API endpoints:

Create Journal Entry

    POST /api/journals

Retrieve User Journals

    GET /api/journals

Create Habit

    POST /api/habits

Retrieve Goals

    GET /api/goals

The OpenAPI specification will be maintained within the service
repositories.

Benefits:

-   standardized API documentation
-   automatic client generation
-   interactive documentation UI

------------------------------------------------------------------------

# Technology Stack

## Backend Languages

Python --- https://python.org\
Go --- https://go.dev\
Rust --- https://rust-lang.org\
Node.js --- https://nodejs.org\
.NET --- https://dotnet.microsoft.com

## Backend Frameworks

Flask --- https://flask.palletsprojects.com\
FastAPI --- https://fastapi.tiangolo.com\
Django --- https://www.djangoproject.com\
NestJS --- https://nestjs.com\
ASP.NET Core --- https://learn.microsoft.com/aspnet/core\
Axum --- https://github.com/tokio-rs/axum\
Actix --- https://actix.rs

## Frontend

React --- https://react.dev\
Next.js --- https://nextjs.org

## Databases

MongoDB --- https://mongodb.com\
ClickHouse --- https://clickhouse.com\
OpenSearch --- https://opensearch.org\
Memcached --- https://memcached.org

## Messaging

RabbitMQ --- https://rabbitmq.com

## Infrastructure

Docker --- https://docker.com\
Kubernetes --- https://kubernetes.io\
Azure Kubernetes Service ---
https://azure.microsoft.com/products/kubernetes-service

## API Documentation

OpenAPI --- https://www.openapis.org

------------------------------------------------------------------------

# Third Party Integrations

Potential integrations include:

OpenAI API --- AI insights\
OAuth Providers --- Google / GitHub authentication\
SendGrid --- transactional email\
Grafana Cloud --- hosted observability

------------------------------------------------------------------------

# Observability & Monitoring

Monitoring stack:

Prometheus --- metrics collection\
Grafana --- dashboards\
OpenTelemetry --- distributed tracing\
Jaeger --- trace visualization

Metrics monitored:

-   request latency
-   AI processing time
-   queue depth
-   service throughput
-   error rates

------------------------------------------------------------------------

# Deployment Architecture

Target deployment:

Azure Kubernetes Service

Deployment pipeline:

``` mermaid
flowchart LR

GitHub[GitHub Repo]
CI[CI Pipeline]
DockerBuild[Docker Image Build]
Registry[Container Registry]
Kubernetes[Kubernetes Cluster]

GitHub --> CI
CI --> DockerBuild
DockerBuild --> Registry
Registry --> Kubernetes
```

------------------------------------------------------------------------

# Development Workflow (Docker)

Local development uses Docker Compose.

Requirements:

-   Docker
-   Docker Compose

Start environment:

    docker compose build
    docker compose up

Stop environment:

    docker compose down

Local services include:

-   API services
-   MongoDB
-   RabbitMQ
-   Memcached
-   OpenSearch
-   ClickHouse

------------------------------------------------------------------------

# Testing Workflow

Testing layers include:

Unit Tests\
Integration Tests\
Service Tests\
End-to-End Tests

Testing executed automatically through CI pipelines.

------------------------------------------------------------------------

# Feature Backlog

Future improvements:

-   reinforcement learning habit recommendations
-   LLM coaching assistant
-   predictive mood modeling
-   semantic search with embeddings
-   advanced analytics dashboards

------------------------------------------------------------------------

# Contribution Guidelines

1 Fork repository\
2 Create feature branch\
3 Implement feature\
4 Add tests\
5 Submit pull request

Coding standards:

-   clean architecture
-   domain driven design
-   high test coverage

------------------------------------------------------------------------

# Contributors

  Name             Role
  ---------------- ------------------------------------------
  Project Author   System Architecture, Backend Engineering

------------------------------------------------------------------------

# Full Testing Analysis

Testing strategy ensures production readiness.

Unit Testing

Tools:

pytest\
Go testing\
Rust testing\
Jest\
xUnit

Integration Testing

Validates interactions between:

-   services
-   databases
-   message queues

API Testing

Ensures:

-   endpoint correctness
-   authentication validation
-   schema validation

End‑to‑End Testing

Simulates full workflows:

-   user registration
-   journal entry creation
-   AI processing
-   insight generation

Load Testing

Tools:

k6\
Locust

Future performance testing includes:

-   message queue stress testing
-   AI pipeline throughput testing

------------------------------------------------------------------------

# Extended Feature Ideas

Candidate features for future versions.

## Progressive Web App

Convert the frontend into an installable PWA:

-   offline-first reads of past entries via service worker cache
-   queued writes synced on reconnect via IndexedDB and Background Sync API
-   web push notifications for weekly reviews and morning prompts
-   installable on iOS and Android home screens

## Voice Notes

Audio journal entries via in-browser recording:

-   capture via MediaRecorder API
-   audio stored in S3-compatible object storage
-   asynchronous transcription via Whisper (self-hosted or OpenAI Whisper API)
-   transcript stored alongside the original audio file on the entry

## Object Storage

S3-compatible storage for binary assets:

-   voice note audio files
-   photo attachments with server-side thumbnail generation
-   presigned URLs with short TTL for secure client access

## Concrete AI Feature Set

Specific AI-powered product features:

-   **Per-entry tagging** — async extraction of emotion labels, named entities, and a one-line summary
-   **Weekly review** — scheduled Sunday summary highlighting wins, recurring themes, and low-mood days
-   **Morning prompts** — one daily reflection prompt informed by recent entry themes
-   **CBT reframing** — opt-in alternative perspectives for high-anxiety entries (with explicit "not therapy" disclaimer)

## AI Cost Tracking

Observability for Anthropic API usage:

-   record model, input tokens, output tokens, and USD cost per call
-   surface monthly totals per user in the settings UI
-   configurable daily cost cap that pauses the AI worker when exceeded

## Performance Budgets

Target SLOs for production readiness:

-   entry create p95 < 200 ms
-   entry list (50 items) p95 < 300 ms
-   AI tagging worker p95 < 30 s end-to-end
-   frontend bundle main chunk < 200 KB gzipped
-   mobile time-to-interactive < 2 s on a mid-tier device over 4G

------------------------------------------------------------------------

# License

AGPL-3.0 license
