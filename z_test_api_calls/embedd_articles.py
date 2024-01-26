import requests
import json

# Define the API endpoint
url = "http://localhost:0420/create_embeddings"  # Adjust the port if your service runs on a different one

# Sample data to be sent to the API
data = [
        {
            "url": "http://example.com/article1",
            "headline": "Breaking News",
            "paragraphs": ["This is the first paragraph.", "This is the second paragraph."]
        },
        {
            "url": "http://example.com/article2",
            "headline": "Latest Update",
            "paragraphs": ["Another news paragraph here.", "More details in this paragraph."]
        }
    ]

# Convert the data to JSON
json_data = json.dumps(data)

# Set the appropriate headers for a JSON request
headers = {'Content-Type': 'application/json'}

# Make the POST request
response = requests.post(url, data=json_data, headers=headers)

# Print the response
print("Status Code:", response.status_code)
print("Response Body:", response.json())
