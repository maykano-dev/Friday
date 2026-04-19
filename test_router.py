# test_router.py - Save and run this
from smart_router import get_router
from free_web_tools import get_web_tools

print("=== Testing Smart Router ===\n")

router = get_router()

# Test 1: Simple query (should use cache or Groq)
response, endpoint = router.route("Hello, how are you?", allow_cache=True)
print(f"Test 1 - Greeting:")
print(f"  Response: {response[:100]}...")
print(f"  Endpoint: {endpoint.value}\n")

# Test 2: Web search
response, endpoint = router.route("What is Python?", allow_web_search=True)
print(f"Test 2 - Web Search:")
print(f"  Response: {response[:100]}...")
print(f"  Endpoint: {endpoint.value}\n")

# Test 3: Free web tools
web = get_web_tools()
weather = web.get_weather("London")
print(f"Test 3 - Weather API:")
print(f"  {weather[:100] if weather else 'Failed'}...\n")

joke = web.get_random_joke()
print(f"Test 4 - Joke API:")
print(f"  {joke}\n")

print("=== All tests complete ===")
