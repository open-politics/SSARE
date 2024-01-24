import requests


def trigger_flags():
    reponse = requests.get("http://localhost:5432/flags")
    print(reponse.json())

def trigger_scraping():
    reponse = requests.post("http://localhost:8081/create_scrape_jobs")
    print(reponse.json())


if __name__ == "__main__":
    # trigger_flags()
    trigger_scraping()



