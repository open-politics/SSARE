from .client_base import BaseClient

class Classification(BaseClient):
    def get_classification(self, text: str) -> dict:
        endpoint = "classification-service/classify"
        return self.post(endpoint, {"text": text})