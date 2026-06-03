# Joy --- AI Manifestation Journal Platform

![version](https://img.shields.io/badge/version-v0.1.0-alpha-orange)
![status](https://img.shields.io/badge/status-proof_of_concept-lightgrey)

------------------------------------------------------------------------

# Table of Contents

1.  General Description\
2.  Project Goals\
3.  Project Status\
4.  System Architecture\
5.  Architecture Diagram\
6.  Microservices Overview\
7.  Event-Driven Messaging System\
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

### Project Evolution

This repository will evolve over time.

Future branches will introduce additional technologies:

-   `main-python` → Python implementations (Flask, FastAPI, Django)
-   `main-go` → Go services
-   `main-rust` → Rust services
-   `main-nestjs` → Node.js/NestJS services
-   `main-dotnet` → .NET services

Each branch will represent **the same platform implemented with
different backend frameworks and languages**, gradually evolving from this initial proof-of-concept.

------------------------------------------------------------------------

# Project Goals

For the **v0.0.1 alpha**, the goals are simple:

-   validate the journaling workflow
-   validate API structure
-   test simple sentiment analysis experiments
-   create a minimal API foundation

Later versions will expand toward:

-   distributed services with a message broker
-   AI pipelines
-   cloud-native infrastructure

------------------------------------------------------------------------

# Project Status

Project Name:

Joy --- AI Manifestation Journal Platform

Version:

v0.1.0

Stage:

Alpha / Proof of Concept

Implementation:

Single Flask API

Storage:

Local JSON files

------------------------------------------------------------------------

# System Architecture

The first alpha version uses a **very simple architecture**.

It consists of:

-   one Flask API server
-   JSON file storage
-   minimal REST endpoints

No microservices are used yet.

------------------------------------------------------------------------

# Architecture Diagram

``` mermaid
flowchart TD

Client[Client / Browser]
FlaskAPI[Flask API]
JSONDB[Local JSON Files]

Client --> FlaskAPI
FlaskAPI --> JSONDB
```

------------------------------------------------------------------------

# Microservices Overview

In **v0.0.1**, final architecture is **not implemented**.

Instead, the system runs as a **single monolithic Flask service**.

Future versions will split this service into:

-   Auth Service
-   Journal Service
-   Habit Service
-   AI Analysis Service

------------------------------------------------------------------------

# Event-Driven Messaging System

This version **does not include messaging infrastructure**.

Future versions may introduce:

-   RabbitMQ

For asynchronous AI processing.

------------------------------------------------------------------------

# AI Processing Pipeline

In this first alpha version, AI is **not implemented**.

Possible experiments include:

-   simple sentiment scoring
-   keyword detection

Future versions will introduce:

-   NLP pipelines
-   transformer models
-   AI-generated insights

------------------------------------------------------------------------

# Database Design (MongoDB)

MongoDB is **not used in v0.0.1**.

Instead the system stores data using:

-   JSON files
-   simple dictionaries

Example storage files:

    data/users.json
    data/journals.json

MongoDB will be introduced in later versions.

------------------------------------------------------------------------

# MongoDB Schema Diagrams

For now the schema is conceptual only.

``` mermaid
erDiagram

USERS {
ObjectId _id
string email
string password_hash
date created_at
bool ai_enabled
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

USERS ||--o{ JOURNALS : writes
```

These schemas will later map to MongoDB collections.

------------------------------------------------------------------------

# API Design & OpenAPI Documentation

The API follows REST conventions.

Example endpoints:

Create Journal Entry

    POST /journals

List Entries

    GET /journals

Get Entry

    GET /journals/{id}

Future versions will include **OpenAPI documentation**.

OpenAPI specification will be available at:

    /api/docs

------------------------------------------------------------------------

# Technology Stack

This version intentionally uses the minimal neccesary tech stack, consisting only of Flask.

## Backend

Python\
https://python.org

Flask\
https://flask.palletsprojects.com

## Data Storage

Local JSON files

## API Format

REST API with JSON responses

------------------------------------------------------------------------

# Third Party Integrations

None in v0.0.1.

Future versions may integrate:

-   OpenAI API
-   OAuth providers
-   email services

------------------------------------------------------------------------

# Observability & Monitoring

Not implemented yet.

Future versions may introduce:

-   Prometheus
-   Grafana
-   OpenTelemetry

------------------------------------------------------------------------

# Deployment Architecture

For now the project runs locally.

Run the Flask server:

    python app.py

Future versions will support:

-   Docker containers
-   Kubernetes deployments

------------------------------------------------------------------------

# Development Workflow (Docker)

Docker is **not required in v0.0.1**.

Future versions will introduce Docker-based development environments.

------------------------------------------------------------------------

# Testing Workflow

Basic testing may include:

-   simple unit tests
-   endpoint tests

Future versions will include:

-   integration tests
-   end-to-end tests
-   load testing

------------------------------------------------------------------------

# Feature Backlog

Planned next steps:

-   add authentication
-   introduce sentiment analysis
-   add habit tracking
-   migrate storage to MongoDB
-   introduce message queues
-   split services into microservices

------------------------------------------------------------------------

# Contribution Guidelines

1.  Fork the repository
2.  Create a feature branch
3.  Implement changes
4.  Open a pull request

------------------------------------------------------------------------

# Contributors

  Name             Commit
  ---------------- ---------------------
  None             None

------------------------------------------------------------------------

# Full Testing Analysis

Testing is minimal for this first alpha version.

Initial tests focus on:

-   endpoint validation
-   JSON storage operations

Future versions will include:

-   unit testing
-   integration testing
-   system testing
-   load testing

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
