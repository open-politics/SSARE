from generate_embeddings_onebatch import encode_text, semantic_chunking, process_content
from core.models import Content
from uuid import uuid4

def test_full_process():
    # Mock content data
    mock_content = Content(
        id=uuid4(),
        title="Test Title",
        text_content="This is the first section of the mock article. It contains some introductory sentences. Here is another sentence in the first section. \n\nThis is the second section of the mock article. It contains more detailed information. Another sentence follows in the second section."
    )
    
    # Process the mock content
    processed_content = process_content(mock_content)
    
    # Check if the processed content is not None
    assert processed_content is not None, "Processed content should not be None"
    
    # Check if the embeddings are generated
    assert 'embeddings' in processed_content, "Embeddings should be present in processed content"
    
    # Check if chunks are generated
    assert 'chunks' in processed_content, "Chunks should be present in processed content"
    assert len(processed_content['chunks']) > 0, "There should be at least one chunk"



    print("[PASSED] Processed content:", f"Nr: {processed_content['chunks'][0]['chunk_number']}, Text: {processed_content['chunks'][0]['text'][:10]}, Embeddings: {processed_content['chunks'][0]['embeddings'][:3]}...")

if __name__ == "__main__":
    test_full_process()