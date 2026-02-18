from __future__ import annotations
import sys

sys.path.insert(0, "./src")

import json
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Sequence

import pandas as pd
from sqlalchemy import inspect, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.reflection import Inspector

DATA_DIR = os.path.abspath("./data")
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "bank_data.db")
DEFAULT_COL_DESC_CSV = os.path.join(DATA_DIR, "table_col_desc.csv")
DEFAULT_TABLE_DESC_CSV = os.path.join(DATA_DIR, "table_descriptions.csv")
DEFAULT_SCHEMA_JSON = os.path.join(DATA_DIR, "schema.json")


@dataclass
class ColumnSchema:
    name: str
    type: str
    description: str = ""


@dataclass
class Relationship:
    constrained_columns: List[str]
    referred_table: str
    referred_columns: List[str]


@dataclass
class TableSchema:
    schema: str
    table: str
    columns: List[ColumnSchema]
    relationships: List[Relationship]
    description: str = ""


def load_description_data(
    column_desc_path: str = DEFAULT_COL_DESC_CSV,
    table_desc_path: str = DEFAULT_TABLE_DESC_CSV,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load table and column description CSVs.

    Returns:
        (desc_df, tab_desc_df) where:
          - desc_df: column-level descriptions
          - tab_desc_df: table-level descriptions indexed by Table_Name
    """
    desc_df = pd.read_csv(column_desc_path, encoding="utf-8")
    tab_desc_df = pd.read_csv(table_desc_path, encoding="utf-8")
    tab_desc_df = tab_desc_df.set_index("Table_Name")
    return desc_df, tab_desc_df


def build_inspector(engine: Engine) -> Inspector:
    """Create a SQLAlchemy Inspector from the engine."""
    return inspect(engine)


def _get_table_description(table_name: str, tab_desc_df: pd.DataFrame) -> str:
    """Safely get the table description, empty string if missing."""
    if table_name in tab_desc_df.index:
        try:
            return str(tab_desc_df.loc[table_name, "Description"])
        except Exception:
            return ""
    return ""


def _get_column_description(
    table_name: str,
    column_name: str,
    desc_df: pd.DataFrame,
) -> str:
    """
    Safely get a column's detailed description from the column description DataFrame.
    """
    temp = desc_df[desc_df["Table_Name"] == table_name]
    match = temp.loc[temp["Column_Name"] == column_name, "Detailed_Description"]
    if match.empty:
        return ""
    value = match.values[0]
    return "" if pd.isna(value) else str(value)


def extract_table_schema(
    inspector: Inspector,
    schema_name: str,
    table_name: str,
    desc_df: pd.DataFrame,
    tab_desc_df: pd.DataFrame,
) -> TableSchema:
    """
    Extract schema information for a single table.
    """
    table_description = _get_table_description(table_name, tab_desc_df)

    # Columns
    columns_meta = inspector.get_columns(table_name, schema=schema_name)
    columns: List[ColumnSchema] = []
    for col in columns_meta:
        col_name = col["name"]
        col_type = str(col["type"])
        col_desc = _get_column_description(table_name, col_name, desc_df)
        columns.append(
            ColumnSchema(
                name=col_name,
                type=col_type,
                description=col_desc,
            )
        )

    # Relationships (foreign keys)
    relationships: List[Relationship] = []
    foreign_keys: Sequence[Dict[str, Any]] = inspector.get_foreign_keys(table_name)
    if foreign_keys:
        for fk in foreign_keys:
            relationships.append(
                Relationship(
                    constrained_columns=list(fk.get("constrained_columns", [])),
                    referred_table=str(fk.get("referred_table", "")),
                    referred_columns=list(fk.get("referred_columns", [])),
                )
            )

    return TableSchema(
        schema=schema_name,
        table=table_name,
        columns=columns,
        relationships=relationships,
        description=table_description,
    )


def create_sqlite_engine(db_path: str = DEFAULT_DB_PATH) -> Engine:
    """Create a SQLite engine from the database path."""
    return create_engine(f"sqlite:///{db_path}")


def extract_schemas(
    db_path: str = DEFAULT_DB_PATH,
    column_desc_path: str = DEFAULT_COL_DESC_CSV,
    table_desc_path: str = DEFAULT_TABLE_DESC_CSV,
) -> List[TableSchema]:
    """
    Extract schema information for all tables in the database.

    """
    desc_df, tab_desc_df = load_description_data(
        column_desc_path=column_desc_path,
        table_desc_path=table_desc_path,
    )

    engine = create_sqlite_engine(db_path=db_path)
    inspector = build_inspector(engine)

    schemas: List[TableSchema] = []
    for schema_name in inspector.get_schema_names():
        for table_name in inspector.get_table_names(schema=schema_name):
            table_schema = extract_table_schema(
                inspector=inspector,
                schema_name=schema_name,
                table_name=table_name,
                desc_df=desc_df,
                tab_desc_df=tab_desc_df,
            )
            schemas.append(table_schema)

    return schemas


def write_schema_json(
    schemas: List[TableSchema], output_path: str = DEFAULT_SCHEMA_JSON
) -> None:
    """
    Serialize schemas to JSON in the original structure expected by downstream code.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    serializable: List[Dict[str, Any]] = []
    for table in schemas:
        table_dict = asdict(table)
        # Convert dataclass structure to the original plain dicts (columns/relationships as dict lists)
        table_dict["columns"] = [asdict(c) for c in table.columns]
        table_dict["relationships"] = [asdict(r) for r in table.relationships]
        serializable.append(table_dict)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)


def main() -> None:
    """
    CLI entrypoint for schema extraction.

    Currently uses default paths under ./data, matching the original script.
    """
    schemas = extract_schemas(
        db_path=DEFAULT_DB_PATH,
        column_desc_path=DEFAULT_COL_DESC_CSV,
        table_desc_path=DEFAULT_TABLE_DESC_CSV,
    )
    write_schema_json(schemas, output_path=DEFAULT_SCHEMA_JSON)


if __name__ == "__main__":
    main()
