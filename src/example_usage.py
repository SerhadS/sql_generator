"""
Example usage of the SQL Generation Agent

This script demonstrates how to use the SQLGenerationAgent to convert
natural language queries into SQL using the FalkorDB knowledge graph and LLMs.
"""

import os
from sql_agent import SQLGenerationAgent


def main():
    """Run example queries through the SQL generation agent."""

    # Ollama setup
    # - Ensure Ollama is running locally (default: http://localhost:11434)
    # - Ensure your model is pulled (example: `ollama pull llama3.1:8b`)
    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    print(f"Using Ollama host: {ollama_host}")

    # Initialize the agent with LLM support
    print("Initializing SQL Generation Agent with LLM support...")
    agent = SQLGenerationAgent(
        llm_provider="ollama",
        model="gemma3:12b",
        ollama_host=ollama_host,
    )
    print("Agent initialized successfully!\n")

    # Example queries
    example_queries = [
        "Count the number of customers transacted by their credit cards in last 3 days above 100 dollars",
        "Show all clients with their account balances where the balance is above 5000 dollars and age is above 30",
        "Find transactions from the last week where the amount is greater than 1000 dollars and the customer is from New York",
        "List all businesses in California which do not have any relation to our credit card customers",
        "List top 2 customers for each day by transaction amount in last 7 days",
    ]

    for i, query in enumerate(example_queries, 1):
        print("=" * 80)
        print(f"Example {i}: {query}")
        print("=" * 80)

        try:
            sql = agent.generate_sql(query)
            print(f"\nGenerated SQL:\n{sql}\n")
        except Exception as e:
            print(f"Error generating SQL: {e}\n")

        print()


if __name__ == "__main__":
    main()
