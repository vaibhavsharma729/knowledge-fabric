"""
prompt_builder.py

Builds a RAG prompt by combining a user query with context retrieved from:
  - Amazon OpenSearch Serverless  (vector search via Bedrock embeddings)
  - Amazon Neptune                (graph traversal via openCypher / Gremlin)

Dependencies:
    pip install boto3 opensearch-py gremlinpython requests-aws4auth
"""

import json
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from gremlin_python.driver import client as gremlin_client
from gremlin_python.driver import serializer


# ---------------------------------------------------------------------------
# Configuration  (replace with your actual values or load from env/SSM)
# ---------------------------------------------------------------------------
REGION = "us-east-1"
BEDROCK_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"

OPENSEARCH_HOST = "your-opensearch-domain.us-east-1.aoss.amazonaws.com"
OPENSEARCH_INDEX = "knowledge-base-index"
OPENSEARCH_VECTOR_FIELD = "embedding"
OPENSEARCH_TEXT_FIELD = "text"
TOP_K = 5  # number of semantic hits to retrieve

NEPTUNE_ENDPOINT = "your-neptune-cluster.cluster-xxxx.us-east-1.neptune.amazonaws.com"
NEPTUNE_PORT = 8182
# ---------------------------------------------------------------------------


def get_bedrock_embedding(text: str) -> list[float]:
    """Embed *text* using Amazon Bedrock Titan Embeddings v2."""
    bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    body = json.dumps({"inputText": text})
    response = bedrock.invoke_model(
        modelId=BEDROCK_EMBEDDING_MODEL_ID,
        body=body,
        accept="application/json",
        contentType="application/json",
    )
    return json.loads(response["body"].read())["embedding"]


# ---------------------------------------------------------------------------
# OpenSearch context retrieval
# ---------------------------------------------------------------------------

def _build_opensearch_client() -> OpenSearch:
    credentials = boto3.Session().get_credentials()
    awsauth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        REGION,
        "aoss",
        session_token=credentials.token,
    )
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )


def retrieve_opensearch_context(query: str, top_k: int = TOP_K) -> list[str]:
    """
    Embed *query* with Bedrock, then run a k-NN vector search against
    OpenSearch and return the top-k matching text chunks.
    """
    query_embedding = get_bedrock_embedding(query)

    os_client = _build_opensearch_client()
    knn_query = {
        "size": top_k,
        "_source": [OPENSEARCH_TEXT_FIELD],
        "query": {
            "knn": {
                OPENSEARCH_VECTOR_FIELD: {
                    "vector": query_embedding,
                    "k": top_k,
                }
            }
        },
    }

    response = os_client.search(index=OPENSEARCH_INDEX, body=knn_query)
    hits = response["hits"]["hits"]
    return [hit["_source"][OPENSEARCH_TEXT_FIELD] for hit in hits]


# ---------------------------------------------------------------------------
# Neptune context retrieval
# ---------------------------------------------------------------------------

def retrieve_neptune_context(query_entity: str) -> list[str]:
    """
    Run an openCypher/Gremlin query on Neptune to retrieve graph facts
    related to *query_entity* (e.g. a named entity extracted from the user
    query).

    Returns a list of human-readable relationship strings.
    """
    gremlin_url = f"wss://{NEPTUNE_ENDPOINT}:{NEPTUNE_PORT}/gremlin"

    gc = gremlin_client.Client(
        gremlin_url,
        "g",
        message_serializer=serializer.GraphSONSerializersV2d0(),
    )

    # Example: find the entity node and its direct neighbours (1-hop)
    gremlin_query = (
        f"g.V().has('name', '{query_entity}')"
        ".as('src')"
        ".bothE()"
        ".as('edge')"
        ".otherV()"
        ".as('neighbour')"
        ".select('src', 'edge', 'neighbour')"
        ".by('name')"
        ".by(label)"
        ".by('name')"
        ".limit(20)"
        ".toList()"
    )

    results = gc.submit(gremlin_query).all().result()
    gc.close()

    facts = []
    for row in results:
        src = row.get("src", "?")
        edge = row.get("edge", "?")
        neighbour = row.get("neighbour", "?")
        facts.append(f"{src} --[{edge}]--> {neighbour}")

    return facts


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """\
You are a knowledgeable assistant. Use the context below to answer the question.
If the context does not contain enough information, say so rather than guessing.

### Context from Knowledge Base (semantic search)
{opensearch_context}

### Context from Knowledge Graph (Neptune)
{neptune_context}

### User Question
{user_query}

### Answer
"""


def build_prompt(
    user_query: str,
    graph_entity: str | None = None,
) -> str:
    """
    Retrieve context from OpenSearch and Neptune, then assemble a RAG prompt.

    Args:
        user_query:    The raw question from the user.
        graph_entity:  An entity name to look up in Neptune (e.g. extracted
                       via NER).  If None, the Neptune section will be empty.

    Returns:
        A fully-formed prompt string ready to send to a Bedrock LLM.
    """
    # --- OpenSearch semantic context ---
    os_chunks = retrieve_opensearch_context(user_query)
    if os_chunks:
        os_section = "\n\n".join(
            f"[Chunk {i + 1}]\n{chunk}" for i, chunk in enumerate(os_chunks)
        )
    else:
        os_section = "No relevant documents found."

    # --- Neptune graph context ---
    if graph_entity:
        neptune_facts = retrieve_neptune_context(graph_entity)
        neptune_section = (
            "\n".join(neptune_facts) if neptune_facts else "No graph facts found."
        )
    else:
        neptune_section = "No graph entity provided."

    return PROMPT_TEMPLATE.format(
        opensearch_context=os_section,
        neptune_context=neptune_section,
        user_query=user_query,
    )


# ---------------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    user_query = "What are the key financial risks for TechStashNova Inc.?"
    graph_entity = "TechStashNova Inc."

    prompt = build_prompt(user_query=user_query, graph_entity=graph_entity)
    print(prompt)

    # Optionally invoke a Bedrock LLM with the assembled prompt:
    #
    # bedrock = boto3.client("bedrock-runtime", region_name=REGION)
    # response = bedrock.invoke_model(
    #     modelId="anthropic.claude-sonnet-4-6",
    #     body=json.dumps({"prompt": prompt, "max_tokens": 1024}),
    #     accept="application/json",
    #     contentType="application/json",
    # )
    # print(json.loads(response["body"].read())["completion"])
