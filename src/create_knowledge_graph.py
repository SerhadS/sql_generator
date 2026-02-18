"""
Knowledge graph creation utility.

This script creates a FalkorDB knowledge graph from database schema information.
It reads schema.json and creates nodes for tables and columns, along with
relationships (HAS_COLUMN and REFERS_TO) between them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv
from falkordb import Edge, FalkorDB, Node

from utils import _get_env_path

# Constants
DEFAULT_SCHEMA_PATH = Path("./data/schema.json")
DEFAULT_GRAPH_NAME = "schema_graph"
DEFAULT_FALKOR_HOST = "localhost"
DEFAULT_FALKOR_PORT = 6379


def load_schema(schema_path: Path) -> List[Dict]:
    """
    Load schema information from JSON file.

    Args:
        schema_path: Path to the schema.json file

    Returns:
        List of schema dictionaries containing table and column information

    Raises:
        FileNotFoundError: If schema file doesn't exist
        json.JSONDecodeError: If schema file is not valid JSON
    """
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_falkor_connection(
    host: str = DEFAULT_FALKOR_HOST, port: int = DEFAULT_FALKOR_PORT
) -> FalkorDB:
    """
    Create and return a FalkorDB connection.

    Args:
        host: FalkorDB host address
        port: FalkorDB port number

    Returns:
        FalkorDB connection instance
    """
    return FalkorDB(host=host, port=port)


def initialize_graph(
    db: FalkorDB, graph_name: str = DEFAULT_GRAPH_NAME
) -> FalkorDB.Graph:
    """
    Initialize or reset the knowledge graph.

    If the graph already exists, it will be deleted and recreated.

    Args:
        db: FalkorDB connection instance
        graph_name: Name of the graph to create/initialize

    Returns:
        Graph instance ready for use
    """
    graph = db.select_graph(graph_name)

    try:
        graph.delete()
        graph = db.select_graph(graph_name)
        print(f"Existing graph '{graph_name}' deleted and recreated")
    except Exception as e:
        print(f"Graph deletion error (may not exist): {e}")

    print(f"Graph '{graph_name}' initialized: {graph}")
    return graph


def create_table_node(
    graph: FalkorDB.Graph, table_name: str, description: str, node_id: int
) -> Node:
    """
    Create a Table node in the knowledge graph.

    Args:
        graph: Graph instance
        table_name: Name of the table
        description: Description of the table
        node_id: Unique node identifier

    Returns:
        Created Node instance
    """
    table_node = Node(
        node_id=node_id,
        labels=["Table"],
        properties={
            "name": table_name,
            "description": description or "",
            "node_id": node_id,
        },
    )

    graph.query(f"CREATE {str(table_node)}")
    print(f"Created table node: {table_name} (id: {node_id})")

    return table_node


def create_column_node(
    graph: FalkorDB.Graph,
    column_name: str,
    column_type: str,
    description: str,
    node_id: int,
) -> Node:
    """
    Create a Column node in the knowledge graph.

    Args:
        graph: Graph instance
        column_name: Name of the column
        column_type: Data type of the column
        description: Description of the column
        node_id: Unique node identifier

    Returns:
        Created Node instance
    """
    column_node = Node(
        node_id=node_id,
        labels=["Column"],
        properties={
            "name": column_name,
            "type": column_type,
            "description": description or "",
            "node_id": node_id,
        },
    )

    graph.query(f"CREATE {str(column_node)}")
    print(f"Created column node: {column_name} (id: {node_id})")

    return column_node


def create_has_column_relationship(
    graph: FalkorDB.Graph, table_node: Node, column_node: Node
) -> None:
    """
    Create a HAS_COLUMN relationship between a table and its column.

    Args:
        graph: Graph instance
        table_node: Table node
        column_node: Column node
    """
    cypher_query = f"""
        MATCH (t:Table {{node_id: {table_node.id}}}), (c:Column {{node_id: {column_node.id}}})
        CREATE (t)-[:HAS_COLUMN]->(c)
    """
    graph.query(cypher_query)
    print(
        f"Created HAS_COLUMN relationship: {table_node.properties['name']} -> {column_node.properties['name']}"
    )


def find_column_node_id(
    table_name: str, column_name: str, schemas: List[Dict]
) -> Optional[int]:
    """
    Find the node_id of a column in the schemas.

    Args:
        table_name: Name of the table containing the column
        column_name: Name of the column
        schemas: List of schema dictionaries

    Returns:
        Node ID if found, None otherwise
    """
    for schema in schemas:
        if schema["table"] == table_name:
            for col in schema["columns"]:
                if col["name"] == column_name:
                    return col.get("node_id")
    return None


def create_refers_to_relationship(
    graph: FalkorDB.Graph, src_node_id: int, target_node_id: int
) -> None:
    """
    Create a REFERS_TO relationship between two columns (foreign key relationship).

    Args:
        graph: Graph instance
        src_node_id: Node ID of the source column (foreign key)
        target_node_id: Node ID of the target column (referenced key)
    """
    cypher_query = f"""
        MATCH (a:Column {{node_id: '{src_node_id}'}}), (b:Column {{node_id: '{target_node_id}'}})
        CREATE (a)-[:REFERS_TO]->(b)
    """
    graph.query(cypher_query)
    print(f"Created REFERS_TO relationship: {src_node_id} -> {target_node_id}")


def create_table_and_column_nodes(
    graph: FalkorDB.Graph, schemas: List[Dict]
) -> Tuple[List[Node], int]:
    """
    Create all table and column nodes, along with HAS_COLUMN relationships.

    Args:
        graph: Graph instance
        schemas: List of schema dictionaries

    Returns:
        Tuple of (list of all nodes, next available node_id)
    """
    nodes: List[Node] = []
    node_id = 0

    for schema in schemas:
        # Create table node
        table_name = schema["table"]
        table_description = schema.get("description", "")
        table_node = create_table_node(graph, table_name, table_description, node_id)

        nodes.append(table_node)
        schema["node_id"] = node_id
        node_id += 1

        # Create column nodes and HAS_COLUMN relationships
        for col in schema["columns"]:
            column_node = create_column_node(
                graph,
                col["name"],
                col["type"],
                col.get("description", ""),
                node_id,
            )
            nodes.append(column_node)
            col["node_id"] = node_id
            node_id += 1

            # Create HAS_COLUMN relationship
            create_has_column_relationship(graph, table_node, column_node)

    return nodes, node_id


def create_foreign_key_relationships(
    graph: FalkorDB.Graph, schemas: List[Dict]
) -> None:
    """
    Create REFERS_TO relationships based on foreign key constraints.

    Args:
        graph: Graph instance
        schemas: List of schema dictionaries with node_ids populated
    """
    for schema in schemas:
        if not schema.get("relationships"):
            continue

        print(f"Processing relationships for table: {schema['table']}")
        print(f"Relationships: {schema['relationships']}")

        for rel in schema["relationships"]:
            referred_table = rel["referred_table"]
            constrained_columns = rel["constrained_columns"]
            referred_columns = rel["referred_columns"]

            # Find the target schema
            target_schema = None
            for schema_ in schemas:
                if schema_["table"] == referred_table:
                    target_schema = schema_
                    break

            if not target_schema:
                print(f"Warning: Referred table '{referred_table}' not found")
                continue

            # Create REFERS_TO relationships for each foreign key column pair
            for i, constrained_col in enumerate(constrained_columns):
                if i >= len(referred_columns):
                    continue

                referred_col = referred_columns[i]

                # Find source column node_id
                src_node_id = find_column_node_id(
                    schema["table"], constrained_col, schemas
                )

                # Find target column node_id
                target_node_id = find_column_node_id(
                    referred_table, referred_col, schemas
                )

                if src_node_id is not None and target_node_id is not None:
                    create_refers_to_relationship(graph, src_node_id, target_node_id)
                else:
                    print(
                        f"Warning: Could not find node_ids for relationship "
                        f"{schema['table']}.{constrained_col} -> {referred_table}.{referred_col}"
                    )


def create_knowledge_graph(
    schema_path: Path,
    graph_name: str = DEFAULT_GRAPH_NAME,
    falkor_host: str = DEFAULT_FALKOR_HOST,
    falkor_port: int = DEFAULT_FALKOR_PORT,
) -> None:
    """
    Main function to create the knowledge graph from schema information.

    Args:
        schema_path: Path to the schema.json file
        graph_name: Name of the graph to create
        falkor_host: FalkorDB host address
        falkor_port: FalkorDB port number
    """
    # Load schema
    print(f"Loading schema from: {schema_path}")
    schemas = load_schema(schema_path)
    print(f"Loaded {len(schemas)} tables")

    # Create FalkorDB connection
    print(f"Connecting to FalkorDB at {falkor_host}:{falkor_port}")
    db = create_falkor_connection(falkor_host, falkor_port)

    # Initialize graph
    graph = initialize_graph(db, graph_name)

    # Create table and column nodes
    print("\nCreating table and column nodes...")
    nodes, _ = create_table_and_column_nodes(graph, schemas)
    print(f"Created {len(nodes)} nodes")

    # Create foreign key relationships
    print("\nCreating foreign key relationships...")
    create_foreign_key_relationships(graph, schemas)

    print("\nKnowledge graph creation completed successfully!")


def main() -> None:
    """Main entry point for the script."""
    schema_path = _get_env_path("SCHEMA_PATH", DEFAULT_SCHEMA_PATH)
    graph_name = os.getenv("GRAPH_NAME", DEFAULT_GRAPH_NAME)
    falkor_host = os.getenv("FALKOR_HOST", DEFAULT_FALKOR_HOST)
    falkor_port = int(os.getenv("FALKOR_PORT", str(DEFAULT_FALKOR_PORT)))

    create_knowledge_graph(schema_path, graph_name, falkor_host, falkor_port)


if __name__ == "__main__":
    load_dotenv()
    main()
