# Architecture Review: Knowledge Graph System

**Date:** 2026-02-20
**Branch:** `claude/review-knowledge-graph-architecture-37fyq`
**Scope:** draw.io architecture diagram submitted for review against knowledge graph requirements and existing codebase.

---

## 1. Architecture Summary (Diagram Decoded)

The diagram depicts an AWS-hosted knowledge graph + RAG system with the following layers:

| Layer | Services |
|---|---|
| **Presentation** | Amazon CloudFront, AWS S3 (static web) |
| **Compute** | AWS Lambda (×3: ingestion, embedding orchestration, RAG) |
| **AI / ML** | AWS Bedrock (Titan Embeddings + Anthropic Claude), AWS Textract, AWS Comprehend |
| **Storage** | AWS S3 (documents), Amazon DynamoDB (conversation history), Amazon OpenSearch (vector DB), Amazon Neptune (graph DB) |
| **Security** | AWS Secrets Manager, VPC, IAM (implied) |
| **Observability** | Amazon CloudWatch |

### Numbered flow steps from the diagram

| Step | Description |
|---|---|
| 1a | User uploads documents → S3 + Lambda (data ingestion) |
| 1b | Lambda triggers transformation workflow: Textract → Comprehend → Lambda → Bedrock Titan Embeddings → OpenSearch |
| 1c | Step Functions workflow stores embeddings back to OpenSearch |
| 2 | User query → CloudFront (Q/R path) |
| 3 | CloudFront → RAG Lambda (query execution) |
| 4 | Lambda → OpenSearch (vector similarity search → relevant context) |
| 5 | Lambda reads conversation history from DynamoDB |
| 6 | Response back from DynamoDB |
| 7 | Prompt = Query + Relevant Context sent to Bedrock Claude |
| 8 | Claude response returned → CloudFront → User |

---

## 2. Strengths

- **Separation of ingestion and query paths** — clean split between the 1x and 2–8 flows.
- **Managed AI services** — Textract (OCR), Comprehend (NLP/NER), Bedrock (embeddings + LLM) reduce undifferentiated heavy lifting.
- **VPC isolation** — compute and storage inside VPC reduces attack surface.
- **Conversation history** — DynamoDB for multi-turn context is appropriate; DynamoDB handles high-frequency reads well.
- **Observability present** — CloudWatch and Secrets Manager included; security hygiene is considered.
- **Titan Embeddings** — consistent with the existing `ActionLambda.py` / Bedrock Knowledge Base setup already in the codebase.

---

## 3. Critical Issues

### 3.1 Amazon Neptune is Orphaned — Biggest Gap

Neptune (graph database) is drawn inside the VPC but has **no connections** to either the ingestion pipeline or the query path. This is the central issue for a knowledge graph architecture.

**What should happen:**

During **ingestion**, Comprehend extracts entities and relationships. These must be written to Neptune as nodes and edges:
```
Comprehend (entities + relations) ──→ Lambda ──→ Neptune (Gremlin/SPARQL write)
```

During **query**, the RAG Lambda must traverse Neptune alongside querying OpenSearch:
```
Query ──→ Lambda ──→ OpenSearch (vector similarity)
                 └──→ Neptune (graph traversal for related entities)
                 └──→ DynamoDB (conversation history)
                 └──→ Merge context ──→ Bedrock Claude
```

Without these connections, Neptune is decorative. The system is a vector-only RAG pipeline, not a knowledge graph.

**Fix:** Add Neptune write connections from the Comprehend-to-Lambda step, and Neptune read connections from the RAG Lambda. Use a hybrid retrieval strategy: vector similarity (OpenSearch) + graph traversal (Neptune) combined before sending to Claude.

---

### 3.2 No API Gateway

CloudFront currently routes directly to Lambda (based on diagram flow 2→3). Lambda functions should not be invoked directly from a CDN.

**Fix:** Insert Amazon API Gateway (HTTP API or REST API) between CloudFront and the RAG Lambda:
```
CloudFront ──→ API Gateway ──→ RAG Lambda
```

API Gateway provides: throttling, authorization (Cognito JWT), request validation, CORS handling, and WAF integration points.

---

### 3.3 No Authentication / Authorization

No Amazon Cognito or equivalent identity service is shown. The `/companyResearch`, `/createPortfolio` action endpoints and the knowledge graph itself need user-level access control.

**Fix:** Add Amazon Cognito User Pool + Identity Pool. Integrate with CloudFront (signed URLs or Cognito-protected origin) and API Gateway (JWT authorizer).

---

### 3.4 Ingestion Trigger is Undefined

Step 1a shows users uploading to S3 and Lambda being involved, but the trigger mechanism is not shown. A direct S3→Lambda invocation works but is fragile at scale and provides no retry/DLQ path for the ingestion step itself.

**Fix:** Add an S3 Event Notification → SQS queue → Lambda trigger. This pattern already exists in the codebase (`ActionCallDLQ` SQS queue in `2-bedrock-agent-lambda-template.yaml`) and should be applied to the ingestion Lambda as well.

```
S3 (PutObject event) ──→ SQS ──→ Ingestion Lambda ──→ Step Functions
```

---

### 3.5 Step Functions Shown as Container but Not as a Service

The "Data Transformation and Embedding Workflow" group uses the Step Functions visual style, but no explicit AWS Step Functions state machine icon or orchestration logic is shown. The current flow relies on sequential Lambda calls, which loses Step Functions' retry logic, parallel branching, and wait-for-callback support.

**Fix:** Make Step Functions explicit with a state machine icon. Define states for:
- Text extraction (Textract) — with retry on `ThrottlingException`
- Entity extraction (Comprehend) — parallel branch to OpenSearch + Neptune
- Embedding generation (Bedrock Titan) — with output to OpenSearch

---

### 3.6 DynamoDB Conversation History Not Connected to Prompt Construction

DynamoDB has a step-5 marker indicating it feeds conversation history, but there is no arrow from DynamoDB to the prompt assembly step (step 7: Prompt = Query + Relevant Context). The diagram implies but does not show the history being merged.

**Fix:** Draw an explicit arrow from DynamoDB to the prompt assembly node, and update the label to:
```
Prompt = Query + Relevant Context (OpenSearch) + Graph Context (Neptune) + Conversation History (DynamoDB)
```

---

### 3.7 Lambda Memory and Timeout Not Addressed

The RAG Lambda handles: DynamoDB read, OpenSearch query, Neptune traversal, Bedrock invocation, and response formatting. This is too much responsibility for a single Lambda and will hit the 15-minute timeout for large graph traversals.

**Fix (option A):** Split into purpose-specific Lambdas coordinated by Step Functions or an API composition layer.
**Fix (option B):** If keeping monolithic, set minimum 3008 MB memory and use Bedrock streaming responses to reduce perceived latency.

---

## 4. Moderate Issues

### 4.1 CloudFront Origin Configuration Incomplete

Two S3 buckets exist: one for documents, one for static web pages. CloudFront likely serves only the static web pages S3 origin, but the diagram does not distinguish which S3 is the CloudFront origin vs. the document store. This will cause confusion when implementing Origin Access Control (OAC).

### 4.2 No VPC Endpoints Shown

OpenSearch, DynamoDB, S3, Bedrock, Secrets Manager, and Neptune are accessed from within the VPC, but no VPC Interface Endpoints or Gateway Endpoints are shown. Without them, traffic exits the VPC to public AWS endpoints, adding latency and potential data exfiltration risk.

Minimum endpoints needed:
- `com.amazonaws.<region>.s3` (Gateway)
- `com.amazonaws.<region>.dynamodb` (Gateway)
- `com.amazonaws.<region>.bedrock-runtime` (Interface)
- `com.amazonaws.<region>.secretsmanager` (Interface)
- `com.amazonaws.<region>.execute-api` (Interface, for API Gateway)

### 4.3 Neptune Not Inside a Subnet Group

Neptune requires a DB subnet group (minimum 2 AZs for a cluster). The VPC shows a single subnet. Multi-AZ Neptune requires the diagram to show at least 2 private subnets across 2 AZs.

### 4.4 OpenSearch Access Control Undefined

OpenSearch Service (formerly Elasticsearch) requires either fine-grained access control (FGAC) with IAM auth or VPC-based access. The diagram does not show how Lambda authenticates to OpenSearch. Given Lambda is in the same VPC, VPC-based access with IAM signing (AWS SigV4) is the correct pattern, but this must be explicit.

### 4.5 Secrets Manager Usage is Unspecified

Secrets Manager is present but it's unclear what secrets it stores: Neptune credentials? OpenSearch master password? Bedrock API keys (not needed — Bedrock uses IAM)? Document what each secret corresponds to.

---

## 5. Alignment with Existing Codebase

The existing codebase (`ActionLambda.py`, `invoke_agent.py`, CFN templates) uses **AWS Bedrock Agents + Bedrock Knowledge Base** (managed), not the custom RAG pipeline shown in the diagram. These are different paradigms:

| Aspect | Existing Codebase | Proposed Diagram |
|---|---|---|
| Orchestration | Bedrock Agents | Custom Lambda RAG |
| Knowledge store | Bedrock Knowledge Base (managed) | Custom OpenSearch + Neptune |
| Embedding | Titan Embeddings (managed by Bedrock KB) | Explicit Titan Embeddings Lambda |
| Entity extraction | Not present | Textract + Comprehend |
| Graph DB | Not present | Neptune |
| Frontend | Streamlit on EC2 | Static web (S3 + CloudFront) |

**Recommendation:** Decide on one architecture pattern:

- **Option A — Extend Bedrock Agents:** Add Neptune as an action group tool. The agent calls a `graphSearch(query)` action that traverses Neptune for relationship context and a `vectorSearch(query)` action for semantic similarity. Minimal rebuild from current code.
- **Option B — Custom RAG Pipeline (as diagrammed):** Rebuild from scratch with the custom pipeline shown. Requires implementing all components shown in the diagram. Higher complexity but more control.

Option A is the lower-risk path given the existing codebase investment.

---

## 6. Missing Services for a Production Knowledge Graph

| Missing Service | Why Needed |
|---|---|
| **Amazon Cognito** | User authentication and JWT issuance for API Gateway |
| **Amazon API Gateway** | Secure entry point between CloudFront and Lambda |
| **AWS WAF** | Protect CloudFront and API Gateway from injection attacks |
| **SQS (ingestion queue)** | Resilient document ingestion trigger |
| **VPC Endpoints** | Keep traffic within AWS network |
| **Neptune Subnet Group (multi-AZ)** | High availability for graph DB |
| **AWS X-Ray** | Distributed tracing across Lambda → OpenSearch → Neptune → Bedrock |

---

## 7. Summary Scorecard

| Category | Rating | Notes |
|---|---|---|
| **Service selection** | Good | Right tools for the job; Neptune inclusion is appropriate |
| **Neptune integration** | Poor | Orphaned — not connected to ingestion or query path |
| **Security** | Fair | VPC + Secrets Manager present; no Cognito, API GW, or WAF |
| **Resilience** | Fair | No SQS ingestion queue; no multi-AZ subnet shown |
| **Observability** | Fair | CloudWatch present; X-Ray missing |
| **Knowledge graph completeness** | Poor | No entity/relationship ingestion to Neptune; no graph traversal in query |
| **Codebase alignment** | Poor | Diagram architecture doesn't match existing Bedrock Agents implementation |

---

## 8. Recommended Action Items (Priority Order)

1. **[Critical]** Connect Neptune to ingestion: Comprehend entities/relations → Lambda → Neptune write (Gremlin `addV` / `addE`)
2. **[Critical]** Connect Neptune to query: RAG Lambda reads Neptune for graph traversal context
3. **[Critical]** Add API Gateway between CloudFront and Lambda
4. **[High]** Add Amazon Cognito for user auth + API Gateway JWT authorizer
5. **[High]** Add SQS between S3 events and ingestion Lambda
6. **[High]** Add VPC endpoints for all AWS service calls within VPC
7. **[High]** Make Step Functions state machine explicit in diagram
8. **[Medium]** Clarify CloudFront origins (static S3 vs. API Gateway)
9. **[Medium]** Add multi-AZ private subnets for Neptune cluster
10. **[Medium]** Add AWS X-Ray for distributed tracing
11. **[Medium]** Align diagram architecture with existing Bedrock Agents codebase or document migration plan
12. **[Low]** Document what each Secrets Manager secret stores
