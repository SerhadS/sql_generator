# SQL Generation Agent using FalkorDB Knowledge Graph and LLMs

This project provides an intelligent SQL generation agent that converts natural language queries into SQL by leveraging a knowledge graph stored in FalkorDB and Large Language Models (LLMs) for semantic understanding. The knowledge graph represents the database schema with tables and columns as nodes, and relationships (HAS_COLUMN, REFERS_TO) as edges.

## Overview

The system works in four main steps:
1. **Schema Retrieval**: Queries the knowledge graph using CYPHER to get all available tables and columns
2. **Semantic Table Matching**: Uses LLMs to understand the query intent and identify relevant tables
3. **Column Selection**: Uses LLMs to select relevant columns needed for the query
4. **SQL Generation**: Uses LLMs to generate SQL queries with proper JOINs, WHERE clauses, and aggregations

## Architecture

### Knowledge Graph Structure

- **Nodes**:
  - `Table`: Represents database tables with properties `name` and `description`
  - `Column`: Represents table columns with properties `name`, `type`, and `description`

- **Relationships**:
  - `HAS_COLUMN`: Links tables to their columns (Table → Column)
  - `REFERS_TO`: Represents foreign key relationships (Column → Column)

### Components

1. **`extract_schema.py`**: Extracts schema information from SQLite database and creates `schema.json`
2. **`create_knowledge_graph.py`**: Populates FalkorDB with the schema graph
3. **`sql_agent.py`**: Main agent that generates SQL from natural language queries
4. **`example_usage.py`**: Example script demonstrating usage

## Setup

### Prerequisites

- Python 3.13+ (Not a must)
- FalkorDB running on localhost:6379
- SQLite database with schema
- Ollama running locally (default: `http://localhost:11434`)

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Ensure FalkorDB is running

3. Ensure Ollama is running and a model is available:
```bash
ollama serve
ollama pull YOUR_PREFERRED_MODEL
```

4. Create mock data:
```bash

python src/gen_data.py
```

5. Extract schema from your SQLite database:
```bash

python src/extract_schema.py
```

6. Create Knowledge Graph:
```bash

python src/create_knowledge_graph.py
```

7. (Optional) Configure environment variables:
```bash
# Copy the example environment file
cp env.example .env

# Edit .env to customize data generation parameters
# See env.example for all available options
```


## Usage

### Basic Usage

```python
from src.sql_agent import SQLGenerationAgent
import os

# Optional: set Ollama host if not default
# os.environ['OLLAMA_HOST'] = 'http://localhost:11434'

# Initialize the agent
agent = SQLGenerationAgent(
    llm_provider='ollama',   # Use 'ollama' or None to disable LLM
    model='YOURMODEL'      # Any Ollama model you have pulled
)

# Generate SQL from natural language
query = "Count the number of customers transacted in last 3 days"
sql = agent.generate_sql(query)
print(sql)
```

### Example Queries

The agent can handle various types of queries:

- **Counting queries**: "Count the number of customers transacted by their credit cards in last 3 days above 100 dollars"
- **Selection queries**: "Show all clients with their account balances where the balance is above 5000 dollars and age is above 30"
- **Time-based queries**: "Find transactions from the last week where the amount is greater than 1000 dollars and the customer is from New York"
- **Filtering queries**: "List all businesses in California which do not have any relation to our credit card customers"
- **Tricky query (Gemma:12b failed)**:List top 2 customers by total credit card transaction amount for each day in last 30 days

### Running Examples

```bash
# Run multiple examples
python src/example_usage.py
```

## How It Works

### 1. Schema Retrieval

The agent first retrieves all tables and their descriptions from the knowledge graph using CYPHER:

```cypher
MATCH (t:Table)
RETURN t.name AS name, t.description AS description
```

### 2. LLM-Based Table Matching

The LLM analyzes the natural language query and semantically matches it to relevant tables. The LLM receives:
- The user's query
- All available tables with their descriptions
- Returns a ranked list of relevant table names

This approach is much more powerful than keyword matching because it understands:
- Synonyms (e.g., "customer" vs "client")
- Context and intent
- Implicit relationships

### 3. Column Selection

For each relevant table, the LLM selects which columns are needed by analyzing:
- The query requirements
- Column names, types, and descriptions
- Whether columns are needed for selection, filtering, joining, or aggregation

### 4. Relationship Discovery

Uses CYPHER to find foreign key relationships between selected tables:

```cypher
MATCH (t1:Table)-[:HAS_COLUMN]->(c1:Column)-[:REFERS_TO]->(c2:Column)<-[:HAS_COLUMN]-(t2:Table)
WHERE t1.name = 'casa_transactions' AND t2.name = 'casa_accounts'
RETURN t1.name AS from_table, c1.name AS from_column,
       t2.name AS to_table, c2.name AS to_column
```

### 5. LLM-Based SQL Generation

The LLM generates the final SQL query using:
- The original query
- Selected tables with their columns
- Relationship information for JOINs
- Query understanding for proper aggregation, filtering, and time constraints