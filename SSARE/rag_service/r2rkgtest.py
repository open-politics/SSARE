from r2r import R2RAppBuilder, Document
import json

def process_documents():
    r2r_app = R2RAppBuilder(from_config="neo4j_kg").build()

    ## ToDo: Pull articles from Postgres // which rule? // --> topics

    ## Metadata is optional, but filtered locations, entities and other classifications need be inserted
    try:
        with open('response.json', 'r') as f:
            response = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return

    # Transform the documents into a list of Document objects
    documents = []
    for result in response["results"]:
        entities = [{"text": entity["text"], "tag": entity["tag"]} for entity in result.get("entities", [])]
        documents.append(
            Document(
                type="txt",
                data=result["content"],
                metadata={
                    "title": result["title"],
                    "url": result["url"],
                    "published_date": result["published date"],
                    "score": result["score"],
                    "entities": entities,
                    "locations": [entity["text"] for entity in result.get("entities", []) if entity["tag"] == "GPE"],
                    "organizations": [entity["text"] for entity in result.get("entities", []) if entity["tag"] == "ORG"],
                    "persons": [entity["text"] for entity in result.get("entities", []) if entity["tag"] == "PERSON"],
                    "dates": [entity["text"] for entity in result.get("entities", []) if entity["tag"] == "DATE"],
                },
            )
        )
    
    for doc in documents:
        print(f"Title: {doc.metadata['title']}")
        print(f"URL: {doc.metadata['url']}")
        print(f"Published Date: {doc.metadata['published_date']}")
        print(f"Score: {doc.metadata['score']}")
        print("Entities:")
        for entity in doc.metadata['entities']:
            print(f"  - {entity['text']} ({entity['tag']})")
        print("Locations:", ", ".join(doc.metadata['locations']))
        print("Organizations:", ", ".join(doc.metadata['organizations']))
        print("Persons:", ", ".join(doc.metadata['persons']))
        print("Dates:", ", ".join(doc.metadata['dates']))
        print("Content:", str(doc.data)[:200] + "..." if len(doc.data) > 200 else doc.data)
        print("\n" + "-"*80 + "\n")

    print('hi')
    print('ho')
    # r2r_app.ingest_documents(documents)

    # # Get the KG provider
    # neo4j_kg = r2r_app.providers.kg

    # ## TODO Pulling articles for a topic from Postgres Service
    # ## Pulling entities and reranking relevant entities
    # ## Putting most relevant entities into below

    # # The expected entities
    # entity_names = ["John", "Paul", "Google", "Microsoft"]

    # print("\nEntities:")
    # for entity in entity_names:
    #     print(f"Locating {entity}:\n", neo4j_kg.get(properties={"name": entity}))

    # relationships = neo4j_kg.get_triplets(entity_names=entity_names)

    # print("\nRelationships:")
    # for triplet in relationships:
    #     source, relation, target = triplet
    #     print(f"{source} -[{relation.label}]-> {target} ")

# # Search the vector database
# vector_search_results = r2r_app.search(query="Who is john")
# print('\nVector Search Results:\n', vector_search_results)

# # Semantic search over the knowledge graph
# from r2r.core import VectorStoreQuery
# node_search_result = neo4j_kg.vector_query(
#     VectorStoreQuery(
#         query_embedding=r2r_app.providers.embedding.get_embedding("A person"),
#     )
# )
# print('\nNode Search Result:', node_search_result)

# # Structured query
# structured_query = """
# MATCH (p1:person)-[:KNOWS]->(p2:person)
# RETURN p1.name AS Person1, p2.name AS Person2
# ORDER BY p1.name
# LIMIT 10;
# """
# print("\nExecuting query:\n", structured_query)
# structured_result = neo4j_kg.structured_query(structured_query)
# print("Structured Query Results:\n", structured_result)