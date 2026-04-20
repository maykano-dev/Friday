"""Test Zara's full integration."""
import zara_core

print("=== Testing Zara Integration ===\n")

test_queries = [
    "What's the weather in London?",
    "Tell me a joke",
    "Give me a quote",
    "Define python",
    "What is artificial intelligence?",
    "Hello Zara",
]

for query in test_queries:
    print(f"\nUser: {query}")
    response = zara_core.generate_response(query)
    print(f"Zara: {response[:150]}...")
    print("-" * 50)

print("\n=== Integration test complete ===")
