from falkordb import FalkorDB
import re
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
import json
import os
import urllib.request
import urllib.error

DEFAULT_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


class SQLGenerationAgent:
    """Agent that generates SQL queries from natural language using knowledge graph and LLMs."""

    def __init__(
        self,
        falkor_host="localhost",
        falkor_port=6379,
        graph_name="schema_graph",
        llm_provider="ollama",
        model="gemma3:12b",
        ollama_host: Optional[str] = None,
    ):
        """
        Initialize the SQL generation agent.

        Args:
            falkor_host: Host for FalkorDB connection
            falkor_port: Port for FalkorDB connection
            graph_name: Name of the graph in FalkorDB
            llm_provider: LLM provider to use ('ollama' or None to disable)
            model: Ollama model name to use (e.g., 'llama3.1:8b', 'qwen2.5:7b', etc.)
            ollama_host: Ollama base URL (defaults to env OLLAMA_HOST or http://localhost:11434)
        """
        self.db = FalkorDB(host=falkor_host, port=falkor_port)
        self.graph = self.db.select_graph(graph_name)

        # Initialize LLM client
        self.llm_provider = llm_provider
        self.model = model
        self.ollama_host = (ollama_host or DEFAULT_OLLAMA_HOST).rstrip("/")
        if llm_provider not in (None, "ollama"):
            raise ValueError("Unsupported llm_provider. Use 'ollama' or None.")

        # Cache for schema information
        self._schema_cache = None

    def _ollama_chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: int = 512,
    ) -> str:
        """
        Call Ollama's chat endpoint and return assistant content.
        Requires Ollama running locally (default: http://localhost:11434).
        """
        url = f"{self.ollama_host}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                # Ollama uses num_predict for max tokens
                "num_predict": max_tokens,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Failed to call Ollama at {url}. Is Ollama running? "
                f"Set OLLAMA_HOST or pass ollama_host. Error: {e}"
            ) from e

        obj = json.loads(body)
        msg = obj.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, str):
            raise RuntimeError(f"Unexpected Ollama response shape: {obj}")
        return content

    @staticmethod
    def _extract_json_array(text: str) -> List[str]:
        """
        Extract a JSON array from model output. Accepts raw JSON or JSON inside markdown fences.
        """
        t = text.strip()
        # Remove markdown fences if any
        if t.startswith("```"):
            t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
            t = re.sub(r"\n?```$", "", t).strip()
        # Try direct parse first
        try:
            obj = json.loads(t)
            if isinstance(obj, list):
                return obj
        except Exception:
            pass
        # Heuristic: slice from first '[' to last ']'
        start = t.find("[")
        end = t.rfind("]")
        if start != -1 and end != -1 and end > start:
            snippet = t[start : end + 1]
            obj = json.loads(snippet)
            if isinstance(obj, list):
                return obj
        raise ValueError(f"Could not parse JSON array from LLM output: {text!r}")

    def _get_all_tables(self) -> List[Dict]:
        """
        Get all tables from the knowledge graph with their descriptions.

        Returns:
            List of table dictionaries with name and description
        """
        if self._schema_cache is not None:
            return self._schema_cache.get("tables", [])

        cypher_query = """
        MATCH (t:Table)
        RETURN t.name AS name, t.description AS description
        ORDER BY t.name
        """
        try:
            result = self.graph.query(cypher_query)
            tables = []
            for row in result.result_set:
                tables.append({"name": row[0], "description": row[1] or ""})

            # Cache the result
            if self._schema_cache is None:
                self._schema_cache = {}
            self._schema_cache["tables"] = tables
            return tables
        except Exception as e:
            print(f"Error getting tables: {e}")
            return []

    def _get_table_with_columns(self, table_name: str) -> Optional[Dict]:
        """
        Get a table with all its columns from the knowledge graph.

        Args:
            table_name: Name of the table

        Returns:
            Dictionary with table info and columns, or None if not found
        """
        cypher_query = f"""
        MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
        WHERE t.name = '{table_name}'
        RETURN t.name AS table_name, t.description AS table_description,
               collect({{name: c.name, type: c.type, description: c.description}}) AS columns
        """
        try:
            result = self.graph.query(cypher_query)
            if result.result_set:
                row = result.result_set[0]
                return {"name": row[0], "description": row[1] or "", "columns": row[2]}
        except Exception as e:
            print(f"Error getting table '{table_name}': {e}")
        return None

    def _get_all_tables_with_columns(self) -> List[Dict]:
        """
        Get all tables with their columns from the knowledge graph.

        Returns:
            List of table dictionaries with columns
        """
        tables = self._get_all_tables()
        tables_with_columns = []
        for table in tables:
            table_info = self._get_table_with_columns(table["name"])
            if table_info:
                tables_with_columns.append(table_info)
        return tables_with_columns

    def _llm_find_relevant_tables(
        self, query: str, all_tables: List[Dict]
    ) -> List[str]:
        """
        Use LLM to semantically match the query to relevant tables.

        Args:
            query: Natural language query
            all_tables: List of all available tables with descriptions

        Returns:
            List of relevant table names
        """

        # Build prompt for LLM
        tables_info = "\n".join(
            [f"- {t['name']}: {t['description']}" for t in all_tables]
        )

        prompt = f"""You are a database expert. Given a user query and a list of available database tables, 
identify which tables are relevant to answer the query.

User Query: "{query}"

Available Tables:
{tables_info}

Return ONLY a JSON array of table names that are relevant to answer this query. 
Order them by relevance (most relevant first).
Example: ["table1", "table2", "table3"]

JSON array:"""

        try:
            result = self._ollama_chat(
                [
                    {
                        "role": "system",
                        "content": "You are a helpful database assistant. Return only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=256,
            )
            table_names = self._extract_json_array(result)
            return [t for t in table_names if isinstance(t, str)]
        except Exception as e:
            print(f"Error in LLM table matching (ollama): {e}")

        return []

    def _llm_select_columns(self, query: str, table_info: Dict) -> List[str]:
        """
        Use LLM to select relevant columns from a table for the query.

        Args:
            query: Natural language query
            table_info: Table dictionary with columns

        Returns:
            List of relevant column names
        """

        columns_info = "\n".join(
            [
                f"- {col['name']} ({col['type']}): {col.get('description', '')}"
                for col in table_info.get("columns", [])
            ]
        )

        prompt = f"""You are a database expert. Given a user query and a database table with its columns, 
identify which columns are needed to answer the query.

User Query: "{query}"

Table: {table_info['name']}
Description: {table_info['description']}

Columns:
{columns_info}

Return ONLY a JSON array of column names that are needed for this query.
Include columns needed for:
- Selection (what to return)
- Filtering (WHERE conditions)
- Joining (foreign keys)
- Aggregation (if counting/summing)

Example: ["column1", "column2", "column3"]

JSON array:"""

        try:
            result = self._ollama_chat(
                [
                    {
                        "role": "system",
                        "content": "You are a helpful database assistant. Return only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=256,
            )
            column_names = self._extract_json_array(result)
            return [c for c in column_names if isinstance(c, str)]
        except Exception as e:
            print(f"Error in LLM column selection (ollama): {e}")

        return []

    def _llm_generate_sql(
        self, query: str, relevant_tables: List[Dict], relationships: List[Dict]
    ) -> Optional[str]:
        """
        Use LLM to generate SQL query from the query and schema information.

        Args:
            query: Natural language query
            relevant_tables: List of relevant table dictionaries with columns
            relationships: List of relationship dictionaries for JOINs

        Returns:
            Generated SQL query string or None
        """

        # Build schema information for LLM
        schema_info = []
        for table in relevant_tables:
            columns_str = ", ".join(
                [f"{col['name']} ({col['type']})" for col in table.get("columns", [])]
            )
            schema_info.append(
                f"Table: {table['name']}\n"
                f"Description: {table['description']}\n"
                f"Columns: {columns_str}\n"
            )

        relationships_str = ""
        if relationships:
            relationships_str = "\nRelationships (for JOINs):\n"
            for rel in relationships:
                relationships_str += (
                    f"- {rel['from_table']}.{rel['from_column']} -> "
                    f"{rel['to_table']}.{rel['to_column']}\n"
                )

        prompt = f"""You are a SQL expert. Generate a SQLite SQL query to answer the user's question.

User Query: "{query}"

Database Schema:
{chr(10).join(schema_info)}
{relationships_str}

Generate a valid SQLite SQL query. Important:
- Use proper JOIN syntax based on the relationships provided
- For "last N days" queries, use: column >= datetime('now', '-N days')
- For COUNT queries, use COUNT(DISTINCT column) when counting distinct entities
- Use proper table aliases if needed
- Return only the SQL query, no explanations

SQL Query:"""

        try:
            sql = self._ollama_chat(
                [
                    {
                        "role": "system",
                        "content": "You are a SQL expert. Generate only valid SQLite SQL queries.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=768,
            ).strip()
            # Clean up markdown code blocks if present
            if sql.startswith("```"):
                sql = re.sub(r"^```[a-zA-Z]*\n?", "", sql)
                sql = re.sub(r"\n?```$", "", sql).strip()
            return sql
        except Exception as e:
            print(f"Error in LLM SQL generation (ollama): {e}")
            return None

    def find_table_relationships(self, table_names: List[str]) -> List[Dict]:
        """
        Find relationships (joins) between tables using REFERS_TO relationships.

        Args:
            table_names: List of table names to find relationships for

        Returns:
            List of relationship dictionaries with join information
        """
        relationships = []

        # Find all REFERS_TO relationships between columns of the given tables
        for table1 in table_names:
            for table2 in table_names:
                if table1 == table2:
                    continue

                cypher_query = f"""
                MATCH (t1:Table)-[:HAS_COLUMN]->(c1:Column)-[:REFERS_TO]->(c2:Column)<-[:HAS_COLUMN]-(t2:Table)
                WHERE t1.name = '{table1}' AND t2.name = '{table2}'
                RETURN t1.name AS from_table, c1.name AS from_column,
                       t2.name AS to_table, c2.name AS to_column
                LIMIT 1
                """
                try:
                    result = self.graph.query(cypher_query)
                    for row in result.result_set:
                        relationships.append(
                            {
                                "from_table": row[0],
                                "from_column": row[1],
                                "to_table": row[2],
                                "to_column": row[3],
                            }
                        )
                except Exception as e:
                    pass  # No relationship found

        return relationships

    def generate_sql(self, query: str) -> str:
        """
        Main method to generate SQL from natural language query using LLM and knowledge graph.

        Args:
            query: Natural language query string

        Returns:
            Generated SQL query string
        """
        print(f"Processing query: {query}\n")

        # Get all tables from the knowledge graph
        all_tables = self._get_all_tables()
        print(f"Found {len(all_tables)} tables in knowledge graph")

        if not all_tables:
            return "-- No tables found in the knowledge graph"

        # Use LLM to find relevant tables
        print("Using LLM to identify relevant tables...")
        relevant_table_names = self._llm_find_relevant_tables(query, all_tables)
        print(
            f"LLM identified {len(relevant_table_names)} relevant tables: {relevant_table_names}"
        )


        if not relevant_table_names:
            return "-- No relevant tables found"

        # Get full table information with columns
        relevant_tables = []
        for table_name in relevant_table_names:
            table_info = self._get_table_with_columns(table_name)
            if table_info:
                relevant_tables.append(table_info)

        # Use LLM to select relevant columns for each table
        print("Using LLM to select relevant columns...")
        for table in relevant_tables:
            selected_columns = self._llm_select_columns(query, table)
            # Filter columns to only selected ones
            if selected_columns:
                table["columns"] = [
                    col
                    for col in table["columns"]
                    if col["name"] in selected_columns
                ]
                print(
                    f"Table '{table['name']}': selected {len(table['columns'])} columns"
                )

        # Find relationships between tables
        relationships = self.find_table_relationships(relevant_table_names)
        print(f"Found {len(relationships)} relationships between tables")

        # Use LLM to generate SQL
        print("Using LLM to generate SQL query...")
        sql = self._llm_generate_sql(query, relevant_tables, relationships)
        if sql:
            return sql
        else:            
            print("LLM failed to generate SQL, falling back to basic generation")



def main():
    """Example usage of the SQL Generation Agent."""
    # Initialize the agent
    # Make sure Ollama is running (default: http://localhost:11434) and the model is pulled.
    agent = SQLGenerationAgent(llm_provider="ollama", model="gemma3:12b")

    # Example query
    query = "Count the number of customers transacted in last 3 days"
    print(f"Query: {query}\n")

    # Generate SQL
    sql = agent.generate_sql(query)
    print(f"\nGenerated SQL:\n{sql}")


if __name__ == "__main__":
    main()
