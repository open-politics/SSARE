from abc import ABC, abstractmethod

class URLBuilder(ABC):
    @abstractmethod
    def build_base_url(self, service_name: str, port: int) -> str:
        pass

class RemoteURLBuilder(URLBuilder):
    def build_base_url(self, service_name: str, port: int) -> str:
        # remote: https://api.opol.io/service-geo/
        return f"https://api.opol.io/{service_name}/"

class LocalURLBuilder(URLBuilder):
    def build_base_url(self, service_name: str, port: int) -> str:
        # local: http://localhost:port/
        return f"http://localhost:{port}/"

class ContainerURLBuilder(URLBuilder):
    def build_base_url(self, service_name: str, port: int) -> str:
        # container: http://service_name:port/
        return f"http://{service_name}:{port}/"
