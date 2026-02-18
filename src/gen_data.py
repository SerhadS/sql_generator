"""
Database data generation utility.

This script generates synthetic banking data and populates a SQLite database.
It creates tables for clients, accounts, transactions, and business relationships,
then generates realistic test data using Faker.
"""

from __future__ import annotations

import sqlite3
import random
from datetime import datetime, timedelta
from typing import List, Tuple, Optional
from pathlib import Path

import os
import pandas as pd
from faker import Faker
from dotenv import load_dotenv
from utils import (
    create_database_connection,
    _get_env_int,
    _get_env_float,
    _get_env_list,
    _get_env_path,
)

# Load environment variables from .env file
load_dotenv()


# Constants loaded from environment variables with defaults
DEFAULT_DB_PATH = _get_env_path("DB_PATH", Path("./data/bank_data.db"))
NUM_CLIENTS = _get_env_int("NUM_CLIENTS", 100000)
NUM_CASA_TRANSACTIONS = _get_env_int("NUM_CASA_TRANSACTIONS", 500000)
NUM_CC_TRANSACTIONS = _get_env_int("NUM_CC_TRANSACTIONS", 30000)
NUM_CLIENT_RELATIONS = _get_env_int("NUM_CLIENT_RELATIONS", 10000)
NUM_BUSINESSES = _get_env_int("NUM_BUSINESSES", 1000)
NUM_BUSINESS_RELATIONS = _get_env_int("NUM_BUSINESS_RELATIONS", 100)

CASA_ACCOUNT_PROBABILITY = _get_env_float("CASA_ACCOUNT_PROBABILITY", 0.7)
CC_ACCOUNT_PROBABILITY = _get_env_float("CC_ACCOUNT_PROBABILITY", 0.3)

STATES = _get_env_list("STATES", ["Texas", "California", "New York", "Florida"])
RELATION_TYPES = _get_env_list(
    "RELATION_TYPES", ["family/partner", "business relation"]
)
BUSINESS_RELATION_TYPES = _get_env_list(
    "BUSINESS_RELATION_TYPES", ["customer", "supplier", "owner"]
)
CC_CATEGORIES = _get_env_list(
    "CC_CATEGORIES", ["groceries", "travel", "entertainment", "utilities"]
)


# Table schema definitions
TABLE_SCHEMAS = {
    "clients": """
        CREATE TABLE IF NOT EXISTS clients (
            client_id INT PRIMARY KEY,
            first_name VARCHAR(50) NOT NULL,
            last_name VARCHAR(50) NOT NULL,
            address TEXT NOT NULL,
            dob DATE NOT NULL,
            phone VARCHAR(15),
            email VARCHAR(50),
            state VARCHAR(50) NOT NULL,
            income DECIMAL(10, 2),
            occupation VARCHAR(50)
        )
    """,
    "casa_accounts": """
        CREATE TABLE IF NOT EXISTS casa_accounts (
            account_id INT PRIMARY KEY,
            client_id INT,
            account_number VARCHAR(50) UNIQUE NOT NULL,
            account_type VARCHAR(20) NOT NULL,
            balance DECIMAL(10, 2),
            FOREIGN KEY (client_id) REFERENCES clients(client_id)
        )
    """,
    "cc_accounts": """
        CREATE TABLE IF NOT EXISTS cc_accounts (
            account_id INT PRIMARY KEY,
            client_id INT,
            card_number VARCHAR(50) UNIQUE NOT NULL,
            account_type VARCHAR(20) NOT NULL,
            credit_limit DECIMAL(10, 2),
            FOREIGN KEY (client_id) REFERENCES clients(client_id)
        )
    """,
    "casa_transactions": """
        CREATE TABLE IF NOT EXISTS casa_transactions (
            transaction_id INT PRIMARY KEY,
            account_id INT,
            date DATETIME NOT NULL,
            type VARCHAR(20) NOT NULL,
            amount DECIMAL(10, 2) NOT NULL,
            balance_after DECIMAL(10, 2),
            FOREIGN KEY (account_id) REFERENCES casa_accounts(account_id)
        )
    """,
    "credit_card_transactions": """
        CREATE TABLE IF NOT EXISTS credit_card_transactions (
            transaction_id INT PRIMARY KEY,
            account_id INT,
            date DATETIME NOT NULL,
            merchant_name VARCHAR(50) NOT NULL,
            category VARCHAR(50),
            state VARCHAR(50),
            amount DECIMAL(10, 2) NOT NULL,
            remaining_credit DECIMAL(10, 2),
            FOREIGN KEY (account_id) REFERENCES cc_accounts(account_id)
        )
    """,
    "client_relations": """
        CREATE TABLE IF NOT EXISTS client_relations (
            relation_id INT PRIMARY KEY,
            client1 INT NOT NULL,
            client2 INT NOT NULL,
            relation_type VARCHAR(20) NOT NULL,
            FOREIGN KEY (client1) REFERENCES clients(client_id),
            FOREIGN KEY (client2) REFERENCES clients(client_id)
        )
    """,
    "client_business_relations": """
        CREATE TABLE IF NOT EXISTS client_business_relations (
            relation_id INT PRIMARY KEY,
            client_id INT NOT NULL,
            business_id INT NOT NULL,
            relation_type VARCHAR(20) NOT NULL,
            FOREIGN KEY (client_id) REFERENCES clients(client_id),
            FOREIGN KEY (business_id) REFERENCES businesses(business_id)
        )
    """,
    "businesses": """
        CREATE TABLE IF NOT EXISTS businesses (
            business_id INT PRIMARY KEY,
            name VARCHAR(50) NOT NULL,
            state VARCHAR(50) NOT NULL,
            revenue DECIMAL(12, 2),
            num_employees INT,
            industry VARCHAR(50)
        )
    """,
}


def create_tables(cursor: sqlite3.Cursor) -> None:
    """
    Create all database tables, dropping existing ones first.

    Args:
        cursor: Database cursor for executing SQL commands
    """
    cursor.execute("PRAGMA foreign_keys = OFF;")
    for table_name, schema in TABLE_SCHEMAS.items():
        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
    cursor.execute("PRAGMA foreign_keys = ON;")
    for table_name, schema in TABLE_SCHEMAS.items():
        cursor.execute(schema)


def generate_clients(num_clients: int = NUM_CLIENTS) -> List[Tuple]:
    """
    Generate synthetic client data.

    Args:
        num_clients: Number of clients to generate

    Returns:
        List of client tuples (client_id, first_name, last_name, address,
        dob, phone, email, state, income, occupation)
    """
    fake = Faker()
    clients = []

    for client_id in range(num_clients):
        first_name = fake.first_name()
        last_name = fake.last_name()
        address = fake.address().replace("\\n", " ")
        dob = fake.date_of_birth(minimum_age=18, maximum_age=90)
        phone = fake.phone_number()
        email = fake.email()
        state = random.choice(STATES)
        income = round(random.uniform(30000, 200000), 2)
        occupation = fake.job()

        clients.append(
            (
                client_id,
                first_name,
                last_name,
                address,
                dob,
                phone,
                email,
                state,
                income,
                occupation,
            )
        )

    return clients


def generate_casa_accounts(
    num_clients: int = NUM_CLIENTS,
    account_probability: float = CASA_ACCOUNT_PROBABILITY,
) -> List[Tuple]:
    """
    Generate CASA (Current Account, Savings Account) account data.

    Args:
        num_clients: Total number of clients to consider
        account_probability: Probability that a client has a CASA account

    Returns:
        List of account tuples (account_id, client_id, account_number,
        account_type, balance)
    """
    fake = Faker()
    accounts = []
    account_id = 0

    for client_id in range(num_clients):
        if random.random() > (1 - account_probability):
            account_type = "CASA"
            balance = round(random.uniform(1000, 50000), 2)
            account_number = f"{fake.uuid4()}_{account_id}"
            accounts.append(
                (account_id, client_id, account_number, account_type, balance)
            )
            account_id += 1

    return accounts


def generate_cc_accounts(
    num_clients: int = NUM_CLIENTS, account_probability: float = CC_ACCOUNT_PROBABILITY
) -> List[Tuple]:
    """
    Generate credit card account data.

    Args:
        num_clients: Total number of clients to consider
        account_probability: Probability that a client has a credit card account

    Returns:
        List of account tuples (account_id, client_id, card_number,
        account_type, credit_limit)
    """
    fake = Faker()
    accounts = []
    account_id = 0

    for client_id in range(num_clients):
        if random.random() > (1 - account_probability):
            account_type = "cc"
            credit_limit = round(random.uniform(5000, 50000), 2)
            card_number = f"{fake.credit_card_number()}_{account_id}"
            accounts.append(
                (account_id, client_id, card_number, account_type, credit_limit)
            )
            account_id += 1

    return accounts


def generate_casa_transactions(
    cursor: sqlite3.Cursor, num_transactions: int = NUM_CASA_TRANSACTIONS
) -> List[Tuple]:
    """
    Generate CASA transaction data.

    Args:
        cursor: Database cursor to query existing accounts
        num_transactions: Number of transactions to generate

    Returns:
        List of transaction tuples (transaction_id, account_id, date,
        type, amount, balance_after)
    """
    fake = Faker()
    transactions = []

    # Get all CASA account IDs
    cursor.execute("SELECT account_id FROM casa_accounts WHERE account_type='CASA'")
    casa_accounts = [row[0] for row in cursor.fetchall()]

    if not casa_accounts:
        return transactions

    for transaction_id in range(num_transactions):
        account_id = random.choice(casa_accounts)
        date = fake.date_between(start_date="-6m", end_date="now")
        amount = round(random.uniform(-5000, 5000), 2)

        # Get current balance and calculate balance_after
        cursor.execute(
            "SELECT balance FROM casa_accounts WHERE account_id=?", (account_id,)
        )
        current_balance = cursor.fetchone()[0]
        balance_after = current_balance + (-amount if random.random() > 0.5 else amount)

        transaction_type = "deposit" if random.random() > 0.5 else "withdrawal"
        transactions.append(
            (transaction_id, account_id, date, transaction_type, amount, balance_after)
        )

    return transactions


def generate_credit_card_transactions(
    cursor: sqlite3.Cursor, num_transactions: int = NUM_CC_TRANSACTIONS
) -> List[Tuple]:
    """
    Generate credit card transaction data.

    Args:
        cursor: Database cursor to query existing accounts
        num_transactions: Number of transactions to generate

    Returns:
        List of transaction tuples (transaction_id, account_id, date,
        merchant_name, category, state, amount, remaining_credit)
    """
    fake = Faker()
    transactions = []

    # Get all credit card account IDs
    cursor.execute("SELECT account_id FROM cc_accounts")
    credit_accounts = [row[0] for row in cursor.fetchall()]

    if not credit_accounts:
        return transactions

    for transaction_id in range(num_transactions):
        account_id = random.choice(credit_accounts)
        date = fake.date_between(start_date="-6m", end_date="now")
        merchant_name = fake.company()
        category = random.choice(CC_CATEGORIES)
        state = random.choice(STATES)
        amount = round(random.uniform(-1000, 1000), 2)

        # Get current credit limit and calculate remaining credit
        cursor.execute(
            "SELECT credit_limit FROM cc_accounts WHERE account_id=?", (account_id,)
        )
        credit_limit = cursor.fetchone()[0]
        remaining_credit = credit_limit - amount

        transactions.append(
            (
                transaction_id,
                account_id,
                date,
                merchant_name,
                category,
                state,
                amount,
                remaining_credit,
            )
        )

    return transactions


def generate_client_relations(
    num_relations: int = NUM_CLIENT_RELATIONS, max_client_id: int = NUM_CLIENTS - 1
) -> List[Tuple]:
    """
    Generate client-to-client relationship data.

    Args:
        num_relations: Number of relationships to generate
        max_client_id: Maximum client ID to use

    Returns:
        List of relation tuples (relation_id, client1, client2, relation_type)
    """
    relations = []

    for relation_id in range(num_relations):
        client1 = random.randint(0, max_client_id)
        client2 = random.randint(0, max_client_id)

        if client1 != client2:
            relation_type = random.choice(RELATION_TYPES)
            relations.append((relation_id, client1, client2, relation_type))

    return relations


def generate_business_data(
    num_businesses: int = NUM_BUSINESSES,
    num_relations: int = NUM_BUSINESS_RELATIONS,
    max_client_id: int = NUM_CLIENTS - 1,
) -> Tuple[List[Tuple], List[Tuple]]:
    """
    Generate business and client-business relationship data.

    Args:
        num_businesses: Number of businesses to generate
        num_relations: Number of client-business relationships to generate
        max_client_id: Maximum client ID to use for relationships

    Returns:
        Tuple of (businesses list, relations list)
        Businesses: (business_id, name, state, revenue, num_employees, industry)
        Relations: (relation_id, client_id, business_id, relation_type)
    """
    fake = Faker()
    businesses = []

    for business_id in range(num_businesses):
        name = fake.company()
        state = random.choice(STATES)
        revenue = round(random.uniform(500000, 5000000), 2)
        num_employees = random.randint(10, 300)
        industry = fake.bs()
        businesses.append((business_id, name, state, revenue, num_employees, industry))

    relations = []
    for relation_id in range(num_relations):
        client_id = random.randint(0, max_client_id)
        business_id = random.randint(0, num_businesses - 1)
        relation_type = random.choice(BUSINESS_RELATION_TYPES)
        relations.append((relation_id, client_id, business_id, relation_type))

    return businesses, relations


def populate_database(conn: sqlite3.Connection, cursor: sqlite3.Cursor) -> None:
    """
    Populate the database with generated data.

    This function orchestrates the data generation and insertion process,
    maintaining the same order and behavior as the original script.

    Args:
        conn: Database connection
        cursor: Database cursor
    """
    # Generate and insert clients
    print("Generating clients...")
    clients = generate_clients()
    cursor.executemany(
        "INSERT INTO clients VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", clients
    )
    conn.commit()
    print("Client table populated")

    # Generate and insert CASA accounts
    print("Generating CASA accounts...")
    casa_accounts = generate_casa_accounts(
        num_clients=NUM_CLIENTS, account_probability=CASA_ACCOUNT_PROBABILITY
    )
    cursor.executemany(
        "INSERT INTO casa_accounts VALUES (?, ?, ?, ?, ?)", casa_accounts
    )
    conn.commit()
    print("CASA account table populated")

    # Generate and insert credit card accounts
    print("Generating credit card accounts...")
    cc_accounts = generate_cc_accounts(
        num_clients=NUM_CLIENTS, account_probability=CC_ACCOUNT_PROBABILITY
    )
    cursor.executemany("INSERT INTO cc_accounts VALUES (?, ?, ?, ?, ?)", cc_accounts)
    conn.commit()
    print("CC account table populated")

    # Generate and insert CASA transactions
    print("Generating CASA transactions...")
    casa_transactions = generate_casa_transactions(cursor)
    cursor.executemany(
        "INSERT INTO casa_transactions VALUES (?, ?, ?, ?, ?, ?)", casa_transactions
    )
    conn.commit()
    print("CASA transaction data table populated")

    # Generate and insert credit card transactions
    print("Generating credit card transactions...")
    cc_transactions = generate_credit_card_transactions(cursor)
    cursor.executemany(
        "INSERT INTO credit_card_transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        cc_transactions,
    )
    conn.commit()
    print("CC transaction data table populated")

    # Generate and insert client relations
    print("Generating client relations...")
    client_relations = generate_client_relations()
    cursor.executemany(
        "INSERT INTO client_relations VALUES (?, ?, ?, ?)", client_relations
    )
    conn.commit()
    print("Client relations table populated")

    # Generate and insert business data
    print("Generating business data...")
    businesses, business_relations = generate_business_data()
    cursor.executemany("INSERT INTO businesses VALUES (?, ?, ?, ?, ?, ?)", businesses)
    cursor.executemany(
        "INSERT INTO client_business_relations VALUES (?, ?, ?, ?)", business_relations
    )
    conn.commit()
    print("Business related table populated")


def main(db_path: Path = DEFAULT_DB_PATH) -> None:
    """
    Main function to generate and populate the database.

    Args:
        db_path: Path to the database file to create/populate
    """
    # Ensure data directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create database connection
    conn = create_database_connection(db_path)
    cursor = conn.cursor()

    try:
        # Create tables
        print("Creating tables...")
        create_tables(cursor)
        conn.commit()
        print("Tables are created")

        # Populate database
        populate_database(conn, cursor)

        print("Database populated successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Error populating database: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
