import re
import httpx
import logging

logging.basicConfig(level=logging.INFO)

qdrant_service_url = 'http://127.0.0.1:6969/search'

test_query = "culture and arts"


response = httpx.get(
        qdrant_service_url,
        params={
            "query": test_query,
            "top": 25,
        }
    )

articles = response.json()  # Getting the list of articles from the result

html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Article Display</title>
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --background-color: #333;
            --text-color: #f0f0f0;
            --accent-color: #007bff;
            --article-bg-color: #222;
            --box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            --border-radius: 8px;
        }
        body {
            font-family: 'Poppins', sans-serif;
            margin: 20px;
            background-color: var(--background-color);
            color: var(--text-color);
        }
        .article {
            background-color: var(--article-bg-color);
            margin-bottom: 20px;
            box-shadow: var(--box-shadow);
            border-radius: var(--border-radius);
            padding: 20px;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .article:hover {
            transform: translateY(-5px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        }
        .headline {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 10px;
        }
        .source {
            font-size: 18px;
            color: var(--accent-color);
            margin-bottom: 20px;
        }
        .source a {
            color: inherit;
            text-decoration: none;
            transition: color 0.2s ease;
        }
        .source a:hover {
            color: darken(var(--accent-color), 15%);
        }
        .preview {
            max-height: 100px;
            overflow: hidden;
            transition: max-height 0.2s ease;
        }
        .article.open .preview {
            max-height: 200px;  /* Adjust the height as per your requirement */
            overflow: auto;
        }
        p {
            text-align: justify;
            line-height: 1.6;
        }
    </style>
</head>
<body>
"""

for article in articles:
    headline = article['payload']['headline']
    paragraphs = article['payload']['paragraphs'].split('\n')  # Splitting paragraphs into a list
    source = article['payload']['source']
    url = article['payload']['url']
    score = article['score']

    paragraphs = [re.sub(r'\s+', ' ', p) for p in paragraphs]  # Removing extra whitespaces

    article_html = f"""
    <div class="article">
        <div class="headline">{headline}</div>
        <div class="source">{source} - <a href="{url}" target="_blank">Read More</a></div>
        <div class="score">Score: {score}</div>
        

        <div class="preview">
            {'<br>'.join(paragraphs)}
        </div>
    </div>
    """
    
    html_content += article_html

html_content += """
</body>
</html>
"""

with open('article_display.html', 'w') as f:
    f.write(html_content)
    f.close()
