sudo mkdir -p ./data/placeholder
sudo chmod 777 ./data/placeholder


sudo docker compose up --build -d

sleep 10

sudo docker exec -it ssare-ollama-1 ollama pull llama3.1