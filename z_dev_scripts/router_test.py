import logging
from typing import List
import textgrad as tg
from semantic_router.encoders import HuggingFaceEncoder
from semantic_router import Route
from semantic_router.layer import RouteLayer
from semantic_router.llms.ollama import OllamaLLM
import os

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Configure HuggingFace Encoder
encoder = HuggingFaceEncoder()
llm = OllamaLLM(llm_name="llama3.1")
os.environ["OPENAI_API_KEY"] = "xxx"
tg.set_backward_engine("gpt-4", override=True)

# Define routes
routes = [
    Route(
        name="politics",
        utterances=[
            "isn't politics the best thing ever",
            "why don't you tell me about your political opinions",
            "don't you just love the president",
            "don't you just hate the president",
            "they're going to destroy this country!",
            "they will save the country!",
        ],
    ),
    Route(
        name="chitchat",
        utterances=[
            "Did you watch the game last night?",
            "what's your favorite type of music?",
            "Have you read any good books lately?",
            "nice weather we're having",
            "Do you have any plans for the weekend?",
        ],
    ),
    Route(
        name="mathematics",
        utterances=[
            "can you explain the concept of a derivative?",
            "What is the formula for the area of a triangle?",
            "how do you solve a system of linear equations?",
            "What is the concept of a prime number?",
            "Can you explain the Pythagorean theorem?",
        ],
    ),
    Route(
        name="biology",
        utterances=[
            "what is the process of osmosis?",
            "can you explain the structure of a cell?",
            "What is the role of RNA?",
            "What is genetic mutation?",
            "Can you explain the process of photosynthesis?",
        ],
    ),
]

# Configure RouteLayer
rl = RouteLayer(encoder=encoder, routes=routes)

def route_text(text: str) -> str:
    """Route the input text using the semantic router."""
    try:
        result = rl(text)
        logger.info(f"Routing result for '{text}': {result}")
        return result.name if result else None
    except Exception as e:
        logger.error(f"Error routing text '{text}': {e}")
        raise

def process_routing_requests(texts: List[str]) -> List[str]:
    """Process a batch of routing requests."""
    results = []
    for text in texts:
        try:
            result = route_text(text)
            results.append(result)
        except Exception as e:
            logger.error(f"Error processing text '{text}': {e}")
            results.append(None)
    return results

def test_multiple_routes(text: str):
    """Test retrieving multiple routes for a given text."""
    results = rl.retrieve_multiple_routes(text)
    logger.info(f"Multiple routes for '{text}':")
    for result in results:
        logger.info(f"  - {result.name}: {result.similarity_score}")

def optimize_routes(routes: List[Route], test_data: List[tuple]):
    """Optimize route utterances using TextGrad."""
    for route in routes:
        # Join utterances into a single string
        utterances_str = "\n".join(route.utterances)
        utterances = tg.Variable(utterances_str, requires_grad=True, role_description=f"utterances for {route.name} route")
        optimizer = tg.TGD(parameters=[utterances])
        
        evaluation_instruction = (f"Evaluate the effectiveness of these utterances for the '{route.name}' route. "
                                  "Provide concise feedback on how to improve them. "
                                  "Each utterance should be on a new line.")
        loss_fn = tg.TextLoss(evaluation_instruction)
        
        for _ in range(3):  # Perform 3 optimization steps
            loss = loss_fn(utterances)
            loss.backward()
            optimizer.step()
        
        # Split the optimized utterances back into a list
        route.utterances = utterances.value.split("\n")
    
    return routes

if __name__ == "__main__":
    # Initial test cases
    initial_test_texts = [
        "don't you love politics?",
        "how's the weather today?",
        "What's DNA?",
        "I'm interested in learning about llama 2",
    ]

    print("Initial testing:")
    for text in initial_test_texts:
        result = route_text(text)
        print(f"Text: '{text}'\nRouted to: {result}\n")

    # Comprehensive test data
    test_data = [
        # politics
        ("What's your opinion on the current government?", "politics"),
        ("Who do you think will win the next election?", "politics"),
        ("What are your thoughts on the new policy?", "politics"),
        ("How do you feel about the political situation?", "politics"),
        ("Do you agree with the president's actions?", "politics"),
        # chitchat
        ("What's the weather like?", "chitchat"),
        ("It's a beautiful day today.", "chitchat"),
        ("How's your day going?", "chitchat"),
        ("It's raining cats and dogs.", "chitchat"),
        ("Let's grab a coffee.", "chitchat"),
        # mathematics
        ("What is the Pythagorean theorem?", "mathematics"),
        ("Can you solve this quadratic equation?", "mathematics"),
        ("What is the derivative of x squared?", "mathematics"),
        ("Explain the concept of integration.", "mathematics"),
        ("What is the area of a circle?", "mathematics"),
        # biology
        ("What is photosynthesis?", "biology"),
        ("Explain the process of cell division.", "biology"),
        ("What is the function of mitochondria?", "biology"),
        ("What is DNA?", "biology"),
        ("What is the difference between prokaryotic and eukaryotic cells?", "biology"),
        # None routes
        ("What is the capital of France?", None),
        ("how many people live in the US?", None),
        ("when is the best time to visit Bali?", None),
        ("how do I learn a language", None),
        ("tell me an interesting fact", None),
    ]

    # Unpack the test data
    X, y = zip(*test_data)

    print("\nEvaluating with default thresholds:")
    accuracy = rl.evaluate(X=X, y=y)
    print(f"Accuracy: {accuracy*100:.2f}%")

    print("\nDefault route thresholds:")
    print(rl.get_thresholds())

    print("\nOptimizing route thresholds...")
    rl.fit(X=X, y=y)

    print("\nUpdated route thresholds:")
    print(rl.get_thresholds())

    print("\nEvaluating with optimized thresholds:")
    accuracy = rl.evaluate(X=X, y=y)
    print(f"Accuracy: {accuracy*100:.2f}%")

    print("\nOptimizing route utterances using TextGrad...")
    optimized_routes = optimize_routes(routes, test_data)

    # Print optimized utterances
    for route in optimized_routes:
        print(f"\nOptimized utterances for {route.name}:")
        for utterance in route.utterances:
            print(f"- {utterance}")

    # Update RouteLayer with optimized routes
    rl = RouteLayer(encoder=encoder, routes=optimized_routes)

    print("\nEvaluating with optimized utterances and thresholds:")
    accuracy = rl.evaluate(X=X, y=y)
    print(f"Accuracy: {accuracy*100:.2f}%")

    print("\nTesting multiple route retrieval:")
    test_multiple_routes("The impact of AI on politics and biology")
    test_multiple_routes("Mathematical models in ecological systems")

    print("\nTesting edge cases:")
    edge_cases = [
        "This text is completely unrelated to any of the defined routes.",
        "A mix of topics: political debates on stem cell research.",
        "",  # Empty string
        "Short text",
    ]
    for text in edge_cases:
        result = route_text(text)
        print(f"Text: '{text}'\nRouted to: {result}\n")