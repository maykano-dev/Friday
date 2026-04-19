"""Test Friday's full integration."""
import friday_core

print("=== Testing Friday Integration ===\n")

test_queries = [
    "What's the weather in London?",
    "Tell me a joke",
    "Give me a quote",
    "Define python",
    "What is artificial intelligence?",
    "Hello Friday",
]

for query in test_queries:
    print(f"\nUser: {query}")
    response = friday_core.generate_response(query)
    print(f"Friday: {response[:150]}...")
    print("-" * 50)

print("\n=== Integration test complete ===")
